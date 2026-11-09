"""Source-free synthetic receipts, not a reproduction of an engineering model."""

import json
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from kompas_mcp import documents
from kompas_mcp.linked_drawing_oracles import assess_linked_drawing
from kompas_mcp.model_identity import drawing_reference


def receipt():
    view = {'source': '/fixture/source.m3d', 'source_sha256': 'a'*64, 'owner': 'canonical-view',
            'matrix': [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]}
    geometry = [{'native_uuid': f'curve-{i}', 'raw_reference': str(100+i), 'valid': True,
                 'generated': bool(i), 'geometry_digest': str(i+1)*64} for i in range(2)]
    invalid = {'native_uuid': '', 'raw_reference': 'unstable', 'valid': False,
               'generated': True, 'geometry_digest': 'f'*64}
    positions = [{'native_uuid': f'position-{i}', 'specification_object_uuid': f'spec-{i}',
                  'property_key': 'partPropertyByKey:fixture', 'semantic_digest': 'b'*64,
                  'text': str(i+1), 'valid': True} for i in range(2)]
    dimension = {'native_uuid': 'dimension-one', 'endpoints': [
        {'end': end, 'direct': True, 'constraint_valid': True,
         'anchor': {'view': deepcopy(view), 'native_uuid': f'curve-{i}',
                    'lookup_uuid': f'curve-{i}', 'point': [float(i), 0.], 'point_on_curve': True,
                    'valid': True, 'temp': False, 'in_association_view': True,
                    'visible_in_association_view': True, 'is_curve': True,
                    'is_geometry_object': True}}
        for i, end in enumerate(['first', 'second'])]}
    seal = {'owned-drawing': 'c'*64, 'owned-specification': 'd'*64}
    live = deepcopy(positions)
    for p in live:
        p['text'] = '?'
    e = {'expected_view': view, 'expected_positions': positions, 'expected_dimensions': [dimension],
         'baseline_geometry': geometry + [invalid], 'live_positions': live,
         'update_return': False, 'live_changed': False,
         'hashes_before_writeback': {'owned-drawing': 'e'*64, 'owned-specification': 'd'*64},
         'owned_files': list(seal), 'write_steps': ['save_specification', 'rebuild_specification',
                                                 'transmit', 'writeback_complete', 'seal'],
         'sealed_hashes': seal, 'original_hashes_before': {'source': 'a'*64},
         'original_hashes_after': {'source': 'a'*64}, 'association_query_target': 'not_called',
         'association_query_attempts': 0, 'cycles': []}
    for i in range(2):
        e['cycles'].append({'open_id': f'RO-{i}', 'read_only': True,
                            'steps': ['read_saved_specification', 'read_saved_drawing'],
                            'hashes': deepcopy(seal), 'positions': deepcopy(positions),
                            'dimensions': [deepcopy(dimension)], 'geometry': deepcopy(geometry)})
    return e


@pytest.mark.parametrize('update', [True, False])
def test_saved_semantics_allow_live_question_mark_and_changed_false_writeback(update):
    e = receipt()
    e['update_return'] = update
    # Invalid/generated raw refs can change/disappear; valid geometry stays pinned.
    e['cycles'][1]['geometry'].append({'native_uuid': '', 'raw_reference': 'different-invalid',
        'valid': False, 'generated': True, 'geometry_digest': 'e'*64})
    for g in e['cycles'][0]['geometry']:
        g['raw_reference'] = 'new-session-reference'
    result = assess_linked_drawing(json.loads(json.dumps(e)))
    assert result['status'] == 'consistent_offline_evidence'
    assert result['native_acceptance'] == 'pending'
    assert not any(result[key] for key in ['dynamic_renumbering_verified',
                                          'arrow_following_verified', 'package_portability_verified'])


