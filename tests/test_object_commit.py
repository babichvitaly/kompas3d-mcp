"""Stateful synthetic child/parent objects with independent commit buffers."""

from copy import deepcopy

import pytest

from kompas_mcp.object_commit import assess_object_commits


class NativeLikeObject:
    def __init__(self, **properties):
        self.live = dict(properties)
        self.committed = dict(properties)

    def Update(self):
        self.committed = dict(self.live)
        return True

    def reopen(self):
        return dict(self.committed)


def evidence(commit_layer=True):
    layer = NativeLikeObject(Visible=True, Printable=True)
    view = NativeLikeObject(Visible=True)
    layer.live.update(Visible=False, Printable=False)
    layer_update = layer.Update() if commit_layer else None
    view.live['Visible'] = False
    view.Update()  # intentionally does not invoke any child's Update
    layer_key, view_key = 'drawing/view/layer0', 'drawing/view'
    expected = {layer_key: {'Visible': False, 'Printable': False}, view_key: {'Visible': False}}
    saved = {layer_key: layer.reopen(), view_key: view.reopen()}
    return {'expected_context': 'drawing/system-view0', 'actual_context': 'drawing/system-view0',
            'context_committed_epoch': 1,
            'objects': [{'key': layer_key, 'interface': 'ILayer', 'expected': expected[layer_key]},
                        {'key': view_key, 'interface': 'IView', 'expected': expected[view_key]}],
            'setters': [{'target': layer_key, 'property': 'Visible', 'value': False, 'epoch': 2},
                        {'target': layer_key, 'property': 'Printable', 'value': False, 'epoch': 3},
                        {'target': view_key, 'property': 'Visible', 'value': False, 'epoch': 5}],
            'updates': ([{'target': layer_key, 'epoch': 4, 'returned': layer_update}]
                        if commit_layer else []) + [{'target': view_key, 'epoch': 6, 'returned': True}],
            'immediate_getters': {layer_key: dict(layer.live), view_key: dict(view.live)},
            'save_epoch': 7, 'sealed_sha256': 'a'*64,
            'reopens': [{'open_id': str(i), 'epoch': 8+i, 'read_only': True,
                         'artifact_sha256': 'a'*64, 'objects': deepcopy(saved)} for i in range(2)]}


def test_layer_own_update_persists_both_flags_through_two_synthetic_reopens():
    result = assess_object_commits(evidence())
    assert result['status'] == 'consistent_offline_evidence'
    assert result['native_acceptance'] == 'pending' and not result['mutation_performed']


def test_parent_update_and_immediate_false_getter_do_not_persist_child_flags():
    e = evidence(commit_layer=False)
    assert e['immediate_getters']['drawing/view/layer0']['Printable'] is False
    assert e['reopens'][0]['objects']['drawing/view/layer0']['Printable'] is True
    assert e['reopens'][0]['objects']['drawing/view']['Visible'] is False
    assert assess_object_commits(e)['status'] == 'rejected'


def test_fabricated_matching_saved_flags_still_cannot_replace_layer_update_event():
    e = evidence(commit_layer=False)
    for r in e['reopens']:
        r['objects'] = deepcopy(e['immediate_getters'])
    assert assess_object_commits(e)['status'] == 'rejected'


@pytest.mark.parametrize('path,value', [
    (('updates', 0, 'target'), 'drawing/view'),  # parent update is insufficient
    (('updates', 0, 'epoch'), 0),
    (('save_epoch',), 4),
    (('actual_context',), 'drawing/uncommitted-other-view'),
    (('context_committed_epoch',), 3),
    (('reopens', 1, 'objects', 'drawing/view/layer0', 'Printable'), True),
    (('reopens', 1, 'objects', 'drawing/view/layer0', 'Printable'), 0),
    (('reopens', 0, 'read_only'), False),
    (('reopens', 1, 'artifact_sha256'), 'b'*64),
    (('reopens', 1, 'open_id'), '0'),
    (('reopens', 0, 'epoch'), 6),
])
def test_mutation_commit_save_reopen_contract_rejects_wrong_scope_or_order(path, value):
    e = evidence()
    parent = e
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert assess_object_commits(e)['status'] == 'rejected'


def test_a_later_setter_invalidates_an_earlier_commit_even_with_matching_getters():
    e = evidence()
    e['setters'].append({'target': 'drawing/view/layer0', 'property': 'Printable',
                         'value': False, 'epoch': 7})
    e['save_epoch'] = 8
    for i, reopen in enumerate(e['reopens']):
        reopen['epoch'] = 9+i
    assert assess_object_commits(e)['status'] == 'rejected'


def test_false_own_update_requires_separate_native_policy_not_a_layer_waiver():
    e = evidence()
    e['updates'][0]['returned'] = False
    assert assess_object_commits(e)['status'] == 'rejected'
