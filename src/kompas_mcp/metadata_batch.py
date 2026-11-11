"""Bounded metadata snapshot reuse with fresh cheap guards on every operation.

This is orchestration for an injected adapter, not a COM connection or rollback
transaction. No persistent/global cache, save, close, retry or native speed claim.
"""

import hashlib
import json
import time
from typing import Annotated

from pydantic import Field, StrictBool

from .authoring_contracts import NativeRow
from .state_oracles import Evidence, Key, PositiveInt
from .view_state import Finite, Sha256, ViewState


class GuardState(Evidence):
    owned_reference: Key
    owned_path: Key
    owned: StrictBool
    owned_read_only: StrictBool
    source_reference: Key
    source_path: Key
    source_read_only: StrictBool
    source_changed: StrictBool


class Limits(Evidence):
    max_steps: Annotated[PositiveInt, Field(le=128)] = 32
    max_rows: Annotated[PositiveInt, Field(le=50000)] = 5000
    max_cells: Annotated[PositiveInt, Field(le=500000)] = 100000
    max_seconds: Annotated[Finite, Field(gt=0, le=3600)] = 60.


class Metadata(Evidence):
    source_rows: list[NativeRow]
    owned_rows: list[NativeRow]
    original_hashes: dict[Key, Sha256]


class Step(Evidence):
    name: Key
    expected_view_state: ViewState


def _digest(payload):
    value = json.dumps(payload.model_dump(mode='json'), sort_keys=True,
                       separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(value.encode()).hexdigest()


def run_metadata_batch(adapter, expected_guard, original_hashes, steps,
                       expected_owned_rows=None, limits=None):
    """Full metadata at entry/exit; no metadata traversal in cheap guard or steps.

    Adapter provides read_guard_state(), read_metadata(limits), execute_step(name)
    and read_view_state(name). Callbacks run synchronously on the caller's owning
    STA. Each callback must implement its documented bounded, exact checks.
    """
    result = {'operation': 'metadata_batch', 'status': 'failed', 'completed_steps': [],
              'full_metadata_reads': 0, 'cheap_guard_reads': 0, 'mutation_possible': False,
              'retry_allowed': False, 'saved': False, 'native_acceptance': 'pending'}
    phase, before, after, after_attempted = 'preflight', None, None, False
    start = time.monotonic()
    try:
        guard = GuardState.model_validate(expected_guard).model_copy(deep=True)
        cap = Limits.model_validate(limits or {}).model_copy(deep=True)
        plan = [Step.model_validate(step).model_copy(deep=True) for step in steps]
        # Validate hash types independently before invoking any adapter callback.
        hashes = Metadata(source_rows=[], owned_rows=[], original_hashes=original_hashes).original_hashes
        if not hashes or not guard.owned or guard.owned_read_only or not guard.source_read_only or guard.source_changed:
            raise ValueError('Pinned originals and writable owned/read-only unchanged source required')
        if guard.source_path not in hashes or guard.owned_path in hashes:
            raise ValueError('Original hashes must pin the source path and exclude the owned target')
        if guard.owned_path == guard.source_path or guard.owned_reference == guard.source_reference:
            raise ValueError('Owned target and read-only source must be distinct')
        if not plan or len(plan) > cap.max_steps or len({s.name for s in plan}) != len(plan):
            raise ValueError('Use a bounded nonempty plan of unique named steps')
        wanted_rows = None if expected_owned_rows is None else [
            NativeRow.model_validate(row).model_copy(deep=True) for row in expected_owned_rows]
        required = ('read_guard_state', 'read_metadata', 'execute_step', 'read_view_state')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete metadata batch adapter')

        def cheap():
            nonlocal phase
            phase = 'cheap_guard'
            result['cheap_guard_reads'] += 1
            actual = GuardState.model_validate(adapter.read_guard_state())
            if actual != guard:
                raise ValueError('Ownership/reference/path/readOnly/sourceChanged guard changed')

        def full(label):
            nonlocal phase
            cheap()
            phase = label
            result['full_metadata_reads'] += 1
            # Adapter must enforce limits before native enumeration, not only after.
            snapshot = Metadata.model_validate(adapter.read_metadata(cap.model_dump())).model_copy(deep=True)
            cheap()
            phase = label + '_validate'
            rows = snapshot.source_rows + snapshot.owned_rows
            if len(rows) > cap.max_rows or sum(len(row.columns) for row in rows) > cap.max_cells:
                raise ValueError('Full metadata traversal exceeded bounded row/cell scope')
            for group in (snapshot.source_rows, snapshot.owned_rows):
                if len({row.uuid for row in group}) != len(group):
                    raise ValueError('Ambiguous metadata row UUID')
            if snapshot.original_hashes != hashes:
                raise ValueError('Read-only source bytes changed')
            return snapshot

        def finish():
            nonlocal after, after_attempted, phase
            after_attempted = True
            after = full('metadata_exit')
            result['after_metadata_digest'] = _digest(after)
            if after.source_rows != before.source_rows:
                phase = 'metadata_exit_compare'
                raise ValueError('Read-only source metadata changed during batch')
            expected = before.owned_rows if wanted_rows is None else wanted_rows
            if after.owned_rows != expected:
                phase = 'metadata_exit_compare'
                raise ValueError('Unexpected owned UUID/columns/section/sync payload at batch exit')

        before = full('metadata_entry')
        result['before_metadata_digest'] = _digest(before)
        for step in plan:
            cheap()
            phase = 'batch_budget'
            if time.monotonic() - start > cap.max_seconds:
                raise ValueError('Cooperative batch time budget exceeded; do not retry')
            phase = 'execute:' + step.name
            result['mutation_possible'] = True
            adapter.execute_step(step.name)
            cheap()
            phase = 'view_state:' + step.name
            actual = ViewState.model_validate(adapter.read_view_state(step.name))
            if actual != step.expected_view_state:
                raise ValueError('Exact geometry/pose/view state differs')
            cheap()
            result['completed_steps'].append(step.name)
        finish()
        phase = 'batch_budget'
        if time.monotonic() - start > cap.max_seconds:
            raise ValueError('Batch completed checks but exceeded its time budget')
        result['status'] = 'batch_verified_in_adapter'
    except Exception as exc:  # noqa: BLE001 - never replay an uncertain mutation
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}')
        if before is not None and not after_attempted:
            # One guarded exit snapshot, no operation retry. Ownership loss blocks
            # even this read so an unknown document is never adopted for diagnostics.
            try:
                finish()
            except Exception as exit_exc:  # noqa: BLE001
                result['exit_check_error'] = f'{type(exit_exc).__name__}: {exit_exc}'
        result['recovery'] = 'Reconcile the owned partial batch and source snapshots; no automatic retry'
    result['elapsed_seconds'] = time.monotonic() - start
    return result
