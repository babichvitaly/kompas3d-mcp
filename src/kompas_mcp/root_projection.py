"""Offline whole-product view-collection evidence. No native calls or fast-path switch.

This deliberately cannot establish per-component AssociationObjects membership.
Collectors and any integration with leader binding need native acceptance first.
"""

from collections import Counter
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from .leader_anchors import OwnerObservation, ProtectedState, SemanticScope, check_owner
from .reference_closure import path_key
from .state_oracles import Evidence, Key, NonnegativeInt, PositiveInt, _result
from .view_state import Finite, Sha256

Kind = Literal['line', 'circle', 'arc']
Classification = Literal['source_projection', 'crop', 'construction', 'unknown']


class RootProjectionPlan(Evidence):
    scope: SemanticScope
    view_key: Key
    coordinate_mode: NonnegativeInt
    protected: ProtectedState
    max_curves: Annotated[PositiveInt, Field(le=20000)] = 20000
    excluded: dict[Key, Literal['crop', 'construction']] = Field(default_factory=dict)

    @model_validator(mode='after')
    def whole_product_only(self):
        s = self.scope
        if s.target.path:
            raise ValueError('Direct view collections require the exact whole-model root')
        if (path_key(s.target.component_file) != path_key(s.target.model_file)
                or s.target.component_sha256 != s.target.model_sha256
                or s.canonical.component_sha256 != s.target.model_sha256):
            raise ValueError('Whole view source must equal the canonical complete product file/SHA')
        if s.mode == 'presentation' and s.presentation_member.path != s.canonical.path:
            raise ValueError('A canonical owner descendant is not the whole canonical product')
        if self.view_key not in self.protected.views:
            raise ValueError('Expected owning view missing')
        v = self.protected.views[self.view_key]
        if (path_key(v.source_file) != path_key(s.target.model_file)
                or v.source_sha256 != s.target.model_sha256):
            raise ValueError('Pinned view source differs from the whole-product model')
        if len(self.excluded) > self.max_curves:
            raise ValueError('Excluded-reference bound exceeded')
        return self


class CollectionCounts(Evidence):
    line: NonnegativeInt
    circle: NonnegativeInt
    arc: NonnegativeInt


class RootProjectionState(Evidence):
    owner: OwnerObservation
    protected: ProtectedState
    geometry_document_reference: Key
    geometry_file: Key
    current_file_sha256: Sha256
    loaded_source_sha256: Sha256  # collector proves loaded model is this revision, not just disk SHA
    model_revision: Key
    read_only: StrictBool
    changed: StrictBool
    main_top_reference: Key
    main_top_valid: StrictBool
    view_reference: Key
    association_view_reference: Key
    view_number: PositiveInt  # excludes system view 0
    view_valid: StrictBool
    counts: CollectionCounts


class RootCurve(Evidence):
    reference: Key
    kind: Kind
    geometry: list[Finite]
    # line: x1,y1,x2,y2; circle: xc,yc,r;
    # arc: xc,yc,r,x1,y1,x2,y2,Angle1,Angle2 (native units retained)
    direction: StrictBool | None = None
    view_reference: Key
    coordinate_mode: NonnegativeInt
    valid: StrictBool
    temporary: StrictBool
    visible: StrictBool
    in_association_view: StrictBool
    is_curve: StrictBool
    is_geometry: StrictBool
    material_class: Classification
    classification_sha256: Sha256  # explicit independent native lineage/classification evidence

    @model_validator(mode='after')
    def real_geometry(self):
        if len(self.geometry) != {'line': 4, 'circle': 3, 'arc': 9}[self.kind]:
            raise ValueError('Typed primitive geometry has the wrong shape')
        if self.kind == 'line' and self.geometry[:2] == self.geometry[2:]:
            raise ValueError('Degenerate line')
        if self.kind != 'line' and self.geometry[2] <= 0:
            raise ValueError('Nonpositive radius')
        if (self.kind == 'arc') != (self.direction is not None):
            raise ValueError('Arc must retain native direction; line/circle must not invent it')
        return self


