"""Synthetic detached DTOs and stateful adapters. Never attach to CAD/VM."""

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass

import pytest

from kompas_mcp.leader_anchors import assess_saved_leader_anchor, bind_existing_leader_owned
from kompas_mcp.native_returns import AutomationMethod, normalize_automation_return

MATRIX = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def plan_fixture():
    occurrence = {'path': [1], 'model_file': '/owned/model.a3d', 'model_sha256': 'a'*64,
                  'component_file': '/owned/parts/item.m3d', 'component_sha256': 'b'*64,
                  'owner_subtree_sha256': 'c'*64, 'instance_sha256': 'd'*64,
                  'placement': MATRIX}
    pose = {'source_file': occurrence['model_file'], 'source_sha256': 'a'*64,
            'geometry_sha256': '6'*64,
            'matrix': MATRIX, 'x': 10., 'y': 20., 'angle': 0., 'scale': 1.,
            'printable': True, 'visible': True}
    protected = {'drawing_file': '/owned/drawing.cdw', 'drawing_active': True,
                 'views': {'view-a': pose, 'view-b': deepcopy(pose)},
                 'layer_printability': {'view-a/layer-0': True, 'view-b/layer-0': False},
                 'leader_invariants_sha256': 'e'*64, 'document_payload_sha256': 'f'*64,
                 'immutable_files': {'/baseline/model.a3d': 'a'*64}}
    return deepcopy({'kompas_major': 25, 'coordinate_mode': -1,
                     'scope': {'mode': 'canonical', 'row_uuid': 'synthetic-row-uuid',
                              'canonical': occurrence, 'target': occurrence,
                              'mapping_sha256': '1'*64},
                     'leader_key': '/owned/drawing.cdw/view-a/leader-uuid',
                     'leader_reference': 'leader-17', 'view_key': 'view-a', 'branch_index': 2,
                     'near_point': [3., 1.], 'max_distance': 4.,
                     'expected_protected': protected})


def curve(reference='curve-1', *, kind='line'):
    return {'reference': reference, 'view_key': 'view-a', 'coordinate_mode': -1, 'kind': kind,
            'geometry': [0., 0., 8., 0.] if kind == 'line' else [0., 0., 2.],
            'valid': True, 'temporary': False, 'visible': True, 'in_association_view': True,
            'is_curve': True, 'is_geometry': True}


def base(reference='curve-1'):
    return {'branch_index': 2, 'base_reference': reference, 'base_valid': True,
            'constraints': [{'branch_index': 2, 'constraint_type': 12,
                             'valid': True, 'partners': []}]}


@dataclass
class TypedDrawingObject:
    reference: str


class FakeAdapter:
    def __init__(self, plan):
        self.plan = deepcopy(plan)
        self.protected = deepcopy(plan['expected_protected'])
        self.owner = {'scope': deepcopy(plan['scope']), 'canonical_reference': 'canonical-1',
                      'row_geometry_references': ['canonical-1'], 'target_reference': 'canonical-1',
                      'target_is_special_root': plan['scope']['target']['path'] == []}
        self.child_map = {}
        self.references = {'canonical-1': ['curve-1']}
        self.curves = {'curve-1': curve()}
        self.readback = base()
        self.calls, self.queries, self.reads = [], [], Counter()
        self.owned, self.setter_result, self.update_result = True, True, True
        self.after_set = self.after_update = None

    def guard_owned_document(self):
        if not self.owned:
            raise RuntimeError('Lease/owned identity lost')

    def protected_snapshot(self):
        return deepcopy(self.protected)

    def semantic_owner(self):
        return deepcopy(self.owner)

    def children(self, node):
        return deepcopy(self.child_map.get(node.reference, []))

    def association_references(self, node):
        assert not node.special_root, 'Forbidden AssociationObjects(MainTopPart)'
        self.queries.append(node.reference)
        return self.references.get(node.reference, [])

    def curve_snapshot(self, reference):
        self.reads[reference] += 1
        return deepcopy(self.curves[reference])

    def resolve_drawing_object(self, reference):
        return TypedDrawingObject(reference)

    def drawing_object_reference(self, obj):
        assert type(obj) is TypedDrawingObject
        return obj.reference

    def resolve_leader(self, key):
        assert key == self.plan['leader_key']
        return TypedDrawingObject(self.plan['leader_reference'])

    def set_base_object(self, leader, branch_index, drawing_object, segment_index):
        assert type(leader) is type(drawing_object) is TypedDrawingObject
        assert leader.reference == self.plan['leader_reference']
        self.calls.append(('set', branch_index, drawing_object.reference, segment_index))
        if self.after_set:
            self.after_set()
        return self.setter_result

    def update_leader(self, leader):
        self.calls.append(('update', leader.reference))
        if self.after_update:
            self.after_update()
        return self.update_result

    def base_readback(self, key, branch):
        return deepcopy(self.readback)