@pytest.mark.parametrize('path,value', [
    (('cycles', 0, 'positions', 0, 'text'), '?'),
    (('cycles', 1, 'positions', 1, 'text'), 'wrong'),
    (('cycles', 0, 'positions', 0, 'native_uuid'), 'other'),
    (('live_positions', 0, 'semantic_digest'), 'e'*64),
    (('live_positions', 0, 'specification_object_uuid'), 'wrong'),
    (('live_positions', 0, 'valid'), False),
    (('cycles', 0, 'steps'), ['read_saved_drawing', 'read_saved_specification']),
    (('write_steps',), ['save_specification', 'rebuild_specification', 'seal',
                        'transmit', 'writeback_complete']),
    (('cycles', 1, 'hashes', 'owned-drawing'), 'e'*64),
    (('original_hashes_after', 'source'), 'b'*64),
    (('owned_files',), ['owned-drawing']),
    (('cycles', 1, 'open_id'), 'RO-0'),
    (('cycles', 0, 'read_only'), False),
    (('cycles',), []),
    (('cycles', 0, 'geometry', 0, 'geometry_digest'), 'e'*64),
    (('cycles', 1, 'geometry', 1, 'geometry_digest'), 'e'*64),  # valid generated curve
    (('cycles', 0, 'geometry', 0, 'native_uuid'), 'other'),
    (('association_query_target',), 'MainTopPart'),
    (('association_query_attempts',), 2),
    (('cycles', 0, 'dimensions', 0, 'endpoints'), []),
    (('update_return',), 'False'),
])
def test_linked_oracle_rejects_individual_missing_saved_proofs(path, value):
    e = receipt()
    parent = e
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert assess_linked_drawing(e)['status'] == 'rejected'


@pytest.mark.parametrize('field,value', [('valid', False), ('temp', True),
    ('in_association_view', False), ('visible_in_association_view', False),
    ('is_curve', False), ('is_geometry_object', False), ('point_on_curve', False),
    ('lookup_uuid', 'different-uuid')])
@pytest.mark.parametrize('end', [0, 1])
def test_both_endpoints_require_actual_associative_geometry_even_if_plan_agrees(field, value, end):
    e = receipt()
    # Mutate both plan and observations: agreement cannot waive anchor predicates.
    e['expected_dimensions'][0]['endpoints'][end]['anchor'][field] = value
    for c in e['cycles']:
        c['dimensions'] = deepcopy(e['expected_dimensions'])
    assert assess_linked_drawing(e)['status'] == 'rejected'


@pytest.mark.parametrize('field,value', [('direct', False), ('constraint_valid', False),
                                        ('end', 'first')])
def test_second_endpoint_cannot_use_indirect_or_duplicate_constraint(field, value):
    e = receipt()
    e['expected_dimensions'][0]['endpoints'][1][field] = value
    for c in e['cycles']:
        c['dimensions'] = deepcopy(e['expected_dimensions'])
    assert assess_linked_drawing(e)['status'] == 'rejected'


@pytest.mark.parametrize('field,value', [('source', '/fixture/other.m3d'),
    ('source_sha256', 'e'*64), ('owner', 'another-view'), ('matrix', [0.]*16),
    ('part_uuid', 'fabricated-part-id')])
def test_canonical_trace_cannot_invent_part_uuid_or_use_wrong_source_matrix_owner(field, value):
    e = receipt()
    e['expected_dimensions'][0]['endpoints'][0]['anchor']['view'][field] = value
    for c in e['cycles']:
        c['dimensions'] = deepcopy(e['expected_dimensions'])
    assert assess_linked_drawing(e)['status'] == 'rejected'


def test_duplicate_valid_uuid_is_not_hidden_by_geometry_filter():
    e = receipt()
    e['baseline_geometry'].append(deepcopy(e['baseline_geometry'][0]))
    assert assess_linked_drawing(e)['status'] == 'rejected'


def test_position_leader_reference_uses_idrawingobject_without_dynamic_fallback(monkeypatch):
    class PositionLeader:
        __slots__ = ()  # typed wrapper has no Reference
    obj = PositionLeader()
    with pytest.raises(AttributeError):
        _ = obj.Reference
    casts = []
    def cast(k, value, interface):
        assert value is obj
        casts.append(interface)
        assert interface == 'IDrawingObject'
        return NS(Reference=73)
    monkeypatch.setattr(documents, '_cast', cast)
    assert drawing_reference(None, obj, 73) == 73
    with pytest.raises(ValueError, match='mutation blocked'):
        drawing_reference(None, obj, 74)
    assert casts == ['IDrawingObject', 'IDrawingObject']
