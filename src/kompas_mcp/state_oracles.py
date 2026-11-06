"""Offline evidence consistency contracts. No native execution or acceptance."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from .view_state import Finite, PositiveInt, Sha256, ViewState

Positive = Annotated[Finite, Field(gt=0)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
Key = Annotated[str, Field(min_length=1)]


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ViewObservation(Evidence):
    state: ViewState
    valid: StrictBool
    supported_geometry_objects: PositiveInt


class Reopen(ViewObservation):
    open_id: Key
    read_only: StrictBool
    drawing_sha256: Sha256


class ViewRebuild(Evidence):
    number: PositiveInt
    succeeded: StrictBool


class ViewEvidence(Evidence):
    update_return: StrictBool
    expected_source: Key  # already resolved canonical path supplied by the native collector
    expected_source_sha256: Sha256
    # Accept JSON arrays as well as Python tuples; numeric/boolean types stay strict.
    requested_pose: Annotated[tuple[Positive, Positive, Positive], Field(strict=False)]
    before: ViewObservation
    after: ViewObservation
    expected_view_numbers: Annotated[list[PositiveInt], Field(min_length=1)]
    view_rebuilds: list[ViewRebuild]
    document_rebuilt: StrictBool
    saved_drawing_sha256: Sha256
    reopens: Annotated[list[Reopen], Field(min_length=2, max_length=2)]


def _result(reasons):
    return {'status': 'rejected' if reasons else 'consistent_offline_evidence',
            'reasons': reasons, 'native_acceptance': 'pending', 'mutation_performed': False}


def assess_view_update(payload):
    """False is eligible only for identical pose/source plus all downstream proof.

    Even True never bypasses rebuild, geometry or two independent RO observations.
    Evidence must be collected by the exclusive native owner; this cannot verify
    that receipt claims actually occurred or replace visual/engineering acceptance.
    """
    try:
        e = ViewEvidence.model_validate(payload)
    except ValidationError as exc:
        return _result([f'invalid_evidence: {exc}'])
    reasons = []
    observations = [e.after, *e.reopens]
    for observation in [e.before, *observations]:
        state = observation.state
        if state.source != e.expected_source or state.source_sha256 != e.expected_source_sha256:
            reasons.append('source_mismatch')
        if not observation.valid or observation.supported_geometry_objects > state.objects:
            reasons.append('invalid_view_or_geometry')
    if not e.update_return:
        before_pose = (e.before.state.scale, e.before.state.x, e.before.state.y)
        if before_pose != e.requested_pose:
            reasons.append('false_update_requires_identical_pose')
    for observation in observations:
        state = observation.state
        if (state.scale, state.x, state.y) != e.requested_pose:
            reasons.append('pose_mismatch')
        if state.model_dump() != e.after.state.model_dump():
            reasons.append('reopen_state_mismatch')
        if observation.supported_geometry_objects != e.after.supported_geometry_objects:
            reasons.append('reopen_geometry_count_mismatch')
    expected = e.expected_view_numbers
    rebuilt = [r.number for r in e.view_rebuilds]
    if (len(set(expected)) != len(expected) or len(set(rebuilt)) != len(rebuilt)
            or set(rebuilt) != set(expected) or e.after.state.number not in expected
            or e.before.state.number != e.after.state.number
            or e.before.state.view_type != e.after.state.view_type
            or not all(r.succeeded for r in e.view_rebuilds) or not e.document_rebuilt):
        reasons.append('incomplete_rebuild_or_view_identity')
    if len({r.open_id for r in e.reopens}) != 2:
        reasons.append('two_independent_reopens_required')
    if any(not r.read_only or r.drawing_sha256 != e.saved_drawing_sha256 for r in e.reopens):
        reasons.append('read_only_or_saved_artifact_mismatch')
    return _result(sorted(set(reasons)))


class HistoryFeature(Evidence):
    semantic_key: Key
    kind: Literal['sheet_bend', 'other']
    excluded: StrictBool
    rolled_back: StrictBool
    valid: StrictBool
    object_error: NonnegativeInt
    state: NonnegativeInt


class SheetState(Evidence):
    thickness: Positive
    unfolded: StrictBool
    solid_bodies: PositiveInt
    errors: NonnegativeInt


class SheetEvidence(Evidence):
    baseline_history: Annotated[list[HistoryFeature], Field(min_length=1)]
    actual_history: Annotated[list[HistoryFeature], Field(min_length=1)]
    baseline_sheet: SheetState
    actual_sheet: SheetState


def assess_sheet_history(payload):
    """Exact pinned history/sheet-state exception for excluded bend features.

    No blanket exclusion waiver, no remapping of changed identities or order.
    This compares observations; it does not establish native body validity.
    """
    try:
        e = SheetEvidence.model_validate(payload)
    except ValidationError as exc:
        return _result([f'invalid_evidence: {exc}'])
    reasons = []
    if e.baseline_history != e.actual_history:
        reasons.append('history_differs_from_baseline')
    if e.baseline_sheet != e.actual_sheet or e.actual_sheet.errors:
        reasons.append('sheet_state_mismatch_or_errors')
    keys = [f.semantic_key for f in e.actual_history]
    if len(keys) != len(set(keys)):
        reasons.append('ambiguous_feature_identity')
    active = [f for f in e.actual_history if not f.excluded and not f.rolled_back]
    if not active or any(not f.valid or f.object_error for f in active):
        reasons.append('active_feature_invalid_or_error')
    if any(f.rolled_back or (f.excluded and f.kind != 'sheet_bend') for f in e.actual_history):
        reasons.append('unsupported_inactive_feature')
    return _result(sorted(set(reasons)))
