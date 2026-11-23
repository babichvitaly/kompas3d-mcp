"""Owned existing-leader binding through an injected, exclusively owned STA adapter.

No COM imports, activation/Current setters, file IO, save/close/rebuild or retries.
All adapter snapshots are detached DTOs. Native acceptance remains separate.
"""

import json
import math
from typing import Annotated, Literal, Protocol

from pydantic import Field, StrictBool, model_validator

from .native_returns import AutomationMethod, normalize_automation_return
from .reference_closure import path_key
from .state_oracles import Evidence, Key, NonnegativeInt, PositiveInt, _result
from .view_state import Finite, Sha256, rotation_matrix

Matrix = Annotated[list[Finite], Field(min_length=16, max_length=16)]
Point = Annotated[list[Finite], Field(min_length=2, max_length=2)]


class OccurrenceIdentity(Evidence):
    """Stable occurrence identity; a file basename or a session ref is insufficient."""

    path: list[NonnegativeInt]
    model_file: Key
    model_sha256: Sha256
    component_file: Key
    component_sha256: Sha256
    owner_subtree_sha256: Sha256
    instance_sha256: Sha256  # semantic instance mapping, not just the file digest
    placement: Matrix

    @model_validator(mode='after')
    def absolute_files(self):
        path_key(self.model_file)
        path_key(self.component_file)
        return self


class SubtreeMember(Evidence):
    path: list[NonnegativeInt]  # exact occurrence path in the canonical model
    file: Key
    sha256: Sha256
    instance_sha256: Sha256  # distinguishes repeated occurrences of identical bytes
    owner_subtree_sha256: Sha256

    @model_validator(mode='after')
    def absolute_file(self):
        path_key(self.file)
        return self


class SemanticScope(Evidence):
    mode: Literal['canonical', 'presentation']
    row_uuid: Key
    canonical: OccurrenceIdentity
    target: OccurrenceIdentity
    mapping_sha256: Sha256  # pinned UUID -> exact occurrence mapping evidence
    presentation_member: SubtreeMember | None = None

    @model_validator(mode='after')
    def canonical_is_exact(self):
        if self.mode == 'canonical' and self.target != self.canonical:
            raise ValueError('Canonical view must target the exact row.Geometry occurrence')
        member = self.presentation_member
        if self.mode == 'canonical' and member is not None:
            raise ValueError('Canonical scope does not use a presentation mapping')
        if self.mode == 'presentation':
            if member is None:
                raise ValueError('Presentation requires exact current canonical subtree membership')
            if (member.path[:len(self.canonical.path)] != self.canonical.path
                    or member.owner_subtree_sha256 != self.canonical.owner_subtree_sha256
                    or member.sha256 != self.target.component_sha256
                    or member.instance_sha256 != self.target.instance_sha256):
                raise ValueError('Presentation target is not the pinned semantic subtree member')
            if member.path == self.canonical.path and (
                    member.file != self.canonical.component_file
                    or member.sha256 != self.canonical.component_sha256):
                raise ValueError('Canonical owner itself must match its exact full file and SHA')
        return self


class OwnerObservation(Evidence):
    scope: SemanticScope
    canonical_reference: Key
    row_geometry_references: list[Key]
    target_reference: Key
    target_is_special_root: StrictBool


def check_owner(expected, actual):
    observed = OwnerObservation.model_validate(actual)
    if observed.scope != expected:
        raise ValueError('Current semantic owner/file/subtree/SHA/occurrence mapping differs')
    if observed.row_geometry_references != [observed.canonical_reference]:
        raise ValueError('UUID row.Geometry is not the exact singleton canonical occurrence')
    if expected.mode == 'canonical' and observed.target_reference != observed.canonical_reference:
        raise ValueError('Canonical target is not the exact row.Geometry object')
    if observed.target_is_special_root != (expected.target.path == []):
        raise ValueError('Special model root must be explicitly identified by its empty path')
    return observed


