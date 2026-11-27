from copy import deepcopy

import pytest

from kompas_mcp.specification_refresh import current_property_text_plan, verify_property_refresh

STATE = {'context': {'owner': '/synthetic/owner.a3d', 'reference': '41'},
         'rows': {u: {'state': 0, 'edit_source': False, 'sync': False,
                      'geometry': [{'object_id': 'persistent-'+u}], 'draw': i == 0,
                      'is_first': i == 0, 'columns': {'3': str(i+1), '4': 'old', '5': 'old name', '6': '1'}}
                  for i, u in enumerate(['target', 'control'])},
         'properties': {u: {'4': {'value': 'new', 'from_source': True},
                            '5': {'value': 'new name', 'from_source': True}}
                        for u in ['target', 'control']}, 'poses': [[1, 0, 0]]}


def test_stale_property_oracle_declares_only_text_and_explicit_sync_restore():
    initial = deepcopy(STATE)
    result = current_property_text_plan(STATE, ['target'], restore_sync=True)
    assert STATE == initial and not result['saved_acceptance']
    expected = deepcopy(STATE)
    expected['rows']['target']['sync'] = True
    expected['rows']['target']['columns'].update({'4': 'new', '5': 'new name'})
    assert result['expected_after'] == expected
    assert len(result['plans'][0]['cells']) == 2
    actual = deepcopy(expected)
    actual['context']['reference'] = 'another-native-open'
    verify_property_refresh(expected, actual)


def test_explicit_sync_false_policy_refreshes_text_without_changing_sync():
    result = current_property_text_plan(STATE, ['target'], expected_sync=False)
    assert result['plans'][0]['expected_sync'] is False
    assert result['expected_after']['rows']['target']['sync'] is False
    assert result['expected_after']['properties'] == STATE['properties']


def test_display_cache_refresh_is_explicit_and_preserves_persistent_identity():
    state = deepcopy(STATE)
    geometry = {'object_id': 'occ-1', 'metadata_key': 'key-1', 'source': '/synthetic/source.a3d',
                'name': 'old cache', 'marking': 'old cache marking', 'matrix': [1, 0, 0]}
    state['rows']['target']['geometry'] = [geometry]
    for tree in ['top_tree', 'main_tree']:
        state[tree] = [deepcopy(geometry), {'object_id': 'other', 'name': 'control'}]
    result = current_property_text_plan(state, ['target'], expected_sync=False,
                                        normalize_display_metadata=True)
    expected = result['expected_after']
    assert expected['rows']['target']['geometry'][0] == {**geometry, 'name': 'new name', 'marking': 'new'}
    assert expected['top_tree'][1] == state['top_tree'][1]
    assert expected['properties'] == state['properties']
    bad = deepcopy(expected)
    bad['rows']['target']['geometry'][0]['object_id'] = 'new-identity'
    with pytest.raises(ValueError):
        verify_property_refresh(expected, bad)
    state['main_tree'].append(deepcopy(geometry))
    with pytest.raises(ValueError, match='exact singleton'):
        current_property_text_plan(state, ['target'], expected_sync=False,
                                    normalize_display_metadata=True)


@pytest.mark.parametrize('mode', ['current', 'local_property', 'bool_as_source', 'multiple_geometry',
                                 'inherited_row', 'implicit_sync', 'duplicate_uuid'])
def test_false_stale_or_unsafe_property_plan_rejected(mode):
    state, selected, restore = deepcopy(STATE), ['target'], True
    if mode == 'current':
        state['rows']['target']['columns'].update({'4': 'new', '5': 'new name'})
    elif mode == 'local_property':
        state['properties']['target']['4']['from_source'] = False
    elif mode == 'bool_as_source':
        state['properties']['target']['4']['from_source'] = 1
    elif mode == 'multiple_geometry':
        state['rows']['target']['geometry'].append({'object_id': 'parent'})
    elif mode == 'inherited_row':
        state['rows']['target']['state'] = 1
    elif mode == 'implicit_sync':
        restore = False
    elif mode == 'duplicate_uuid':
        selected.append('target')
    with pytest.raises(ValueError):
        current_property_text_plan(state, selected, restore_sync=restore)


@pytest.mark.parametrize('mode', ['hidden_position', 'grouping', 'from_source', 'property_value',
                                 'extra_geometry', 'uuid', 'pose', 'owner'])
def test_saved_full_state_gate_rejects_drift_in_targets_or_controls(mode):
    expected = current_property_text_plan(STATE, ['target'], restore_sync=True)['expected_after']
    actual = deepcopy(expected)
    if mode == 'hidden_position':
        actual['rows']['control']['columns']['3'] = '1'
    elif mode == 'grouping':
        actual['rows']['control']['is_first'] = True
    elif mode == 'from_source':
        actual['properties']['target']['4']['from_source'] = False
    elif mode == 'property_value':
        actual['properties']['control']['5']['value'] = 'unexpected'
    elif mode == 'extra_geometry':
        actual['rows']['target']['geometry'].append({'object_id': 'parent'})
    elif mode == 'uuid':
        actual['rows']['replacement'] = actual['rows'].pop('target')
    elif mode == 'pose':
        actual['poses'][0][2] = 3
    elif mode == 'owner':
        actual['context']['owner'] = '/synthetic/other.a3d'
    with pytest.raises(ValueError):
        verify_property_refresh(expected, actual)
