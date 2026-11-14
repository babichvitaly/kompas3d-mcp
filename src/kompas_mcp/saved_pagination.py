"""Bounded two-phase saved pagination and owned-dependent writeback checks."""

from pydantic import TypeAdapter

from .publication_finalization import SpecificationPlan, SpecificationState, _spw
from .state_oracles import Evidence, Key
from .view_state import Sha256


class Dependent(Evidence):
    bytes_sha256: Sha256
    geometry_sha256: Sha256
    fields_sha256: Sha256
    frame_sha256: Sha256


def stabilize_saved_pagination(adapter, specification, original_hashes, owned_dependents,
                               max_saves=3):
    """Discover saved count, write total, verify saved fixed point before final seal.

    Adapter must guard exact owned SPW/dependent scope and read-only originals;
    Save/Close/Open are explicit phases, never exception retries. Each save can
    reserialize ONLY the explicitly owned dependents with unchanged semantics.
    """
    result = {'status': 'failed', 'saved_observations': [], 'owned_byte_changes': [],
              'save_count': 0, 'mutation_possible': False, 'retry_allowed': False,
              'native_acceptance': 'pending', 'ready_for_finalization': False}
    phase = 'preflight'
    try:
        plan = SpecificationPlan.model_validate(specification).model_copy(deep=True)
        originals = TypeAdapter(dict[Key, Sha256]).validate_python(original_hashes)
        baseline = TypeAdapter(dict[Key, Dependent]).validate_python(owned_dependents)
        baseline = {k: v.model_copy(deep=True) for k, v in baseline.items()}
        if (not originals or set(originals) & (set(baseline) | {plan.key})
                or plan.key in baseline or isinstance(max_saves, bool)
                or not isinstance(max_saves, int) or not 2 <= max_saves <= 8):
            raise ValueError('Disjoint originals/owned SPW/dependents and bounded saves required')

        def guard():
            adapter.guard_owned_scope(plan.key, tuple(baseline), tuple(originals))
            if adapter.read_original_hashes() != originals:
                raise ValueError('Immutable input bytes changed')

        def read_saved():
            value = SpecificationState.model_validate(adapter.read_saved_specification())
            # Validate pagination/styles/rows/library independently of a stale total field.
            candidate = value.model_copy(update={'text8': str(value.saved_api5_pages)})
            _spw(plan, candidate)
            result['saved_observations'].append(value.model_dump(mode='json'))
            return value

        def dependents():
            state = TypeAdapter(dict[Key, Dependent]).validate_python(adapter.read_owned_dependents())
            if state.keys() != baseline.keys():
                raise ValueError('Owned dependent scope changed')
            for key, current in state.items():
                if current.model_dump(exclude={'bytes_sha256'}) != baseline[key].model_dump(
                        exclude={'bytes_sha256'}):
                    raise ValueError('Owned dependent geometry/fields/frame changed')
                if (current.bytes_sha256 != baseline[key].bytes_sha256
                        and key not in result['owned_byte_changes']):
                    result['owned_byte_changes'].append(key)
            return state

        phase = 'entry_guard'
        guard()
        if TypeAdapter(dict[Key, Dependent]).validate_python(adapter.read_owned_dependents()) != baseline:
            raise ValueError('Owned dependent baseline differs before writeback')
        previous = None
        for attempt in range(max_saves):
            phase = 'save_close_open'
            guard()
            result['mutation_possible'] = True
            result['save_count'] += 1
            adapter.save_close_open_specification()
            guard()
            phase = 'saved_pagination_readback'
            current = read_saved()
            latest_dependents = dependents()
            if current.text8 == str(current.saved_api5_pages):
                # Second phase may be a non-writing saved RO confirmation when
                # the saved header already agrees. Never save merely to confirm.
                phase = 'saved_confirmation'
                guard()
                adapter.open_saved_readonly_confirmation()
                confirmed = read_saved()
                latest_dependents = dependents()
                guard()
                if confirmed != current:
                    raise ValueError('Saved pagination/header is not stable on confirmation')
                if previous is not None and previous != current.saved_api5_pages:
                    raise ValueError('Header update changed saved pagination; reconcile layout before proceeding')
                result.update(status='saved_pagination_stable_in_adapter',
                              ready_for_finalization=True, final_saved_pages=current.saved_api5_pages,
                              dependent_hashes_after_writeback={k: v.bytes_sha256
                                                               for k, v in latest_dependents.items()})
                break
            if attempt + 1 == max_saves:
                raise ValueError('Pagination/header did not stabilize within the explicit save budget')
            phase = 'write_total_from_saved_count'
            guard()
            adapter.set_total_field(current.saved_api5_pages)
            previous = current.saved_api5_pages
        if not result['ready_for_finalization']:
            raise ValueError('No saved fixed point established')
    except Exception as exc:  # noqa: BLE001 - no save replay or blind header retry after errors
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile saved pagination and owned writeback before final CDW serialization/seal')
    return result
