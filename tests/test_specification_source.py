from copy import deepcopy

import pytest

from kompas_mcp.specification_cached_text import author_cached_text_owned, plan_cached_text_refresh
from kompas_mcp.specification_source import plan_owned_source_refresh, refresh_owned_sources


def fixture():
    rows, props, tree, bindings = {}, {}, [], {}
    for i, u in enumerate(['first', 'hidden', 'control']):
        selected = i < 2
        geometry = {'object_id': u, 'metadata_key': u, 'source': '/synthetic/'+('A' if selected else 'B'),
                    'name': 'old' if selected else 'control', 'marking': 'mark', 'valid': True,
                    'matrix': [1, 0, 0], 'fixed': True}
        rows[u] = {'state': 0, 'sync': True, 'edit_source': False, 'draw': i != 1,
                   'is_first': i != 1, 'geometry': [deepcopy(geometry)],
                   'columns': {'3': '10' if selected else '20', '4': 'mark',
                               '5': 'old' if selected else 'control', '6': '1'}}
        props[u] = {'4': {'value': 'mark', 'from_source': True},
                    '5': {'value': 'new' if selected else 'control', 'from_source': True}}
        tree.append({'path': [i], **geometry})
        bindings[u] = [i]
    state = {'context': {'reference': 'native', 'owner': '/synthetic/owner.a3d', 'kind': 5,
                         'description_index': 0, 'style': 1, 'layout': 'standard', 'source': ''},
             'rows': rows, 'properties': props, 'top_tree': tree, 'main_tree': deepcopy(tree)}
    evidence = {'/synthetic/A': {'sha256': 'a'*64, 'values': {'4': 'mark', '5': 'new'}}}
    groups = {u: {'position': r['columns']['3'], 'summary': 2 if u == 'first' else 1,
                   'draw': r['draw'], 'is_first': r['is_first']} for u, r in rows.items()}
    return state, bindings, evidence, groups


def plan():
    s, b, e, g = fixture()
    return plan_owned_source_refresh(s, b, ['first', 'hidden'], e, [5], g)


class Adapter:
    def __init__(self, p, mode=None):
        self.state, self.sources = deepcopy(p['batch']['before']), deepcopy(p['source_evidence'])
        self.groups, self.final = deepcopy(p['group_summary']), deepcopy(p['batch']['expected_after'])
        self.calls, self.resets, self.mode = [], [], mode

    def guard_owned_context(self, context):
        self.calls.append('guard')
        if self.mode == 'wrong_owner':
            raise ValueError('ownership lost')
        assert context == self.state['context']

    def guarded(self, name):
        assert self.calls[-1] == 'guard'
        self.calls.append(name)

    def capture_state(self):
        self.guarded('capture')
        return deepcopy(self.state)

    def source_evidence(self):
        self.guarded('source')
        return deepcopy(self.sources)

    def group_summary(self):
        self.guarded('group')
        return deepcopy(self.groups)

    def reset_source_property(self, u, pid):
        self.guarded('reset')
        self.resets.append((u, pid))
        if self.mode == 'False':
            return False
        if self.mode == 'long1':
            return 1
        if self.mode != 'no_effect':
            self.state['rows'][u] = deepcopy(self.final['rows'][u])
            self.state['properties'][u] = deepcopy(self.final['properties'][u])
            for t in ['top_tree', 'main_tree']:
                for i, n in enumerate(self.state[t]):
                    if n['object_id'] == u:
                        self.state[t][i] = deepcopy(self.final[t][i])
        if self.mode == 'source_change':
            self.sources['/synthetic/A']['sha256'] = 'b'*64
        elif self.mode == 'source_flag':
            self.state['properties'][u]['5']['from_source'] = False
        elif self.mode == 'control_position':
            self.state['rows']['control']['columns']['3'] = '99'
        elif self.mode == 'extra_geometry':
            self.state['rows'][u]['geometry'].append({'object_id': 'parent'})
        elif self.mode == 'final_position':
            self.state['rows'][u]['columns']['3'] = '99'
        elif self.mode == 'quantity':
            self.groups['first']['summary'] = 1
        return True


def test_default_diagnostics_guards_sources_and_state_without_native_write():
    p = plan()
    adapter = Adapter(p)
    result = refresh_owned_sources(p, adapter)
    assert result['status'] == 'ready_without_mutation'
    assert adapter.resets == [] and result['mutation_possible'] is False and result['saved'] is False
    assert adapter.state == p['batch']['before']


def test_explicit_batch_keeps_numbered_group_source_flags_and_returns_unsaved():
    p = plan()
    adapter = Adapter(p)
    result = refresh_owned_sources(p, adapter, dry_run=False)
    assert result['status'] == 'verified_unsaved'
    assert adapter.state == p['batch']['expected_after']
    assert adapter.resets == [('first', 5), ('hidden', 5)]
    assert result['saved'] is False and result['native_acceptance'] == 'pending'
    assert result['retry_allowed'] is False