def test_existing_typed_leader_negative_one_and_empty_partner_are_structurally_accepted():
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'structural_binding_verified_in_adapter'
    assert adapter.calls == [('set', 2, 'curve-1', -1), ('update', 'leader-17')]
    assert result['mutation_possible'] and not result['partner_explicit']
    assert not result['saved'] and not result['persistence_verified']
    assert not result['dynamics_verified'] and result['native_acceptance'] == 'pending'
    assert adapter.reads == {'curve-1': 2}  # one collection + one fresh selected read


@pytest.mark.parametrize('kind', ['line', 'circle'])
def test_line_and_circle_selection_in_explicit_view_coordinates(kind):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    adapter.curves['curve-1'] = curve(kind=kind)
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'structural_binding_verified_in_adapter'
    assert result['selection']['kind'] == kind


@pytest.mark.parametrize('segment', [0, 1, -1.0, False, None])
def test_only_explicit_integer_negative_one_recipe_is_supported(segment):
    plan = plan_fixture()
    plan['segment_index'] = segment
    adapter = FakeAdapter(plan)
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert adapter.calls == []


@pytest.mark.parametrize('path,value', [
    (('scope', 'target', 'component_file'), '/another/item.m3d'),  # same basename
    (('scope', 'target', 'path'), [2]),  # repeated instance of same file
    (('scope', 'target', 'component_sha256'), '9'*64),
    (('scope', 'target', 'owner_subtree_sha256'), '9'*64),
    (('scope', 'mapping_sha256'), '9'*64),
    (('row_geometry_references',), ['another-instance']),
    (('row_geometry_references',), ['canonical-1', 'another-instance']),
    (('target_reference',), 'another-instance'),
])
def test_semantic_owner_gate_precedes_any_geometry_query(path, value):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    target = adapter.owner
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed'
    assert not adapter.queries and not adapter.calls


def root_adapter():
    plan = plan_fixture()
    for which in ['canonical', 'target']:
        plan['scope'][which]['path'] = []
    adapter = FakeAdapter(plan)
    child = {'reference': 'insert-0', 'path': [0], 'special_root': False}
    adapter.child_map = {'canonical-1': [child, child]}
    adapter.references = {'insert-0': ['curve-1', 'curve-1', 'curve-2']}
    adapter.curves['curve-2'] = curve('curve-2')
    adapter.curves['curve-2']['geometry'] = [0., 8., 8., 8.]
    return plan, adapter


def test_special_root_is_skipped_children_and_geometry_are_deduplicated():
    plan, adapter = root_adapter()
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'structural_binding_verified_in_adapter'
    assert adapter.queries == ['insert-0']
    assert adapter.reads == {'curve-1': 2, 'curve-2': 1}
    assert result['traversal']['nodes'] == 2


def test_standalone_root_without_inserted_children_has_no_safe_geometry():
    plan, adapter = root_adapter()
    adapter.child_map = {}
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert adapter.queries == []  # never retries unsafe root API


@pytest.mark.parametrize('limits', [
    {'max_nodes': 1}, {'max_depth': 0}, {'max_entries': 1},
])
def test_traversal_bounds_abort_without_partial_selection_or_mutation(limits):
    plan, adapter = root_adapter()
    plan['limits'] = limits
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert not adapter.calls


def test_duplicated_infinite_raw_reference_stream_is_bounded():
    plan = plan_fixture()
    plan['limits'] = {'max_entries': 5}
    adapter = FakeAdapter(plan)

    def forever():
        while True:
            yield 'curve-1'

    adapter.references['canonical-1'] = forever()
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert adapter.reads == {'curve-1': 1}


def test_conflicting_path_reference_or_root_descendant_is_rejected():
    for child in [{'reference': 'canonical-1', 'path': [0], 'special_root': False},
                  {'reference': 'root-again', 'path': [0], 'special_root': True},
                  {'reference': 'outside', 'path': [2, 0], 'special_root': False}]:
        plan, adapter = root_adapter()
        adapter.child_map['canonical-1'] = [child]
        assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']