class ViewPose(Evidence):
    source_file: Key
    source_sha256: Sha256
    geometry_sha256: Sha256  # complete projected material, independent of numeric refs
    matrix: Matrix
    x: Finite
    y: Finite
    angle: Finite
    scale: Annotated[Finite, Field(gt=0)]
    printable: StrictBool
    visible: StrictBool

    @model_validator(mode='after')
    def valid_pose(self):
        path_key(self.source_file)
        rotation_matrix(self.matrix)
        return self


class ProtectedState(Evidence):
    drawing_file: Key
    drawing_active: StrictBool
    views: Annotated[dict[Key, ViewPose], Field(min_length=1)]
    layer_printability: Annotated[dict[Key, StrictBool], Field(min_length=1)]
    leader_invariants_sha256: Sha256  # UUID, typed field, tips, shelf, style; excludes base
    document_payload_sha256: Sha256  # complete protected rows/fields/other annotations
    immutable_files: Annotated[dict[Key, Sha256], Field(min_length=1)]

    @model_validator(mode='after')
    def absolute_files(self):
        path_key(self.drawing_file)
        for file in self.immutable_files:
            path_key(file)
        return self


class Node(Evidence):
    reference: Key
    path: list[NonnegativeInt]
    special_root: StrictBool


class Curve(Evidence):
    reference: Key
    view_key: Key
    coordinate_mode: NonnegativeInt  # native DrawingObjectParamType, same as leader
    kind: Literal['line', 'circle']
    geometry: list[Finite]  # line x1,y1,x2,y2; circle xc,yc,r in explicit view coords
    valid: StrictBool
    temporary: StrictBool
    visible: StrictBool
    in_association_view: StrictBool
    is_curve: StrictBool
    is_geometry: StrictBool

    @model_validator(mode='after')
    def valid_shape(self):
        if self.kind == 'line':
            if len(self.geometry) != 4 or self.geometry[:2] == self.geometry[2:]:
                raise ValueError('Expected a nondegenerate line segment')
        elif len(self.geometry) != 3 or self.geometry[2] <= 0:
            raise ValueError('Expected a circle with positive radius')
        return self


class Limits(Evidence):
    max_nodes: Annotated[PositiveInt, Field(le=100000)] = 5000
    max_depth: Annotated[NonnegativeInt, Field(le=100)] = 40
    max_entries: Annotated[PositiveInt, Field(le=1000000)] = 50000


class AnchorPlan(Evidence):
    kompas_major: Annotated[int, Field(strict=True, ge=25, le=25)]
    scope: SemanticScope
    leader_key: Key  # full stable drawing/view/leader identity, never basename
    leader_reference: Key  # only this live call; never used as a saved identity
    view_key: Key
    coordinate_mode: NonnegativeInt
    branch_index: NonnegativeInt
    segment_index: Annotated[int, Field(strict=True, ge=-1, le=-1)] = -1
    near_point: Point
    max_distance: Annotated[Finite, Field(gt=0)]  # caller chooses coordinate-space bound
    ambiguity_tolerance: Annotated[Finite, Field(gt=0)] = 1e-8
    expected_protected: ProtectedState
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode='after')
    def active_owned_context(self):
        if not self.expected_protected.drawing_active:
            raise ValueError('Existing-object recipe requires an already active owned drawing')
        if self.view_key not in self.expected_protected.views:
            raise ValueError('Explicit owning view missing from complete protected snapshot')
        view = self.expected_protected.views[self.view_key]
        if (view.source_file != self.scope.target.model_file
                or view.source_sha256 != self.scope.target.model_sha256):
            raise ValueError('Owning view source differs from target model identity')
        if self.ambiguity_tolerance >= self.max_distance:
            raise ValueError('Ambiguity tolerance must be smaller than the selection bound')
        return self