@pytest.mark.parametrize('mode, resets', [('wrong_owner', 0), ('source_change', 1),
                                        ('source_flag', 1), ('control_position', 1),
                                        ('extra_geometry', 1), ('False', 1), ('long1', 1),
                                        ('no_effect', 2), ('final_position', 2), ('quantity', 2)])
def test_partial_failure_never_saves_retries_or_waives_preservation(mode, resets):
    p = plan()
    adapter = Adapter(p, mode)
    result = refresh_owned_sources(p, adapter, dry_run=False)
    assert result['status'] == 'failed' and len(adapter.resets) == resets
    assert result['saved'] is False and result['retry_allowed'] is False
    if resets:
        assert result['mutation_possible'] is True


def test_source_revision_drift_is_rejected_before_first_setter():
    p = plan()
    adapter = Adapter(p)
    adapter.sources['/synthetic/A']['sha256'] = 'b'*64
    result = refresh_owned_sources(p, adapter, dry_run=False)
    assert result['status'] == 'failed' and adapter.resets == []


def test_saved_snapshot_reference_cannot_authorize_a_new_runtime_context():
    p = plan()
    adapter = Adapter(p)
    adapter.state['context']['reference'] = 'fresh-RW-reference'
    rejected = refresh_owned_sources(p, adapter, dry_run=False)
    assert rejected['status'] == 'failed' and adapter.resets == []
    # Reopen-stable semantic evidence stays exact, but ownership must be rebound
    # explicitly from a fresh complete capture before preparing the live plan.
    rebound = plan_owned_source_refresh(adapter.state, p['bindings'], ['first', 'hidden'],
                                        p['source_evidence'], [5], p['group_summary'])
    accepted = refresh_owned_sources(rebound, adapter)
    assert accepted['status'] == 'ready_without_mutation' and adapter.resets == []


@pytest.mark.parametrize('mode', ['nested', 'override', 'wrong_style', 'basename', 'extra_parent',
                                 'missing_binding', 'changed_object_id', 'missing_hash'])
def test_preflight_blocks_unproven_routes_overrides_and_inexact_source_identity(mode):
    s, b, e, g = fixture()
    if mode == 'nested':
        b['first'] = [0, 0]
    elif mode == 'override':
        s['properties']['hidden']['5']['from_source'] = False
    elif mode == 'wrong_style':
        s['context']['style'] = 2
    elif mode == 'basename':
        e['/another/A'] = e.pop('/synthetic/A')
    elif mode == 'extra_parent':
        s['rows']['first']['geometry'].append({'object_id': 'parent'})
    elif mode == 'missing_binding':
        b.pop('control')
    elif mode == 'changed_object_id':
        s['rows']['first']['geometry'][0]['object_id'] = 'other'
    elif mode == 'missing_hash':
        e['/synthetic/A']['sha256'] = ''
    with pytest.raises(ValueError):
        plan_owned_source_refresh(s, b, ['first', 'hidden'], e, [5], g)


def test_tampered_expected_position_is_rejected_before_native_access():
    p = plan()
    p['batch']['expected_after']['rows']['hidden']['columns']['3'] = '99'
    adapter = Adapter(p)
    result = refresh_owned_sources(p, adapter, dry_run=False)
    assert result['status'] == 'failed' and adapter.calls == []


def test_property4_cache_update_needs_explicit_policy_and_source_proof():
    s, b, e, g = fixture()
    for u in ['first', 'hidden']:
        s['rows'][u]['columns']['5'] = 'new'
        s['rows'][u]['geometry'][0]['name'] = 'new'
    for tree in ['top_tree', 'main_tree']:
        for n in s[tree][:2]:
            n['name'] = 'new'
    e['/synthetic/A']['values']['4'] = 'new designation'
    with pytest.raises(ValueError, match='cache change not declared'):
        plan_owned_source_refresh(s, b, ['first', 'hidden'], e, [4], g)
    p = plan_owned_source_refresh(s, b, ['first', 'hidden'], e, [4], g,
                                  allow_property_value_refresh=True)
    adapter = Adapter(p)
    result = refresh_owned_sources(p, adapter, dry_run=False)
    assert result['status'] == 'verified_unsaved'
    assert adapter.state['properties']['hidden']['4'] == {
        'value': 'new designation', 'from_source': True}


def text_plan():
    p = plan()
    current = deepcopy(p['batch']['expected_after'])
    for u in ['first', 'hidden']:
        current['rows'][u]['columns']['5'] = 'old'
    return plan_cached_text_refresh(current, ['first', 'hidden'], p['source_evidence'], [5],
                                    p['group_summary'])