@pytest.mark.parametrize('key,value', [
    ('view_key', 'other-view'), ('coordinate_mode', -2), ('valid', False),
    ('temporary', True), ('visible', False),
    ('in_association_view', False), ('is_curve', False), ('is_geometry', False),
])
def test_ineligible_projected_curve_is_never_used(key, value):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    adapter.curves['curve-1'][key] = value
    assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']


def test_ambiguous_or_too_distant_or_unsupported_geometry_is_not_guessed():
    plan = plan_fixture()
    for mode in ['ambiguous', 'distant', 'unsupported', 'circle-centre']:
        adapter = FakeAdapter(plan)
        if mode == 'ambiguous':
            adapter.curves['curve-2'] = curve('curve-2')
            adapter.references['canonical-1'].append('curve-2')
        elif mode == 'distant':
            adapter.curves['curve-1']['geometry'] = [0., 80., 8., 80.]
        elif mode == 'unsupported':
            adapter.curves['curve-1'] = None
        else:
            adapter.curves['curve-1'] = curve(kind='circle')
            adapter.curves['curve-1']['geometry'] = [3., 1., 2.]
        assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']


@pytest.mark.parametrize('which,value', [('setter_result', False), ('setter_result', None),
                                        ('update_result', False), ('update_result', None)])
def test_false_or_void_boolean_call_is_not_overruled_by_good_getter(which, value):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    setattr(adapter, which, value)
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and result['mutation_possible']
    assert len([c for c in adapter.calls if c[0] == 'set']) == 1
    assert not result['retry_allowed'] and not result['saved']


def test_mutation_exception_and_ownership_loss_never_retry_or_update():
    for mode in ['exception', 'ownership-loss']:
        plan = plan_fixture()
        adapter = FakeAdapter(plan)

        def break_after_set(mode=mode, adapter=adapter):
            if mode == 'exception':
                raise RuntimeError('Uncertain setter failure after native mutation')
            adapter.owned = False

        adapter.after_set = break_after_set
        result = bind_existing_leader_owned(plan, adapter)
        assert result['status'] == 'failed' and result['mutation_possible']
        assert len(adapter.calls) == 1
        assert not result['retry_allowed']
        if mode == 'ownership-loss':
            assert result['raw_mutation_returns']['set_base_object'] is True


@pytest.mark.parametrize('kind', ['scale-zero', 'matrix', 'printability', 'other-view',
                                 'payload', 'projected-geometry'])
def test_view_or_print_side_effect_is_reported_without_hidden_restore(kind):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)

    def side_effect():
        if kind == 'scale-zero':
            adapter.protected['views']['view-a']['scale'] = 0.
        elif kind == 'matrix':
            adapter.protected['views']['view-a']['matrix'][0] = 0.
        elif kind == 'printability':
            adapter.protected['layer_printability']['view-b/layer-0'] = True
        elif kind == 'other-view':
            adapter.protected['views']['view-b']['x'] += 1.
        elif kind == 'projected-geometry':
            adapter.protected['views']['view-b']['geometry_sha256'] = '0'*64
        else:
            adapter.protected['document_payload_sha256'] = '0'*64

    adapter.after_update = side_effect
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'failed' and result['mutation_possible']
    assert 'protected_diagnostic_error' in result
    assert len(adapter.calls) == 2 and not result['saved']
    assert result['observed_protected'] == adapter.protected


@pytest.mark.parametrize('fault', ['invalid-base', 'wrong-base', 'wrong-branch',
                                  'invalid-constraint', 'wrong-type', 'wrong-partner'])
def test_structural_readback_requires_exact_base_and_branch_constraint(fault):
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    if fault == 'invalid-base':
        adapter.readback['base_valid'] = False
    elif fault == 'wrong-base':
        adapter.readback['base_reference'] = 'other'
    elif fault == 'wrong-branch':
        adapter.readback['constraints'][0]['branch_index'] = 0
    elif fault == 'invalid-constraint':
        adapter.readback['constraints'][0]['valid'] = False
    elif fault == 'wrong-type':
        adapter.readback['constraints'][0]['constraint_type'] = 2
    else:
        adapter.readback['constraints'][0]['partners'] = ['other']
    assert bind_existing_leader_owned(plan, adapter)['status'] == 'failed'


def test_selected_curve_is_refreshed_before_mutation():
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    original = adapter.curve_snapshot

    def stale(reference):
        data = original(reference)
        if adapter.reads[reference] > 1:
            data['geometry'][0] = -1.
        return data

    adapter.curve_snapshot = stale
    assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']