class RootProjectionEvidence(Evidence):
    plan: RootProjectionPlan
    before: RootProjectionState
    after: RootProjectionState
    inventory_epoch: PositiveInt
    harvest_epoch: PositiveInt
    recheck_epoch: PositiveInt
    association_objects_calls: NonnegativeInt
    recursive_component_enumerations: NonnegativeInt
    candidates: list[RootCurve]  # ALL raw entries from all 3 collections, before filtering


def assess_whole_root_projection(payload):
    """Evaluate a future collector's detached data, preserving arcs without selection.

    Counts must have been checked before native item reads, and raw rejected
    entries must remain in candidates. This evaluator verifies reported evidence,
    not the truth/freshness/completeness of native reads. No speedup is established.
    """
    try:
        e = RootProjectionEvidence.model_validate(payload)
        p = e.plan
        if not e.inventory_epoch < e.harvest_epoch < e.recheck_epoch:
            raise ValueError('Bounded inventory must precede item harvest and final recheck')
        if e.association_objects_calls or e.recursive_component_enumerations:
            raise ValueError('Whole-root fast strategy must not query root/children associations')
        if e.before != e.after:
            raise ValueError('Source/root/view/pose/printability/counts drifted during collection')
        state = e.before
        owner = check_owner(p.scope, state.owner)
        if (not owner.target_is_special_root or not state.main_top_valid
                or state.main_top_reference != owner.target_reference
                or not state.view_valid
                or state.view_reference != state.association_view_reference):
            raise ValueError('Exact MainTopPart/association/owning view identity not proved')
        if (state.protected != p.protected
                or path_key(state.geometry_file) != path_key(p.scope.target.model_file)
                or state.current_file_sha256 != p.scope.target.model_sha256
                or state.loaded_source_sha256 != p.scope.target.model_sha256
                or not state.read_only or state.changed):
            raise ValueError('Exact current clean RO whole-product source not proved')
        counts = state.counts.model_dump()
        if sum(counts.values()) > p.max_curves:
            raise ValueError('Raw total of all three collections exceeds the preflight bound')
        actual = Counter(c.kind for c in e.candidates)
        if any(actual[k] != counts[k] for k in counts):
            raise ValueError('Incomplete raw typed-collection harvest')
        refs = {c.reference for c in e.candidates}
        if len(refs) != len(e.candidates):
            raise ValueError('Duplicate reference within/across native typed collections')
        if not set(p.excluded) <= refs:
            raise ValueError('Excluded reference absent from this fresh collection')
        accepted, rejected = [], Counter()
        for curve in e.candidates:
            if curve.reference in p.excluded:
                if curve.material_class != p.excluded[curve.reference]:
                    raise ValueError('Explicit exclusion contradicts current classification')
                rejected['explicitly_excluded'] += 1
                continue
            if (not curve.valid or curve.temporary or not curve.visible
                    or not curve.in_association_view or not curve.is_curve or not curve.is_geometry):
                rejected['not_visible_projected_material'] += 1
                continue
            if curve.view_reference != state.view_reference:
                raise ValueError('Foreign owning view returned by native curve collection')
            if curve.coordinate_mode != p.coordinate_mode:
                rejected['coordinate_mode_mismatch'] += 1
                continue
            if curve.material_class != 'source_projection':
                raise ValueError('Projection flags alone cannot distinguish material/crop/construction')
            accepted.append(curve.model_dump(mode='json'))
        if not accepted:
            raise ValueError('No safe whole-product projected material')
    except (TypeError, ValueError) as exc:
        return {**_result([str(exc)]), 'whole_root_evidence_consistent': False,
                'component_membership_verified': False, 'speedup_verified': False}
    return {**_result([]), 'whole_root_evidence_consistent': True,
            'source_scope': 'whole_product_view_only', 'curves': accepted,
            'raw_counts': counts, 'rejected_counts': dict(rejected),
            'component_membership_verified': False, 'nearest_selection_performed': False,
            'dynamics_verified': False, 'speedup_verified': False}