class TextBatchAdapter(Adapter):
    ids = ('first', 'hidden', 'control')

    def __init__(self, p, mode=None):
        super().__init__(p, mode)
        self.editing, self.pending, self.edits = None, None, []

    def row_number(self, u):
        self.guarded('number')
        return 100.+self.ids.index(u)

    def pointer_for_number(self, number):
        self.guarded('pointer')
        return int(number)+1000

    def number_for_pointer(self, ptr):
        self.guarded('roundtrip')
        return float(ptr-1000)+(1 if self.mode == 'wrong_roundtrip' else 0)

    def get_column_text(self, ptr, c, execution, block):
        self.guarded('get_text')
        assert (execution, block) == (1, 0)
        return self.state['rows'][self.ids[ptr-1100]]['columns'][str(c)]

    def edit(self, ptr):
        self.guarded('edit')
        self.editing = self.ids[ptr-1100]
        self.pending = {}
        self.edits.append(self.editing)
        return True if self.mode == 'bool_Edit' else 1

    def set_column_text(self, c, execution, block, text):
        self.guarded('set')
        assert (execution, block) == (1, 0)
        self.pending[str(c)] = text
        return 0 if self.mode == 'failed_Set' else 1

    def end(self):
        self.guarded('end')
        u = self.editing
        if self.mode != 'no_effect':
            self.state['rows'][u]['columns'].update(self.pending)
        if self.mode == 'source_flag':
            self.state['properties'][u]['5']['from_source'] = False
        elif self.mode == 'source_change':
            self.sources['/synthetic/A']['sha256'] = 'b'*64
        elif self.mode == 'final_position':
            self.state['rows'][u]['columns']['3'] = '99'
        self.editing = None
        return 1100+self.ids.index(u)


def test_cached_text_dry_run_and_explicit_batch_preserve_the_complete_numbered_state():
    p = text_plan()
    adapter = TextBatchAdapter(p)
    ready = author_cached_text_owned(p, adapter)
    assert ready['status'] == 'ready_without_mutation' and adapter.edits == []
    result = author_cached_text_owned(p, adapter, dry_run=False)
    assert result['status'] == 'verified_unsaved' and result['saved'] is False
    assert result['edit_may_be_open'] is False
    assert adapter.state == p['batch']['expected_after']
    assert adapter.edits == ['first', 'hidden']


@pytest.mark.parametrize('mode, edits, pending', [('wrong_roundtrip', 0, False),
                                                ('bool_Edit', 1, True), ('failed_Set', 1, True),
                                                ('source_flag', 1, False), ('source_change', 1, False),
                                                ('no_effect', 2, False), ('final_position', 2, False)])
def test_cached_text_failure_retains_partial_edit_state_and_never_saves(mode, edits, pending):
    p = text_plan()
    adapter = TextBatchAdapter(p, mode)
    result = author_cached_text_owned(p, adapter, dry_run=False)
    assert result['status'] == 'failed' and result['saved'] is False
    assert result['retry_allowed'] is False and len(adapter.edits) == edits
    assert result['edit_may_be_open'] is pending


def test_cached_text_preflight_rejects_current_values_with_old_display_cache():
    s, _, e, g = fixture()
    with pytest.raises(ValueError):
        plan_cached_text_refresh(s, ['first', 'hidden'], e, [5], g)


def test_cached_text_tampered_grouping_waiver_is_rejected_before_native_access():
    p = text_plan()
    p['batch']['expected_after']['rows']['hidden']['is_first'] = True
    adapter = TextBatchAdapter(p)
    result = author_cached_text_owned(p, adapter, dry_run=False)
    assert result['status'] == 'failed' and adapter.calls == []


def test_two_cell_text_batch_preserves_both_inherited_properties():
    old = text_plan()
    state = deepcopy(old['batch']['before'])
    evidence = deepcopy(old['source_evidence'])
    evidence['/synthetic/A']['values']['4'] = 'current designation'
    for u in ['first', 'hidden']:
        state['properties'][u]['4']['value'] = 'current designation'
        state['rows'][u]['geometry'][0]['marking'] = 'current designation'
    for tree in ['top_tree', 'main_tree']:
        for n in state[tree][:2]:
            n['marking'] = 'current designation'
    p = plan_cached_text_refresh(state, ['first', 'hidden'], evidence, [4, 5], old['group_summary'])
    adapter = TextBatchAdapter(p)
    result = author_cached_text_owned(p, adapter, dry_run=False)
    assert result['status'] == 'verified_unsaved' and result['saved'] is False
    assert adapter.state == p['batch']['expected_after']
    assert all(len(r['Set_returns']) == 2 for r in result['text_calls'])
