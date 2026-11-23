"""Counterexamples to base/type12 truthiness, first-UUID parsing and local-only deltas."""

from copy import deepcopy

import pytest

from kompas_mcp.leader_motion import (
    assess_projected_tip_translation,
    canonical_position_identity,
)


def motion_fixture():
    return {'before': {'tip': [2., 0.], 'line_endpoints': [[0., 0.], [4., 0.]],
                       'to_paper': [2., 0., 0., 2., 10., 20.]},
            'moved': {'tip': [-1., -1.], 'line_endpoints': [[-3., -1.], [1., -1.]],
                      'to_paper': [2., 0., 0., 2., 10., 21.]},
            'source_placement_changed': True, 'same_material_identity_verified': True,
            'base_valid': True, 'constraint_type12_valid': True,
            'tolerance': 1e-6, 'minimum_material_displacement': .1}


def test_real_projected_motion_with_stationary_local_tip_fails_despite_valid_base_and_type12():
    evidence = motion_fixture()
    evidence['moved']['tip'] = deepcopy(evidence['before']['tip'])
    result = assess_projected_tip_translation(evidence)
    assert result['status'] == 'motion_does_not_follow'
    assert result['paper_material_delta'] == [-6., -1.]
    assert result['paper_tip_delta'] == [0., 1.]  # view recentering is not tip following
    assert result['reported_base_valid'] and result['reported_constraint_type12_valid']
    assert not result['dynamics_verified']


def test_equal_two_axis_displacement_is_only_reported_motion_not_native_acceptance():
    result = assess_projected_tip_translation(motion_fixture())
    assert result['status'] == 'motion_follows_in_reported_evidence'
    assert result['paper_material_delta'] == result['paper_tip_delta'] == [-6., -1.]
    assert result['paper_residual'] == 0.
    assert not result['dynamics_verified'] and not result['save_reopen_restore_verified']
    assert result['native_acceptance'] == 'pending'


def test_point_sliding_along_the_same_infinite_line_does_not_pass_translation_gate():
    evidence = motion_fixture()
    evidence['moved']['tip'] = [0., -1.]  # still on moved finite segment, wrong material location
    assert assess_projected_tip_translation(evidence)['status'] == 'motion_does_not_follow'


def test_reversed_line_endpoint_order_does_not_look_like_a_different_displacement():
    evidence = motion_fixture()
    evidence['moved']['line_endpoints'].reverse()
    assert assess_projected_tip_translation(evidence)['status'] == 'motion_follows_in_reported_evidence'


@pytest.mark.parametrize('fault', ['no-material-motion', 'no-source-change', 'wrong-identity',
                                  'deformation', 'singular-map', 'scale-change',
                                  'off-segment-baseline', 'degenerate-baseline', 'nonfinite'])
def test_invalid_or_unsupported_stimulus_is_inconclusive_not_a_failed_native_anchor(fault):
    e = motion_fixture()
    if fault == 'no-material-motion':
        e['moved'] = deepcopy(e['before'])
    elif fault == 'no-source-change':
        e['source_placement_changed'] = False
    elif fault == 'wrong-identity':
        e['same_material_identity_verified'] = False
    elif fault == 'deformation':
        e['moved']['line_endpoints'][0][0] -= 1.
    elif fault == 'singular-map':
        e['moved']['to_paper'][3] = 0.
    elif fault == 'scale-change':
        e['moved']['to_paper'][3] = 3.
    elif fault == 'off-segment-baseline':
        e['before']['tip'] = [8., 0.]
    elif fault == 'degenerate-baseline':
        e['before']['line_endpoints'][1] = [0., 0.]
    else:
        e['moved']['tip'][0] = float('nan')
    result = assess_projected_tip_translation(e)
    assert result['status'] == 'inconclusive' and not result['dynamics_verified']


CANONICAL = '00000000-0000-0000-0000-000000000001'
PRESENTATION = '00000000-0000-0000-0000-000000000002'


def field(key):
    return {'item_type': 8192, 'properties': {},
            'property_field': {'key': key, 'prop': 'position', 'type': 'partPropertyByKey'}}


def text_fixture():
    text = {'properties': {}, 'lines': [
        {'properties': {}, 'items': [field(PRESENTATION)]},
        {'properties': {}, 'items': [field(CANONICAL)]}]}
    lookup = {'leader_uuid': 'leader-native-uuid', 'matched_row_uuids': [CANONICAL],
              'included_in_row': True}
    return text, lookup


def test_canonical_second_typed_line_and_direct_native_lookup_override_first_field_order():
    text, lookup = text_fixture()
    before = deepcopy(text)
    result = canonical_position_identity(CANONICAL, text, lookup)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['canonical_row_uuid'] == CANONICAL
    assert result['all_typed_position_keys'] == [PRESENTATION, CANONICAL]
    assert result['additional_fields_present'] and not result['field_cleanup_performed']
    assert not result['final_text_acceptance'] and text == before


@pytest.mark.parametrize('fault', ['first-field-lookup', 'ambiguous-lookup', 'not-included',
                                  'missing-canonical', 'duplicate-canonical', 'missing-metadata'])
def test_typed_field_presence_alone_never_substitutes_for_canonical_native_binding(fault):
    text, lookup = text_fixture()
    if fault == 'first-field-lookup':
        lookup['matched_row_uuids'] = [PRESENTATION]
    elif fault == 'ambiguous-lookup':
        lookup['matched_row_uuids'] += [PRESENTATION]
    elif fault == 'not-included':
        lookup['included_in_row'] = False
    elif fault == 'missing-canonical':
        text['lines'].pop()
    elif fault == 'duplicate-canonical':
        text['lines'].append(deepcopy(text['lines'][1]))
    else:
        text['lines'][1]['items'][0]['property_field'] = None
    assert canonical_position_identity(CANONICAL, text, lookup)['status'] == 'rejected'