class Constraint(Evidence):
    branch_index: NonnegativeInt  # collector must prove branch attribution, not assume point 0
    constraint_type: NonnegativeInt
    valid: StrictBool
    partners: list[Key]


class BaseReadback(Evidence):
    branch_index: NonnegativeInt
    base_reference: Key
    base_valid: StrictBool
    constraints: list[Constraint]


def check_base(readback, branch_index, target_reference):
    b = BaseReadback.model_validate(readback)
    if (b.branch_index != branch_index or not b.base_valid
            or b.base_reference != target_reference):
        raise ValueError('GetBaseObject must be valid and exact for the selected branch')
    constraints = [c for c in b.constraints
                   if c.branch_index == branch_index and c.constraint_type == 12 and c.valid]
    if not constraints:
        raise ValueError('Missing valid branch-attributed association constraint type 12')
    if any(c.partners and target_reference not in c.partners for c in constraints):
        raise ValueError('Explicit constraint Partner contradicts the selected base')
    return {'base': b.model_dump(mode='json'),
            'partner_explicit': any(target_reference in c.partners for c in constraints)}


def _eligible(curve, view_key, coordinate_mode):
    return (curve.view_key == view_key and curve.coordinate_mode == coordinate_mode
            and curve.valid and not curve.temporary
            and curve.visible and curve.in_association_view and curve.is_curve and curve.is_geometry)


def _nearest(curve, point):
    x, y = point
    if curve.kind == 'line':
        x1, y1, x2, y2 = curve.geometry
        t = max(0., min(1., ((x-x1)*(x2-x1)+(y-y1)*(y2-y1))
                        / ((x2-x1)**2+(y2-y1)**2)))
        target = [x1+t*(x2-x1), y1+t*(y2-y1)]
    else:
        xc, yc, r = curve.geometry
        distance = math.hypot(x-xc, y-yc)
        if distance == 0:
            raise ValueError('Circle centre has no unique nearest material point')
        target = [xc+r*(x-xc)/distance, yc+r*(y-yc)/distance]
    distance = math.hypot(x-target[0], y-target[1])
    if not math.isfinite(distance) or not all(math.isfinite(v) for v in target):
        raise ValueError('Nonfinite nearest-point computation')
    return distance, target


def collect_scoped_curves(owner, plan, call):
    """Query inserted nodes only, bounded and deduplicated per operation.

    call is the guarded adapter dispatcher. Iterators must be getter-only and on
    the owning STA. Limits bound consumed nodes/edges/raw entries, not wall time
    of a blocked native call. No cached COM wrappers survive this collection.
    """
    root = Node(reference=owner.target_reference, path=plan.scope.target.path,
                special_root=owner.target_is_special_root)
    pending, nodes, paths = [root], {root.reference: root}, {tuple(root.path): root.reference}
    seen_curves, curves, entries = set(), [], 0

    def consume():
        nonlocal entries
        entries += 1
        if entries > plan.limits.max_entries:
            raise ValueError('Raw traversal/geometry entry bound exceeded; no partial selection')

    while pending:
        node = pending.pop()
        if len(node.path)-len(root.path) > plan.limits.max_depth:
            raise ValueError('Occurrence traversal depth bound exceeded')
        # The special MainTopPart is NEVER passed to AssociationObjects, even
        # when it has no children. Standalone root geometry remains unsupported.
        if not node.special_root:
            for reference in call('association_references', node):
                consume()
                if not isinstance(reference, str) or not reference:
                    raise TypeError('Expected detached IDrawingObject references')
                if reference in seen_curves:
                    continue
                seen_curves.add(reference)
                raw = call('curve_snapshot', reference)
                if raw is None:  # explicitly unsupported primitive; never cast repeatedly
                    continue
                curve = Curve.model_validate(raw)
                if curve.reference != reference:
                    raise ValueError('Curve snapshot reference differs from scoped query')
                if _eligible(curve, plan.view_key, plan.coordinate_mode):
                    curves.append(curve)
        for raw in call('children', node):
            consume()
            child = Node.model_validate(raw)
            if (child.special_root or len(child.path) != len(node.path)+1
                    or child.path[:-1] != node.path):
                raise ValueError('Child is not an inserted occurrence in the authorized subtree')
            if child.reference in nodes:
                if child != nodes[child.reference]:
                    raise ValueError('Aliased/cyclic occurrence reference has conflicting paths')
                continue
            if tuple(child.path) in paths:
                raise ValueError('Occurrence path is ambiguous')
            if len(nodes) >= plan.limits.max_nodes:
                raise ValueError('Occurrence traversal node bound exceeded')
            nodes[child.reference] = child
            paths[tuple(child.path)] = child.reference
            pending.append(child)
    if not curves:
        raise ValueError('No safe visible line/circle in the authorized inserted subtree')
    return curves, {'nodes': len(nodes), 'raw_entries': entries,
                    'unique_geometry_references': len(seen_curves)}


