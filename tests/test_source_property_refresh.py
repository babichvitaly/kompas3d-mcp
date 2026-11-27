from copy import deepcopy

import pytest

from kompas_mcp.specification_refresh import (
    source_property_refresh_plan,
    verify_property_refresh,
    verify_source_refresh_progress,
)


def fixture():
    rows, props, tree = {}, {}, []
    for i, u in enumerate(['first', 'hidden', 'control']):
        geometry = {'object_id': u, 'metadata_key': u, 'source': '/synthetic/'+u,
                    'name': 'same name', 'marking': 'old', 'matrix': [1, 0, 0]}
        rows[u] = {'state': 0, 'sync': True, 'edit_source': False, 'draw': i != 1,
                   'is_first': i != 1, 'geometry': [geometry],
                   'columns': {'3': str(i+1), '4': 'old', '5': 'same name', '6': '1'}}
        props[u] = {'4': {'value': 'old', 'from_source': True},
                    '5': {'value': 'same name', 'from_source': True}}
        tree.append(deepcopy(geometry))
    return {'context': {'reference': 'native', 'owner': '/synthetic/owner'}, 'rows': rows,
            'properties': props, 'top_tree': tree, 'main_tree': deepcopy(tree)}


SOURCES = {u: {'4': 'new', '5': 'same name'} for u in ['first', 'hidden']}


def plan():
    return source_property_refresh_plan(fixture(), ['first', 'hidden'], SOURCES, [4],
                                         allow_property_value_refresh=True)


def test_designation_cache_refresh_is_explicit_and_final_grouping_positions_frozen():
    state = fixture()
    with pytest.raises(ValueError, match='cache change not declared'):
        source_property_refresh_plan(state, ['first', 'hidden'], SOURCES, [4])
    p = plan()
    assert len(p['declared_property_cache_changes']) == 2
    final = p['expected_after']
    assert final['properties']['hidden']['4'] == {'value': 'new', 'from_source': True}
    assert final['rows']['hidden']['columns']['3'] == '2'
    assert final['rows']['hidden']['is_first'] is False
    assert final['rows']['control'] == state['rows']['control']
    assert final['rows']['hidden']['geometry'][0]['object_id'] == 'hidden'


def test_intermediate_group_split_may_be_observed_but_is_not_final_acceptance():
    p = plan()
    partial = deepcopy(p['before'])
    for key in ['rows', 'properties']:
        partial[key]['first'] = deepcopy(p['expected_after'][key]['first'])
    for tree in ['top_tree', 'main_tree']:
        partial[tree][0] = deepcopy(p['expected_after'][tree][0])
    partial['rows']['hidden']['draw'] = partial['rows']['hidden']['is_first'] = True
    partial['rows']['hidden']['columns']['3'] = 'temporary native position'
    verify_source_refresh_progress(p, partial)
    with pytest.raises(ValueError):
        verify_property_refresh(p['expected_after'], partial)
    verify_property_refresh(p['expected_after'], p['expected_after'])


@pytest.mark.parametrize('mode', ['source_flag', 'control_position', 'extra_parent', 'new_uuid',
                                 'pose', 'foreign_value', 'source_path', 'other_property'])
def test_partial_batch_never_waives_identity_inheritance_controls_or_other_fields(mode):
    p = plan()
    actual = deepcopy(p['before'])
    if mode == 'source_flag':
        actual['properties']['first']['4']['from_source'] = False
    elif mode == 'control_position':
        actual['rows']['control']['columns']['3'] = '9'
    elif mode == 'extra_parent':
        actual['rows']['first']['geometry'].append({'object_id': 'parent'})
    elif mode == 'new_uuid':
        actual['rows']['another'] = actual['rows'].pop('hidden')
    elif mode == 'pose':
        actual['rows']['first']['geometry'][0]['matrix'][2] = 3
    elif mode == 'foreign_value':
        actual['rows']['first']['columns']['4'] = 'unplanned'
    elif mode == 'source_path':
        actual['rows']['hidden']['geometry'][0]['source'] = '/synthetic/wrong'
    elif mode == 'other_property':
        actual['properties']['hidden']['5']['value'] = 'not the current source'
    with pytest.raises((ValueError, KeyError)):
        verify_source_refresh_progress(p, actual)


@pytest.mark.parametrize('mode', ['hidden_position', 'first_swapped', 'quantity'])
def test_final_gate_rejects_preservation_failures_even_after_text_is_correct(mode):
    p = plan()
    actual = deepcopy(p['expected_after'])
    if mode == 'hidden_position':
        actual['rows']['hidden']['columns']['3'] = '1'
    elif mode == 'first_swapped':
        actual['rows']['first']['is_first'], actual['rows']['hidden']['is_first'] = False, True
    else:
        actual['rows']['hidden']['columns']['6'] = '2'
    with pytest.raises(ValueError):
        verify_property_refresh(p['expected_after'], actual)