def saved_fixture():
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    reopens = []
    for index in range(2):
        reference = f'regenerated-{index}'
        owner = deepcopy(adapter.owner)
        owner['canonical_reference'] = owner['target_reference'] = f'owner-{index}'
        owner['row_geometry_references'] = [f'owner-{index}']
        reopens.append({'open_id': f'fresh-{index}', 'epoch': index+3, 'read_only': True,
                        'drawing_file': '/owned/drawing.cdw', 'drawing_sha256': '2'*64,
                        'owner': owner, 'protected': deepcopy(adapter.protected),
                        'selected_curve': curve(reference),
                        'selected_owner_reference': f'owner-{index}',
                        'nodes': [{'reference': f'owner-{index}', 'path': [1],
                                   'special_root': False}],
                        'queried_geometry': {f'owner-{index}': [reference]},
                        'base': base(reference)})
    return {'plan': plan, 'drawing_file': '/owned/drawing.cdw', 'save_return': None,
            'save_epoch': 1, 'closed_epoch': 2, 'changed_after_save': False,
            'sealed_sha256': '2'*64, 'bound_curve': curve(), 'reopens': reopens}


def test_void_save_and_regenerated_references_need_separate_saved_ro_evidence():
    result = assess_saved_leader_anchor(saved_fixture())
    assert result['status'] == 'consistent_offline_evidence'
    assert result['persistence_evidence_consistent']
    assert result['partner_explicit_per_reopen'] == [False, False]
    assert not result['dynamics_verified'] and result['native_acceptance'] == 'pending'


@pytest.mark.parametrize('path,value', [
    (('save_return',), False), (('save_return',), True), (('changed_after_save',), True),
    (('changed_after_save',), 0), (('closed_epoch',), 4), (('reopens', 1, 'open_id'), 'fresh-0'),
    (('reopens', 1, 'read_only'), False), (('reopens', 1, 'drawing_sha256'), '3'*64),
    (('reopens', 1, 'drawing_file'), '/different/drawing.cdw'),
    (('reopens', 0, 'owner', 'scope', 'target', 'component_file'), '/wrong/item.m3d'),
    (('reopens', 0, 'protected', 'views', 'view-b', 'printable'), False),
    (('reopens', 0, 'base', 'base_reference'), 'old-stale-reference'),
    (('reopens', 0, 'queried_geometry'), {'wrong-owner': ['regenerated-0']}),
    (('reopens', 0, 'selected_curve', 'geometry'), [0., 0., 7., 0.]),
    (('reopens', 0, 'nodes', 0, 'path'), [2]),
])
def test_saved_contract_rejects_missing_or_conflicting_file_owner_and_state(path, value):
    evidence = saved_fixture()
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert assess_saved_leader_anchor(evidence)['status'] == 'rejected'


def test_save_none_alone_never_proves_persistence():
    normalized = normalize_automation_return(AutomationMethod.SAVE, None)
    assert normalized['call_completed'] and not normalized['persistence_verified']
    assert assess_saved_leader_anchor({'save_return': None})['status'] == 'rejected'


@pytest.mark.parametrize('method', [AutomationMethod.UPDATE_DRAWING_OBJECT,
                                  AutomationMethod.CREATE_CONSTRAINT, AutomationMethod.SET_BASE])
def test_boolean_automation_contract_is_method_specific(method):
    assert normalize_automation_return(method, True)['call_completed']
    assert not normalize_automation_return(method, False)['call_completed']
    for wrong in [None, 0, 1, -1, 'True']:
        with pytest.raises(TypeError):
            normalize_automation_return(method, wrong)


def test_unknown_method_is_not_silently_treated_as_void_or_boolean():
    with pytest.raises(TypeError):
        normalize_automation_return('SomeOther.Create', None)


def presentation_fixture():
    plan = plan_fixture()
    scope = plan['scope']
    scope['mode'] = 'presentation'
    scope['target'] = deepcopy(scope['canonical'])
    scope['target']['path'] = [0, 2]
    scope['target']['model_file'] = '/owned/presentation.a3d'
    scope['target']['model_sha256'] = '7'*64
    scope['target']['component_file'] = '/owned/presentation-parts/item.m3d'
    scope['presentation_member'] = {'path': [1, 3], 'file': '/owned/parts/item.m3d',
                                    'sha256': 'b'*64, 'instance_sha256': 'd'*64,
                                    'owner_subtree_sha256': 'c'*64}
    view = plan['expected_protected']['views']['view-a']
    view['source_file'] = scope['target']['model_file']
    view['source_sha256'] = scope['target']['model_sha256']
    return plan