class AnchorAdapter(Protocol):
    """Callbacks must be getter-only except set_base_object/update_leader.

    guard checks fresh identity/path/RO/lease, exclusively owned copy, active
    drawing, model revision and no external mutation. No implicit adoption.
    children/association_references return detached, eager data (not COM proxies).
    resolve_* and reference getters explicitly use IDrawingObject; SetBaseObject
    must receive that typed interface. Never set Current in any callback.
    """

    def guard_owned_document(self): ...
    def protected_snapshot(self): ...
    def semantic_owner(self): ...
    def children(self, node): ...
    def association_references(self, node): ...
    def curve_snapshot(self, reference): ...
    def resolve_drawing_object(self, reference): ...
    def drawing_object_reference(self, obj): ...
    def resolve_leader(self, key): ...
    def set_base_object(self, leader, branch_index, drawing_object, segment_index): ...
    def update_leader(self, leader): ...
    def base_readback(self, leader_key, branch_index): ...


def bind_existing_leader_owned(payload, adapter: AnchorAdapter):
    """Bind one existing branch; preserve uncertain partial failures without retry.

    Success is unsaved structural readback in an injected adapter, not native,
    persisted or dynamic acceptance. Full protected snapshots are compared
    exactly; native collectors must normalize tolerances explicitly upstream.
    """
    result = {'operation': 'bind_existing_leader_owned', 'status': 'failed', 'events': [],
              'raw_mutation_returns': {},
              'mutation_possible': False, 'retry_allowed': False, 'saved': False,
              'native_acceptance': 'pending', 'dynamics_verified': False,
              'persistence_verified': False}
    phase, plan = 'preflight', None
    try:
        plan = AnchorPlan.model_validate(payload).model_copy(deep=True)
        required = ('guard_owned_document', 'protected_snapshot', 'semantic_owner', 'children',
                    'association_references', 'curve_snapshot', 'resolve_drawing_object',
                    'drawing_object_reference', 'resolve_leader', 'set_base_object',
                    'update_leader', 'base_readback')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete anchor adapter')

        def call(name, *args, mutates=False):
            nonlocal phase
            phase = 'guard_before_' + name
            adapter.guard_owned_document()
            phase = name
            if mutates:
                result['mutation_possible'] = True
            value = getattr(adapter, name)(*args)
            result['events'].append(name)
            if mutates:
                result['raw_mutation_returns'][name] = (
                    value if value is None or type(value) in (bool, int, str)
                    else {'unexpected_python_type': type(value).__name__})
            phase = 'guard_after_' + name
            adapter.guard_owned_document()
            return value

        def protected():
            raw = call('protected_snapshot')
            # Preserve even invalid-but-serializable Scale=0 diagnostics.
            result['observed_protected'] = json.loads(json.dumps(raw, allow_nan=False))
            actual = ProtectedState.model_validate(raw)
            if actual != plan.expected_protected:
                raise ValueError('Protected view pose/matrix/printability/payload/source changed')

        protected()
        owner = check_owner(plan.scope, call('semantic_owner'))
        curves, counts = collect_scoped_curves(owner, plan, call)
        scored = sorted([(*_nearest(c, plan.near_point), c) for c in curves], key=lambda r: r[0])
        if scored[0][0] > plan.max_distance:
            raise ValueError('No authorized curve within explicit distance bound')
        if len(scored) > 1 and scored[1][0]-scored[0][0] <= plan.ambiguity_tolerance:
            raise ValueError('Nearest authorized curve is ambiguous; no implicit tie break')
        distance, point, selected = scored[0]
        result.update(selection=selected.model_dump(mode='json'), distance=distance,
                      material_point=point, traversal=counts)
        if check_owner(plan.scope, call('semantic_owner')) != owner:
            raise ValueError('Owner references changed during selection')
        protected()
        if Curve.model_validate(call('curve_snapshot', selected.reference)) != selected:
            raise ValueError('Selected curve changed before mutation')
        target = call('resolve_drawing_object', selected.reference)
        if call('drawing_object_reference', target) != selected.reference:
            raise ValueError('Typed target reference mismatch')
        leader = call('resolve_leader', plan.leader_key)
        if call('drawing_object_reference', leader) != plan.leader_reference:
            raise ValueError('Existing typed leader reference mismatch')
        if check_owner(plan.scope, call('semantic_owner')) != owner:
            raise ValueError('Semantic owner changed while resolving typed objects')
        protected()
        raw = call('set_base_object', leader, plan.branch_index, target,
                   plan.segment_index, mutates=True)
        result['set_base_return'] = normalize_automation_return(AutomationMethod.SET_BASE, raw)
        if not result['set_base_return']['call_completed']:
            raise ValueError('SetBaseObject returned False; no alternate segment/retry')
        raw = call('update_leader', leader, mutates=True)
        result['update_return'] = normalize_automation_return(
            AutomationMethod.UPDATE_DRAWING_OBJECT, raw)
        if not result['update_return']['call_completed']:
            raise ValueError('Own leader Update returned False; no generic waiver')
        del target, leader
        result.update(check_base(call('base_readback', plan.leader_key, plan.branch_index),
                                 plan.branch_index, selected.reference))
        check_owner(plan.scope, call('semantic_owner'))
        protected()
        result['status'] = 'structural_binding_verified_in_adapter'
    except Exception as exc:  # noqa: BLE001 - uncertain native calls must never be replayed
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile the owned unsaved copy; no automatic restore/save/retry')
        if result['mutation_possible'] and plan is not None:
            try:
                protected()
            except Exception as diagnostic:  # noqa: BLE001 - one guarded diagnostic, no mutation
                result['protected_diagnostic_error'] = f'{type(diagnostic).__name__}: {diagnostic}'
    return result


