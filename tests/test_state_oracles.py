"""Synthetic receipt matrices; never imports COM or reads an engineering file."""

import json
from copy import deepcopy

import pytest

from kompas_mcp.state_oracles import assess_sheet_history, assess_view_update


def view_evidence():
    state = {'number': 3, 'view_type': 7, 'source': '/synthetic/root/model.m3d',
             'source_sha256': 'a'*64, 'scale': 1., 'x': 120., 'y': 80., 'angle': 0.,
             'matrix': [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.],
             'bounds': (0., 0., 20., 10.), 'objects': 8, 'unfold': False,
             'geometry_digest': 'b'*64}
    observation = {'state': state, 'valid': True, 'supported_geometry_objects': 6}
    return deepcopy({'update_return': False, 'expected_source': state['source'],
                     'expected_source_sha256': 'a'*64, 'requested_pose': (1., 120., 80.),
                     'before': observation, 'after': observation,
                     'expected_view_numbers': [1, 3],
                     'view_rebuilds': [{'number': 1, 'succeeded': True},
                                       {'number': 3, 'succeeded': True}],
                     'document_rebuilt': True, 'saved_drawing_sha256': 'c'*64,
                     'reopens': [{**observation, 'open_id': name, 'read_only': True,
                                  'drawing_sha256': 'c'*64} for name in ['first', 'second']]})


def isolated_view_evidence():
    # Break shared fixture aliases so each mutation tests exactly one gate.
    e = view_evidence()
    e['before'] = deepcopy(e['before'])
    e['after'] = deepcopy(e['after'])
    e['reopens'] = [deepcopy(r) for r in e['reopens']]
    return e


@pytest.mark.parametrize('update', [True, False])
def test_identical_section_pose_passes_only_with_full_evidence(update):
    e = isolated_view_evidence()
    e['update_return'] = update
    result = assess_view_update(e)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['native_acceptance'] == 'pending' and not result['mutation_performed']


@pytest.mark.parametrize('path,value', [
    (('before', 'state', 'scale'), 2.),
    (('before', 'state', 'source'), '/synthetic/old/model.m3d'),
    (('after', 'state', 'source_sha256'), 'd'*64),
    (('after', 'valid'), False),
    (('after', 'state', 'x'), -120.),
    (('after', 'state', 'matrix'), [0.]*16),
    (('after', 'state', 'bounds'), (0., 0., 0., 1.)),
    (('after', 'state', 'objects'), 0),
    (('after', 'supported_geometry_objects'), 0),
    (('after', 'supported_geometry_objects'), 9),
    (('view_rebuilds',), [{'number': 1, 'succeeded': True}]),
    (('view_rebuilds', 1, 'succeeded'), False),
    (('document_rebuilt',), False),
    (('reopens',), []),
    (('reopens', 1, 'open_id'), 'first'),
    (('reopens', 0, 'read_only'), False),
    (('reopens', 1, 'drawing_sha256'), 'd'*64),
    (('reopens', 1, 'state', 'geometry_digest'), 'd'*64),
    (('reopens', 1, 'state', 'unfold'), True),
    (('requested_pose',), (0., 120., 80.)),
    (('requested_pose',), (1., float('nan'), 80.)),
    (('update_return',), 'False'),
])
def test_view_exception_rejects_each_missing_or_inconsistent_gate(path, value):
    e = isolated_view_evidence()
    parent = e
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert assess_view_update(e)['status'] == 'rejected'


def test_true_update_does_not_bypass_failed_rebuild():
    e = isolated_view_evidence()
    e.update(update_return=True, document_rebuilt=False)
    assert assess_view_update(e)['status'] == 'rejected'


def sheet_evidence():
    history = [{'semantic_key': 'base', 'kind': 'other', 'excluded': False,
                'rolled_back': False, 'valid': True, 'object_error': 0, 'state': 0},
               {'semantic_key': 'bend-variant', 'kind': 'sheet_bend', 'excluded': True,
                'rolled_back': False, 'valid': False, 'object_error': 5, 'state': 2}]
    sheet = {'thickness': 1., 'unfolded': False, 'solid_bodies': 1, 'errors': 0}
    return {'baseline_history': deepcopy(history), 'actual_history': deepcopy(history),
            'baseline_sheet': deepcopy(sheet), 'actual_sheet': deepcopy(sheet)}


def test_excluded_bend_identical_baseline_is_not_a_blanket_geometry_failure():
    assert assess_sheet_history(sheet_evidence())['status'] == 'consistent_offline_evidence'


@pytest.mark.parametrize('path,value', [
    (('actual_history', 0, 'valid'), False),
    (('actual_history', 0, 'object_error'), 1),
    (('actual_history', 1, 'object_error'), 6),
    (('actual_history', 1, 'excluded'), False),
    (('actual_history', 1, 'semantic_key'), 'new-bend'),
    (('actual_history', 1, 'rolled_back'), True),
    (('actual_sheet', 'unfolded'), True),
    (('actual_sheet', 'thickness'), 2.),
    (('actual_sheet', 'solid_bodies'), 2),
    (('actual_sheet', 'errors'), 1),
    (('baseline_history',), []),
])
def test_sheet_exception_requires_exact_history_active_health_and_sheet_state(path, value):
    e = sheet_evidence()
    parent = e
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert assess_sheet_history(e)['status'] == 'rejected'


@pytest.mark.parametrize('field,value', [('kind', 'other'), ('rolled_back', True),
                                         ('semantic_key', 'base')])
def test_even_matching_baseline_cannot_waive_other_inactive_or_ambiguous_history(field, value):
    e = sheet_evidence()
    e['actual_history'][1][field] = value
    e['baseline_history'] = deepcopy(e['actual_history'])
    assert assess_sheet_history(e)['status'] == 'rejected'


def test_matching_bad_active_feature_cannot_be_whitelisted_by_baseline():
    e = sheet_evidence()
    e['actual_history'][0]['object_error'] = 9
    e['baseline_history'] = deepcopy(e['actual_history'])
    assert assess_sheet_history(e)['status'] == 'rejected'


def test_oracles_accept_json_roundtrip_without_loosening_scalar_types():
    e = json.loads(json.dumps(isolated_view_evidence()))
    assert assess_view_update(e)['status'] == 'consistent_offline_evidence'
    e['requested_pose'][0] = True
    assert assess_view_update(e)['status'] == 'rejected'
    sheet = json.loads(json.dumps(sheet_evidence()))
    assert assess_sheet_history(sheet)['status'] == 'consistent_offline_evidence'