def test_presentation_requires_current_exact_semantic_subtree_mapping():
    plan = presentation_fixture()
    adapter = FakeAdapter(plan)
    adapter.owner['target_reference'] = 'presentation-instance'
    adapter.references = {'presentation-instance': ['curve-1']}
    result = bind_existing_leader_owned(plan, adapter)
    assert result['status'] == 'structural_binding_verified_in_adapter'
    assert adapter.queries == ['presentation-instance']
    assert not result['dynamics_verified']


@pytest.mark.parametrize('member_key,value', [
    ('path', [2, 3]), ('sha256', '0'*64), ('instance_sha256', '0'*64),
    ('owner_subtree_sha256', '0'*64), ('file', 'item.m3d'),
])
def test_same_bytes_or_basename_never_replace_semantic_occurrence_proof(member_key, value):
    plan = presentation_fixture()
    plan['scope']['presentation_member'][member_key] = value
    adapter = FakeAdapter(plan)
    result = bind_existing_leader_owned(plan, adapter)
    assert not result['mutation_possible'] and not adapter.queries


def test_presentation_without_membership_is_rejected_before_queries():
    plan = presentation_fixture()
    del plan['scope']['presentation_member']
    adapter = FakeAdapter(plan)
    assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']
    assert not adapter.queries


def test_explicit_partner_is_logged_when_it_matches_the_exact_base():
    evidence = saved_fixture()
    for r in evidence['reopens']:
        r['base']['constraints'][0]['partners'] = [r['selected_curve']['reference']]
    result = assess_saved_leader_anchor(evidence)
    assert result['partner_explicit_per_reopen'] == [True, True]
    assert not result['dynamics_verified']


def test_saved_root_guard_requires_inserted_descendant_and_rejects_root_query():
    evidence = saved_fixture()
    for which in ['canonical', 'target']:
        evidence['plan']['scope'][which]['path'] = []
    for i, r in enumerate(evidence['reopens']):
        r['owner']['scope'] = deepcopy(evidence['plan']['scope'])
        r['owner']['target_is_special_root'] = True
        r['nodes'] = [{'reference': f'owner-{i}', 'path': [], 'special_root': True},
                      {'reference': f'child-{i}', 'path': [0], 'special_root': False}]
        r['selected_owner_reference'] = f'child-{i}'
        r['queried_geometry'] = {f'child-{i}': [r['selected_curve']['reference']]}
    assert assess_saved_leader_anchor(evidence)['persistence_evidence_consistent']
    evidence['reopens'][0]['queried_geometry']['owner-0'] = ['regenerated-0']
    assert assess_saved_leader_anchor(evidence)['status'] == 'rejected'


def test_foreign_save_path_cannot_be_accepted_even_if_both_ro_receipts_agree():
    evidence = saved_fixture()
    evidence['drawing_file'] = '/foreign/drawing.cdw'
    for r in evidence['reopens']:
        r['drawing_file'] = evidence['drawing_file']
    assert assess_saved_leader_anchor(evidence)['status'] == 'rejected'


def test_side_effect_during_typed_resolution_stops_before_setter():
    plan = plan_fixture()
    adapter = FakeAdapter(plan)
    original = adapter.resolve_leader

    def resolve(key):
        adapter.protected['views']['view-a']['scale'] = 0.
        return original(key)

    adapter.resolve_leader = resolve
    result = bind_existing_leader_owned(plan, adapter)
    assert not result['mutation_possible'] and not adapter.calls
    assert result['observed_protected']['views']['view-a']['scale'] == 0.


def test_other_native_version_requires_its_own_recipe_acceptance():
    plan = plan_fixture()
    plan['kompas_major'] = 24
    adapter = FakeAdapter(plan)
    assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']


@pytest.mark.parametrize('mode', [-1, -2, -7])
def test_documented_signed_coordinate_modes_require_exact_matching_curve_mode(mode):
    plan = plan_fixture()
    plan['coordinate_mode'] = mode
    adapter = FakeAdapter(plan)
    adapter.curves['curve-1']['coordinate_mode'] = mode
    assert bind_existing_leader_owned(plan, adapter)['status'] == 'structural_binding_verified_in_adapter'


@pytest.mark.parametrize('mode', [0, 1, -3, -1.0, True])
def test_coordinate_mode_is_a_strict_documented_sdk_enum(mode):
    plan = plan_fixture()
    plan['coordinate_mode'] = mode
    adapter = FakeAdapter(plan)
    assert not bind_existing_leader_owned(plan, adapter)['mutation_possible']
