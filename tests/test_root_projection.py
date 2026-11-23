"""Whole-product scope is not nearest-leaf membership or native speed evidence."""

from copy import deepcopy

import pytest

from kompas_mcp.root_projection import assess_whole_root_projection

MATRIX = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def fixture():
    canonical = {'path': [2], 'model_file': '/owned/main.a3d', 'model_sha256': '9'*64,
                 'component_file': '/owned/product.a3d', 'component_sha256': 'a'*64,
                 'owner_subtree_sha256': 'b'*64, 'instance_sha256': 'c'*64, 'placement': MATRIX}
    target = {**canonical, 'path': [], 'model_file': '/owned/copy/product.a3d',
              'model_sha256': 'a'*64, 'component_file': '/owned/copy/product.a3d'}
    scope = {'mode': 'presentation', 'row_uuid': 'synthetic-row-uuid', 'canonical': canonical,
             'target': target, 'mapping_sha256': 'd'*64,
             'presentation_member': {'path': [2], 'file': '/owned/product.a3d',
                                     'sha256': 'a'*64, 'instance_sha256': 'c'*64,
                                     'owner_subtree_sha256': 'b'*64}}
    pose = {'source_file': target['model_file'], 'source_sha256': 'a'*64,
            'geometry_sha256': 'e'*64, 'matrix': MATRIX, 'x': 0., 'y': 0., 'angle': 0.,
            'scale': 1., 'printable': True, 'visible': True}
    protected = {'drawing_file': '/owned/view.cdw', 'drawing_active': True,
                 'views': {'view-1': pose}, 'layer_printability': {'layer-0': True},
                 'leader_invariants_sha256': 'f'*64, 'document_payload_sha256': '1'*64,
                 'immutable_files': {'/baseline/product.a3d': 'a'*64}}
    plan = {'scope': scope, 'view_key': 'view-1', 'coordinate_mode': -1, 'protected': protected}
    state = {'owner': {'scope': scope, 'canonical_reference': 'canonical-2',
                       'row_geometry_references': ['canonical-2'], 'target_reference': 'root-1',
                       'target_is_special_root': True},
             'protected': protected, 'geometry_document_reference': 'doc-1',
             'geometry_file': target['model_file'], 'current_file_sha256': 'a'*64,
             'loaded_source_sha256': 'a'*64, 'model_revision': 'fresh-model-revision',
             'read_only': True, 'changed': False, 'main_top_reference': 'root-1',
             'main_top_valid': True, 'view_reference': 'view-ref-1',
             'association_view_reference': 'view-ref-1', 'view_number': 1, 'view_valid': True,
             'counts': {'line': 1, 'circle': 1, 'arc': 1}}
    geometries = {'line': [0., 0., 5., 0.], 'circle': [0., 0., 2.],
                  'arc': [0., 0., 2., 2., 0., 0., 2., 0., 90.]}
    candidates = [{'reference': f'{kind}-1', 'kind': kind, 'geometry': values,
                   'direction': True if kind == 'arc' else None,
                   'view_reference': 'view-ref-1', 'coordinate_mode': -1, 'valid': True,
                   'temporary': False, 'visible': True, 'in_association_view': True,
                   'is_curve': True, 'is_geometry': True, 'material_class': 'source_projection',
                   'classification_sha256': '2'*64} for kind, values in geometries.items()]
    # Deliberately detach every reported phase; shared dict aliases are not evidence.
    return {'plan': deepcopy(plan), 'before': deepcopy(state), 'after': deepcopy(state),
            'inventory_epoch': 1, 'harvest_epoch': 2, 'recheck_epoch': 3,
            'association_objects_calls': 0, 'recursive_component_enumerations': 0,
            'candidates': deepcopy(candidates)}


def test_whole_product_copy_sha_equivalence_preserves_arcs_without_membership_claim():
    evidence = fixture()
    result = assess_whole_root_projection(evidence)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['whole_root_evidence_consistent']
    assert result['source_scope'] == 'whole_product_view_only'
    assert result['curves'][2] == evidence['candidates'][2]
    assert result['curves'][2]['kind'] == 'arc' and result['curves'][2]['direction'] is True
    assert not result['component_membership_verified'] and not result['speedup_verified']
    assert not result['nearest_selection_performed'] and not result['mutation_performed']
    assert result['native_acceptance'] == 'pending'