class SavedAnchorObservation(Evidence):
    open_id: Key
    epoch: PositiveInt
    read_only: StrictBool
    drawing_file: Key
    drawing_sha256: Sha256
    owner: OwnerObservation
    protected: ProtectedState
    selected_curve: Curve  # freshly queried from exact owner in THIS reopen
    nodes: list[Node]  # complete bounded traversal, including the selected scope node
    queried_geometry: dict[Key, list[Key]]  # node -> detached AssociationObjects refs
    selected_owner_reference: Key
    base: BaseReadback


class SavedAnchorEvidence(Evidence):
    plan: AnchorPlan
    drawing_file: Key
    save_return: None  # Automation Save(void), never bool(None)
    save_epoch: PositiveInt
    closed_epoch: PositiveInt
    changed_after_save: StrictBool
    sealed_sha256: Sha256
    bound_curve: Curve  # detached curve selected by the successful live binding call
    reopens: Annotated[list[SavedAnchorObservation], Field(min_length=2, max_length=2)]


def assess_saved_leader_anchor(payload):
    """Check persistence evidence only; not proof observations happened in CAD.

    References may change on reopen. Exact base is compared with a newly scoped
    curve in each cycle. Empty Partner is logged, never dynamics acceptance.
    """
    try:
        e = SavedAnchorEvidence.model_validate(payload)
        normalize_automation_return(AutomationMethod.SAVE, e.save_return)
        if path_key(e.drawing_file) != path_key(e.plan.expected_protected.drawing_file):
            raise ValueError('Saved file is not the explicitly planned owned drawing')
        if e.changed_after_save:
            raise ValueError('Save did not clear the changed flag')
        if not e.save_epoch < e.closed_epoch < e.reopens[0].epoch < e.reopens[1].epoch:
            raise ValueError('Save/close/two ordered fresh RO cycles required')
        if len({r.open_id for r in e.reopens}) != 2:
            raise ValueError('Two independent RO opens required')
        partners = []
        if not _eligible(e.bound_curve, e.plan.view_key, e.plan.coordinate_mode):
            raise ValueError('Expected bound curve is not eligible')
        for r in e.reopens:
            owner = check_owner(e.plan.scope, r.owner)
            if (not r.read_only or path_key(r.drawing_file) != path_key(e.drawing_file)
                    or r.drawing_sha256 != e.sealed_sha256):
                raise ValueError('Saved owned file/path/hash/read-only evidence differs')
            if r.protected != e.plan.expected_protected:
                raise ValueError('Saved protected pose/matrix/printability/payload differs')
            root = Node(reference=owner.target_reference, path=e.plan.scope.target.path,
                        special_root=owner.target_is_special_root)
            nodes = {n.reference: n for n in r.nodes}
            paths = {tuple(n.path): n for n in r.nodes}
            if (len(nodes) != len(r.nodes) or len(paths) != len(r.nodes)
                    or nodes.get(root.reference) != root or len(nodes) > e.plan.limits.max_nodes):
                raise ValueError('Incomplete/ambiguous bounded saved occurrence traversal')
            for node in r.nodes:
                if node == root:
                    continue
                if (node.special_root or node.path[:len(root.path)] != root.path
                        or len(node.path) <= len(root.path)
                        or len(node.path)-len(root.path) > e.plan.limits.max_depth
                        or tuple(node.path[:-1]) not in paths):
                    raise ValueError('Saved query node lies outside the authorized subtree')
            if set(r.queried_geometry) != {n.reference for n in r.nodes if not n.special_root}:
                raise ValueError('Saved root query or missing inserted-node query')
            entries = len(r.nodes)-1 + sum(len(refs) for refs in r.queried_geometry.values())
            if entries > e.plan.limits.max_entries:
                raise ValueError('Saved raw traversal bound exceeded')
            if (not _eligible(r.selected_curve, e.plan.view_key, e.plan.coordinate_mode)
                    or r.selected_curve.reference not in r.queried_geometry.get(
                        r.selected_owner_reference, [])
                    or r.selected_curve.kind != e.bound_curve.kind
                    or r.selected_curve.geometry != e.bound_curve.geometry):
                raise ValueError('Reopened target is not safe freshly scoped projected geometry')
            distance, _ = _nearest(r.selected_curve, e.plan.near_point)
            if distance > e.plan.max_distance:
                raise ValueError('Saved tip is outside the selected material bound')
            partners.append(check_base(r.base, e.plan.branch_index,
                                       r.selected_curve.reference)['partner_explicit'])
    except (TypeError, ValueError) as exc:
        return {**_result([str(exc)]), 'persistence_evidence_consistent': False,
                'dynamics_verified': False}
    return {**_result([]), 'persistence_evidence_consistent': True,
            'dynamics_verified': False, 'partner_explicit_per_reopen': partners}
