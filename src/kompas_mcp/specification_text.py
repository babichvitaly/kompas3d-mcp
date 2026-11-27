"""Bounded API5 text authoring on an explicitly owned existing model-SP row.

No COM imports, connections, saves, retries or implicit edit-context recovery.
The caller supplies an adapter on its exclusive STA worker. Detached snapshots
must cover ALL rows, flags, geometry membership, positions, properties and poses;
the helper cannot establish completeness of an adapter's native observations.
"""

from copy import deepcopy
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field


class TextCellChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)

    column: int
    execution: int = Field(ge=1)
    block: int = Field(ge=0)
    before: str
    after: str


class ExistingRowTextPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)

    row_uuid: str = Field(min_length=1)
    expected_context: dict
    expected_sync: bool = True
    cells: list[TextCellChange] = Field(min_length=1, max_length=2)


def author_existing_row_text_owned(plan, adapter):
    """Edit one exact UUID, then require the entire observed payload to match.

    ``capture_state`` returns a detached JSON-serializable mapping with ``context``
    and ``rows`` (UUID -> complete payload). Each row's ``columns`` maps decimal
    column types to text for the explicitly verified execution/block. Do not use
    this adapter contract for multiple text blocks represented by the same key.
    Context must include exact owner path/reference/type and description identity.
    Sync=True is the default; a different expected_sync must be explicit. The
    helper never changes that flag or accepts any post-write flag drift.
    The adapter's guard must verify exclusive ownership and current context before
    EVERY native access, including reads. No Save is performed here.

    A failed setter/End can leave a native edit open. It is deliberately retained
    for explicit reconciliation; no automatic End, cancel, retry or save follows.
    """
    result = {'operation': 'author_existing_row_text_owned', 'status': 'failed',
              'events': [], 'mutation_possible': False, 'edit_may_be_open': False,
              'saved': False, 'retry_allowed': False, 'native_acceptance': 'pending'}
    phase = 'preflight'
    try:
        wanted = ExistingRowTextPlan.model_validate(plan).model_copy(deep=True)
        if not wanted.expected_context or not wanted.row_uuid.strip():
            raise ValueError('Explicit owner/description context and UUID required')
        columns = [cell.column for cell in wanted.cells]
        if len(set(columns)) != len(columns) or not set(columns) <= {4, 5}:
            raise ValueError('Only distinct explicit designation/name columns 4/5 are supported')
        if any(cell.before == cell.after for cell in wanted.cells):
            raise ValueError('Text plan must declare actual finite cell changes')
        required = ('guard_owned_context', 'capture_state', 'row_number', 'pointer_for_number',
                    'number_for_pointer', 'get_column_text', 'edit', 'set_column_text', 'end')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete existing-row text adapter')

        def call(name, *args, mutates=False):
            nonlocal phase
            phase = 'guard_before_' + name
            adapter.guard_owned_context(deepcopy(wanted.expected_context))
            phase = name
            if mutates:
                result['mutation_possible'] = True
            value = getattr(adapter, name)(*args)
            result['events'].append(name)
            return value

        def number(value):
            if type(value) not in {float, int} or not isfinite(value) or value <= 0:
                raise ValueError('Invalid native UniqueNumber; never substitute UUID/index/position')
            return value

        def pointer(value):
            if type(value) is not int or value <= 0:
                raise ValueError('API5 object pointer must be a positive long, not BOOL')
            return value

        def success(value, label):
            if type(value) is not int or value != 1:
                raise ValueError(label + ' did not return native long 1')

        before = deepcopy(call('capture_state'))
        if before['context'] != wanted.expected_context or wanted.row_uuid not in before['rows']:
            raise ValueError('Exact owner/description or existing UUID mismatch')
        previous = before['rows'][wanted.row_uuid]
        if (type(previous['state']) is not int or previous['state'] != 0
                or previous['sync'] is not wanted.expected_sync or previous['edit_source'] is not False):
            raise ValueError('Require own independent row, explicitly pinned Sync and EditSourceObject=False')
        expected = deepcopy(before)
        native_number = number(call('row_number', wanted.row_uuid))
        ptr = pointer(call('pointer_for_number', native_number))
        if number(call('number_for_pointer', ptr)) != native_number:
            raise ValueError('API7/API5 numeric mapping does not roundtrip')
        result.update(row_uuid=wanted.row_uuid, unique_number=native_number, pointer_before=ptr)
        for cell in wanted.cells:
            if previous['columns'][str(cell.column)] != cell.before:
                raise ValueError('Plan differs from complete API7 snapshot')
            text = call('get_column_text', ptr, cell.column, cell.execution, cell.block)
            if type(text) is not str or text != cell.before:
                raise ValueError('Exact API5 column address does not match API7 text')
            expected['rows'][wanted.row_uuid]['columns'][str(cell.column)] = cell.after
        result['before'] = before
        # Detect a changed row/context after the preflight getters, before Edit.
        if call('row_number', wanted.row_uuid) != native_number or call('capture_state') != before:
            raise ValueError('Preflight state drifted')
        result['edit_may_be_open'] = True  # native exception can occur after entering Edit
        edited = call('edit', ptr, mutates=True)
        result['edit_return'] = edited
        success(edited, 'Edit')
        result['set_returns'] = []
        for cell in wanted.cells:
            returned = call('set_column_text', cell.column, cell.execution, cell.block,
                            cell.after, mutates=True)
            result['set_returns'].append(returned)
            success(returned, 'SetColumnText')
        ended = call('end', mutates=True)
        result['end_pointer'] = ended
        pointer(ended)
        result['edit_may_be_open'] = False
        if number(call('number_for_pointer', ended)) != native_number:
            raise ValueError('End pointer resolves to a different UniqueNumber')
        if call('row_number', wanted.row_uuid) != native_number:
            raise ValueError('Existing UUID numeric identity changed')
        after = deepcopy(call('capture_state'))
        result['after'] = after
        if after != expected:
            raise ValueError('Payload/UUID/flags/Geometry/position/properties/poses changed beyond plan')
        for cell in wanted.cells:
            if call('get_column_text', ended, cell.column, cell.execution, cell.block) != cell.after:
                raise ValueError('API5 text readback after End differs')
        phase = 'final_ownership_guard'
        adapter.guard_owned_context(deepcopy(wanted.expected_context))
        result.update(status='text_verified_in_adapter', expected_after=expected)
    except Exception as exc:  # noqa: BLE001 - preserve partial native mutation, never retry
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile owned RAM and edit context before any new native job')
    return result