@pytest.mark.parametrize('path,value', [
    (('plan', 'scope', 'target', 'path'), [0]),
    (('plan', 'scope', 'canonical', 'component_sha256'), '3'*64),
    (('plan', 'scope', 'presentation_member', 'path'), [2, 0]),
    (('plan', 'scope', 'target', 'component_file'), '/other/product.a3d'),
    (('plan', 'scope', 'presentation_member'), None),
    (('before', 'geometry_file'), '/wrong/product.a3d'),
    (('before', 'current_file_sha256'), '3'*64),
    (('before', 'loaded_source_sha256'), '3'*64),
    (('before', 'changed'), True), (('before', 'read_only'), False),
    (('before', 'main_top_reference'), 'leaf-0'),
    (('before', 'main_top_valid'), False),
    (('before', 'association_view_reference'), 'foreign-view'),
    (('before', 'view_number'), 0), (('before', 'view_valid'), False),
    (('before', 'owner', 'row_geometry_references'), ['different-canonical-instance']),
    (('before', 'protected', 'views', 'view-1', 'scale'), 0.),
    (('after', 'protected', 'layer_printability', 'layer-0'), False),
    (('after', 'model_revision'), 'new-revision'),
    (('after', 'counts', 'line'), 2),
    (('inventory_epoch',), 2), (('recheck_epoch',), 2),
    (('association_objects_calls',), 1), (('recursive_component_enumerations',), 7),
    (('candidates', 0, 'view_reference'), 'foreign-view'),
    (('candidates', 0, 'material_class'), 'unknown'),
    (('candidates', 0, 'material_class'), 'construction'),
    (('candidates', 2, 'direction'), None),
    (('candidates', 2, 'geometry'), [0., 0., 2.]),  # cannot flatten an arc to a circle
    (('candidates', 0, 'geometry'), [False, 0., 5., 0.]),
])
def test_direct_collection_gate_rejects_wrong_scope_stale_source_and_ambiguous_material(path, value):
    evidence = fixture()
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    # Source/identity negatives exercise the actual gate, not just phase drift.
    if path[0] == 'before':
        evidence['after'] = deepcopy(evidence['before'])
    result = assess_whole_root_projection(evidence)
    assert result['status'] == 'rejected' and not result['whole_root_evidence_consistent']
    assert not result['component_membership_verified'] and not result['speedup_verified']


def test_count_bound_includes_rejected_and_arc_entries_before_native_item_traversal():
    evidence = fixture()
    evidence['plan']['max_curves'] = 2
    evidence['candidates'][0]['temporary'] = True
    result = assess_whole_root_projection(evidence)
    assert result['status'] == 'rejected'
    assert 'preflight bound' in result['reasons'][0]


def test_same_kind_and_cross_kind_duplicate_references_are_never_deduplicated_as_membership():
    evidence = fixture()
    evidence['candidates'][0]['valid'] = False
    evidence['candidates'][1]['reference'] = evidence['candidates'][0]['reference']
    assert assess_whole_root_projection(evidence)['status'] == 'rejected'


def test_missing_raw_entry_is_not_masked_by_accepted_nonempty_geometry():
    evidence = fixture()
    evidence['candidates'].pop()
    assert assess_whole_root_projection(evidence)['status'] == 'rejected'


def test_explicit_crop_exclusion_needs_matching_current_classification():
    evidence = fixture()
    evidence['plan']['excluded'] = {'line-1': 'crop'}
    assert assess_whole_root_projection(evidence)['status'] == 'rejected'
    evidence['candidates'][0]['material_class'] = 'crop'
    result = assess_whole_root_projection(evidence)
    assert result['whole_root_evidence_consistent']
    assert result['rejected_counts'] == {'explicitly_excluded': 1}
    assert {c['reference'] for c in result['curves']} == {'circle-1', 'arc-1'}


def test_empty_or_unknown_exclusion_is_not_a_current_whitelist():
    evidence = fixture()
    evidence['plan']['excluded'] = {'stale-reference': 'construction'}
    assert assess_whole_root_projection(evidence)['status'] == 'rejected'


def test_mode_mismatch_is_counted_and_does_not_change_coordinate_system():
    evidence = fixture()
    evidence['candidates'][0]['coordinate_mode'] = -2
    result = assess_whole_root_projection(evidence)
    assert result['whole_root_evidence_consistent']
    assert result['rejected_counts'] == {'coordinate_mode_mismatch': 1}
    assert {c['kind'] for c in result['curves']} == {'circle', 'arc'}
