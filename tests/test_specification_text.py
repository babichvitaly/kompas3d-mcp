from copy import deepcopy

import pytest

from kompas_mcp.specification_text import author_existing_row_text_owned

CONTEXT = {'owner': '/synthetic/owner.a3d', 'reference': '41', 'kind': 5,
           'description_index': 0, 'layout': 'synthetic', 'style': 1, 'source': ''}
PLAN = {'row_uuid': 'row-a', 'expected_context': CONTEXT,
        'cells': [{'column': c, 'execution': 1, 'block': 0, 'before': f'old-{c}',
                   'after': f'new-{c}'} for c in [4, 5]]}


class Adapter:
    def __init__(self, mode=None):
        self.mode, self.calls, self.changed = mode, [], False
        self.state = {'context': deepcopy(CONTEXT), 'rows': {
            uid: {'state': 0, 'sync': True, 'edit_source': False,
                  'columns': {'3': str(i), '4': 'old-4', '5': 'old-5', '6': '1'},
                  'draw': i == 1, 'geometry': [f'occurrence-{i}'],
                  'properties': {'4': ['old-4', True]}, 'pose': [1, 0, 0]}
            for i, uid in enumerate(['row-a', 'row-b'], 1)}}

    def guard_owned_context(self, expected):
        if self.mode == 'unowned' or (self.mode == 'lost_owner' and self.changed):
            raise ValueError('Ownership lost')
        assert self.state['context'] == expected

    def capture_state(self):
        return deepcopy(self.state)

    def row_number(self, uuid):
        assert uuid == 'row-a'
        return 4294967296.5  # double, beyond signed/unsigned 32-bit and not an integer

    def pointer_for_number(self, number):
        assert number == 4294967296.5
        return 71

    def number_for_pointer(self, ptr):
        assert ptr in {71, 83}
        return 3. if self.mode == 'wrong_number' else 4294967296.5

    def get_column_text(self, ptr, col, execution, block):
        assert (execution, block) == (1, 0)
        return 'wrong-address' if self.mode == 'address' else self.state['rows']['row-a']['columns'][str(col)]

    def edit(self, ptr):
        self.calls.append('edit')
        if self.mode == 'edit_exception':
            raise RuntimeError('Native exception after entering edit')
        return True if self.mode == 'bool_edit' else 0 if self.mode == 'edit_false' else 1

    def set_column_text(self, col, execution, block, text):
        self.calls.append('set')
        self.changed = True
        self.state['rows']['row-a']['columns'][str(col)] = text
        return 0 if self.mode == 'set_false' else 1

    def end(self):
        self.calls.append('end')
        row = self.state['rows']['row-a']
        if self.mode == 'position':
            self.state['rows']['row-b']['columns']['3'] = '1'
        elif self.mode == 'extra_parent':
            row['geometry'].append('parent')
        elif self.mode == 'uuid':
            self.state['rows']['new-uuid'] = self.state['rows'].pop('row-a')
        elif self.mode == 'flags':
            row['draw'] = False
        elif self.mode == 'property':
            row['properties']['4'][1] = False
        elif self.mode == 'pose':
            row['pose'][2] = 2
        return True if self.mode == 'bool_end' else 0 if self.mode == 'null_end' else 83


def test_complete_state_preserved_except_two_explicit_cells_and_end_is_pointer():
    adapter = Adapter()
    result = author_existing_row_text_owned(PLAN, adapter)
    assert result['status'] == 'text_verified_in_adapter'
    assert result['unique_number'] == 4294967296.5
    assert result['end_pointer'] == 83 != result['pointer_before']
    assert adapter.calls == ['edit', 'set', 'set', 'end']
    assert not result['edit_may_be_open'] and not result['saved']
    assert result['native_acceptance'] == 'pending'


@pytest.mark.parametrize('mode', ['unowned', 'wrong_number', 'address'])
def test_preflight_failure_never_edits(mode):
    adapter = Adapter(mode)
    result = author_existing_row_text_owned(PLAN, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert not adapter.calls


@pytest.mark.parametrize('mode', ['edit_false', 'bool_edit', 'edit_exception', 'set_false',
                                 'bool_end', 'null_end', 'lost_owner'])
def test_partial_native_failure_is_retained_without_retry_end_or_save(mode):
    adapter = Adapter(mode)
    result = author_existing_row_text_owned(PLAN, adapter)
    assert result['status'] == 'failed' and result['mutation_possible']
    assert result['edit_may_be_open'] and not result['retry_allowed']
    assert adapter.calls.count('edit') == 1 and adapter.calls.count('end') <= 1
    if mode in {'set_false', 'lost_owner'}:
        assert adapter.calls == ['edit', 'set']


@pytest.mark.parametrize('mode', ['position', 'extra_parent', 'uuid', 'flags', 'property', 'pose'])
def test_full_payload_gate_catches_hidden_and_non_text_changes(mode):
    result = author_existing_row_text_owned(PLAN, Adapter(mode))
    assert result['status'] == 'failed' and result['mutation_possible']
    assert not result['edit_may_be_open'] and not result['saved']


@pytest.mark.parametrize('change', [
    {'column': 3}, {'execution': 0}, {'block': -1}, {'column': True}, {'after': 'old-4'},
])
def test_invalid_or_noop_plan_rejected_before_native_access(change):
    plan = deepcopy(PLAN)
    plan['cells'][0].update(change)
    adapter = Adapter()
    result = author_existing_row_text_owned(plan, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert not adapter.calls


def test_non_independent_row_and_duplicate_cell_rejected():
    adapter = Adapter()
    adapter.state['rows']['row-a']['state'] = 1
    assert not author_existing_row_text_owned(PLAN, adapter)['mutation_possible']
    plan = deepcopy(PLAN)
    plan['cells'][1] = plan['cells'][0]
    assert not author_existing_row_text_owned(plan, Adapter())['mutation_possible']
