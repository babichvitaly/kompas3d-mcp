"""Sequential row-binding orchestration; native adapters require separate acceptance.

No COM imports, connections, save, close, retries or implicit document adoption.
The caller injects an adapter on its exclusively owned CAD STA worker.
"""

from typing import Protocol

from .authoring_contracts import OccurrenceKey


class RowBindingAdapter(Protocol):
    def guard_owned_document(self): ...
    def mutate_boundary(self, kind): ...
    def resolve_occurrence(self, key): ...
    def occurrence_key(self, occurrence): ...
    def occurrence_reference(self, occurrence): ...
    def row_uuid(self, row): ...
    def include_geometry(self, row, occurrence): ...
    def update_row(self, row): ...
    def geometry_references(self, row): ...


def bind_row_geometry_owned(expected, boundary_kind, adapter: RowBindingAdapter):
    """Apply one explicit boundary, refetch twice and verify exact geometry binding.

    Adapter must validate the current document's identity/path/ownership and reject
    ambiguous occurrence lookup. mutate_boundary returns the one explicitly scoped
    row. It may create a row or finish the selected description/tuning mutation.
    Raw Update=False is retained; exact UUID and geometry readback are the gates.
    A failure preserves a serializable partial receipt and forbids automatic retry.
    """
    result = {'operation': 'bind_row_geometry_owned', 'status': 'failed', 'events': [],
              'mutation_possible': False, 'retry_allowed': False, 'saved': False,
              'native_acceptance': 'pending'}
    phase = 'preflight'
    try:
        wanted = OccurrenceKey.model_validate(expected).model_copy(deep=True)
        if boundary_kind not in {'row_add', 'description_add', 'tuning_update'}:
            raise ValueError('Unsupported explicit mutation boundary')
        # Validate all adapter capabilities before crossing a mutation boundary.
        required = ('guard_owned_document', 'mutate_boundary', 'resolve_occurrence',
                    'occurrence_key', 'occurrence_reference', 'row_uuid',
                    'include_geometry', 'update_row', 'geometry_references')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete row binding adapter')

        def call(name, *args, mutates=False):
            nonlocal phase
            phase = 'guard_before_' + name
            adapter.guard_owned_document()
            phase = name
            if mutates:
                result['mutation_possible'] = True  # mark before entering uncertain native code
            value = getattr(adapter, name)(*args)
            result['events'].append(name)
            return value

        def fresh():
            obj = call('resolve_occurrence', wanted.model_copy(deep=True))
            actual = OccurrenceKey.model_validate(call('occurrence_key', obj))
            if actual != wanted:
                raise ValueError('Fresh occurrence path/source/matrix mismatch')
            reference = call('occurrence_reference', obj)
            if not isinstance(reference, str) or not reference:
                raise ValueError('Expected an explicit native occurrence reference')
            return obj, reference

        row = call('mutate_boundary', boundary_kind, mutates=True)
        uuid = call('row_uuid', row)
        if not isinstance(uuid, str) or not uuid:
            raise ValueError('Expected an explicit native row UUID')
        first, first_ref = fresh()
        included = call('include_geometry', row, first, mutates=True)
        if included is not True:
            raise ValueError('IncludeGeometry did not confirm inclusion')
        # Never read the cached occurrence again after another mutation.
        del first
        updated = call('update_row', row, mutates=True)
        if not isinstance(updated, bool):
            raise TypeError('Adapter must report Update as an explicit boolean')
        result['update_return'] = updated
        second, second_ref = fresh()
        del second
        if call('row_uuid', row) != uuid:
            raise ValueError('Row UUID changed across Update')
        refs = call('geometry_references', row)
        result.update(reference_after_boundary=first_ref, reference_after_update=second_ref)
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ValueError('Expected a detached list of native geometry references')
        result['geometry_references'] = list(refs)
        if refs != [second_ref]:
            count = refs.count(second_ref)
            result['geometry_mismatch'] = {
                'expected_reference_present': count > 0,
                'expected_reference_count': count,
                'actual_member_count': len(refs),
                'additional_references': [ref for ref in refs if ref != second_ref],
                'classification': ('extra_membership' if count == 1 else
                                   'duplicate_target_reference' if count > 1 else
                                   'expected_reference_not_observed'),
                'semantic_link_loss_established': False,
            }
            raise ValueError('Geometry differs from exact fresh post-Update occurrence')
        phase = 'final_ownership_guard'
        adapter.guard_owned_document()
        result.update(status='binding_verified_in_adapter', row_uuid=uuid,
                      expected_occurrence=wanted.model_dump(mode='json'),
                      reference_after_boundary=first_ref, reference_after_update=second_ref,
                      geometry_references=refs)
    except Exception as exc:  # noqa: BLE001 - preserve partial mutation evidence, never retry
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile the owned unsaved copy and native state before any new job')
    return result
