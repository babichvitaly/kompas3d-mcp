"""Pure translation diagnostics and canonical typed-field identity, never CAD repair."""

import math
from typing import Annotated

from pydantic import Field, StrictBool

from .leader_anchors import Point
from .state_oracles import Evidence, _result
from .typed_position_copy import RowLookup, TypedText
from .view_state import Finite


def canonical_position_identity(row_uuid, typed_text, native_lookup):
    """A new first presentation field cannot override an exact native UUID lookup.

    Getter-only diagnostic. Additional native fields are reported, not deleted,
    accepted as final formatting or repaired through a raw Positions.Str write.
    """
    try:
        text = TypedText.model_validate(typed_text)
        lookup = RowLookup.model_validate(native_lookup)
        if (not isinstance(row_uuid, str) or not row_uuid or not lookup.included_in_row
                or lookup.matched_row_uuids != [row_uuid]):
            raise ValueError('Exact singleton native row lookup is required')
        keys = []
        for line in text.lines:
            for item in line.items:
                if item.item_type == 8192:
                    if item.property_field is None:
                        raise ValueError('Native field lacks typed property metadata')
                    keys.append(item.property_field.key)
                elif item.property_field is not None:
                    raise ValueError('Property metadata attached to a non-field item')
        if keys.count(row_uuid) != 1:
            raise ValueError('Canonical typed position field is absent or duplicated')
    except (TypeError, ValueError) as exc:
        return _result([str(exc)])
    return {**_result([]), 'canonical_row_uuid': row_uuid, 'leader_uuid': lookup.leader_uuid,
            'all_typed_position_keys': keys, 'additional_fields_present': len(keys) > 1,
            'field_cleanup_performed': False, 'final_text_acceptance': False}


class TranslationSnapshot(Evidence):
    tip: Point
    line_endpoints: Annotated[list[Point], Field(min_length=2, max_length=2)]
    to_paper: Annotated[list[Finite], Field(min_length=6, max_length=6)]
    # Explicit measured affine map x'=a*x+b*y+tx, y'=c*x+d*y+ty.
    # Values are already normalized from the declared native parameter mode.


class TranslationEvidence(Evidence):
    before: TranslationSnapshot
    moved: TranslationSnapshot
    source_placement_changed: StrictBool
    same_material_identity_verified: StrictBool
    base_valid: StrictBool  # diagnostics only; never substitutes for measured movement
    constraint_type12_valid: StrictBool
    tolerance: Annotated[Finite, Field(gt=0)]
    minimum_material_displacement: Annotated[Finite, Field(gt=0)]


def _paper(point, affine):
    x, y = point
    a, b, c, d, tx, ty = affine
    return [a*x+b*y+tx, c*x+d*y+ty]


def _delta(after, before):
    return [after[i]-before[i] for i in (0, 1)]


def assess_projected_tip_translation(payload):
    """Distinguish an invalid stimulus from valid material motion with a lagging tip.

    Supports a rigid translated segment, fixed projection basis and measured view
    recentering. Not a general topology/rotation oracle or native acceptance gate.
    """
    base = {'native_acceptance': 'pending', 'dynamics_verified': False,
            'save_reopen_restore_verified': False, 'mutation_performed': False}
    try:
        e = TranslationEvidence.model_validate(payload)
        if (not e.source_placement_changed or not e.same_material_identity_verified
                or e.minimum_material_displacement <= e.tolerance):
            raise ValueError('Independent changed-source/material identity and meaningful bound required')
        a, b = e.before, e.moved
        for state in (a, b):
            m = state.to_paper
            if abs(m[0]*m[3]-m[1]*m[2]) <= 1e-12:
                raise ValueError('Singular coordinate-to-paper map')
        if any(abs(a.to_paper[i]-b.to_paper[i]) > 1e-12 for i in range(4)):
            raise ValueError('This translation-only oracle requires an unchanged linear view basis')
        old = [_paper(p, a.to_paper) for p in a.line_endpoints]
        new = [_paper(p, b.to_paper) for p in b.line_endpoints]
        tip0, tip1 = _paper(a.tip, a.to_paper), _paper(b.tip, b.to_paper)
        if not all(math.isfinite(v) for p in [*old, *new, tip0, tip1] for v in p):
            raise ValueError('Nonfinite transformed coordinates')
        length = math.dist(old[0], old[1])
        if not math.isfinite(length) or length <= e.tolerance:
            raise ValueError('Degenerate baseline material segment')
        vector = _delta(old[1], old[0])
        t = sum((tip0[i]-old[0][i])*(vector[i]/length) for i in (0, 1))/length
        if not math.isfinite(t):
            raise ValueError('Nonfinite baseline material parameter')
        nearest = [old[0][i]+max(0., min(1., t))*vector[i] for i in (0, 1)]
        if math.dist(nearest, tip0) > e.tolerance:
            raise ValueError('Baseline tip was not on the finite material segment')
        pairings = [[_delta(points[i], old[i]) for i in (0, 1)]
                    for points in (new, new[::-1])]
        shifts = min(pairings, key=lambda ds: math.dist(ds[0], ds[1]))
        if not all(math.isfinite(v) for ds in shifts for v in ds):
            raise ValueError('Nonfinite material displacement')
        if math.dist(shifts[0], shifts[1]) > e.tolerance:
            raise ValueError('Material endpoints did not translate rigidly')
        motion, tip_motion = shifts[0], _delta(tip1, tip0)
        if math.hypot(*motion) <= e.minimum_material_displacement:
            raise ValueError('Material displacement is insufficient; stimulus is inconclusive')
        residual = math.dist(motion, tip_motion)
        if not math.isfinite(residual):
            raise ValueError('Nonfinite measured residual')
    except (TypeError, ValueError, OverflowError) as exc:
        return {**base, 'status': 'inconclusive', 'reasons': [str(exc)]}
    return {**base, 'status': 'motion_follows_in_reported_evidence' if residual <= e.tolerance
            else 'motion_does_not_follow', 'paper_material_delta': motion,
            'paper_tip_delta': tip_motion, 'paper_residual': residual,
            'reported_base_valid': e.base_valid,
            'reported_constraint_type12_valid': e.constraint_type12_valid}
