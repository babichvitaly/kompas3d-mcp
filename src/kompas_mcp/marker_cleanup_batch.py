"""Classify all explicit Local-cut marker scopes before any deletion; two snapshots."""

import math
from typing import Annotated

from pydantic import Field, JsonValue, StrictBool, TypeAdapter, model_validator

from .state_oracles import Evidence, Key, PositiveInt
from .view_state import Finite, Sha256, rotation_matrix


class CutFrame(Evidence):
    view_key: Key
    reference: Key
    source: Key
    source_sha256: Sha256
    matrix: Annotated[list[Finite], Field(min_length=16, max_length=16)]
    scale: Annotated[Finite, Field(gt=0)]
    x: Finite
    y: Finite
    angle: Finite
    local: StrictBool
    base_cut_reference: Key
    paper_crop_center: Annotated[list[Finite], Field(min_length=2, max_length=2)]
    paper_crop_radius: Annotated[Finite, Field(gt=0)]

    @model_validator(mode='after')
    def matrix_valid(self):
        rotation_matrix(self.matrix)
        if not self.local:
            raise ValueError('Only explicitly captured Local circular sections supported')
        return self


class Base(Evidence):
    reference: Key
    drawing_type: PositiveInt
    valid: StrictBool


class Marker(Evidence):
    reference: Key
    owner_view_key: Key
    drawing_type: PositiveInt
    valid: StrictBool
    temp: StrictBool
    associated: StrictBool
    bounds: Annotated[list[Finite], Field(min_length=4, max_length=4)]
    base: Base | None
    properties: dict[Key, JsonValue]  # full agreed native marker getter scope


class ProtectedSnapshot(Evidence):
    fingerprint: Sha256  # all protected material/axes/text/cuts; excludes deletable markers
    references: list[Key]
    frames: dict[Key, CutFrame]


def cleanup_local_marker_batch(adapter, frames, centre_marker_type, invalid_line_type,
                               max_markers=200, margin=.1):
    """No CAD connection, implicit scope expansion, save, rollback or retry.

    Native adapter must provide exact document/process/source ownership and fresh
    marker resolution. This bounded circular-crop classification is intentionally
    conservative: unknown outside markers abort the entire whitelist before Delete.
    """
    result = {'status': 'failed', 'deleted': [], 'attempted_deletions': [], 'snapshot_reads': 0, 'mutation_possible': False,
              'retry_allowed': False, 'saved': False, 'native_acceptance': 'pending'}
    phase, before, after_attempted = 'preflight', None, False
    try:
        expected = [CutFrame.model_validate(f).model_copy(deep=True) for f in frames]
        keys = tuple(f.view_key for f in expected)
        if not expected or len(expected) > 64 or len(keys) != len(set(keys)):
            raise ValueError('Explicit unique bounded Local-cut scope required')
        for value in (centre_marker_type, invalid_line_type, max_markers):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError('Positive installed type constants and inspection bound required')
        if max_markers > 5000 or isinstance(margin, bool) or not math.isfinite(margin) or margin < 0:
            raise ValueError('Invalid finite inspection/margin bound')
        frame_map = {f.view_key: f for f in expected}
        required = ('guard_owned_scope', 'protected_snapshot', 'list_markers', 'read_marker',
                    'read_cut_frame', 'delete_marker', 'marker_valid')
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete explicit marker adapter')

        def guard():
            adapter.guard_owned_scope(keys)

        def snapshot():
            guard()
            result['snapshot_reads'] += 1
            value = ProtectedSnapshot.model_validate(adapter.protected_snapshot()).model_copy(deep=True)
            if value.frames != frame_map or len(value.references) != len(set(value.references)):
                raise ValueError('Captured Local frame/lineage or protected reference scope differs')
            return value

        def list_markers(key):
            guard()
            values = TypeAdapter(list[Marker]).validate_python(adapter.list_markers(key, max_markers))
            if len(values) > max_markers:
                raise ValueError('Marker enumeration bound exceeded')
            return values

        phase = 'protected_before'
        before = snapshot()
        prepared, retained, seen = [], {key: [] for key in keys}, set()
        phase = 'classify_all_scopes'
        for frame in expected:
            for marker in list_markers(frame.view_key):
                if (marker.reference in seen or marker.reference in before.references
                        or marker.owner_view_key != frame.view_key or not marker.valid or marker.temp
                        or marker.drawing_type != centre_marker_type):
                    raise ValueError('Aliased/foreign/invalid marker is not disposable')
                seen.add(marker.reference)
                x1, y1, x2, y2 = marker.bounds
                if x2 <= x1 or y2 <= y1:
                    raise ValueError('Invalid marker bounds')
                centre = [(x1+x2)/2, (y1+y2)/2]
                outside = math.dist(centre, frame.paper_crop_center) > frame.paper_crop_radius + margin
                if not outside or (marker.base is not None and marker.base.valid):
                    retained[frame.view_key].append(marker)
                elif (marker.base is not None and not marker.base.valid
                      and marker.base.drawing_type == invalid_line_type and not marker.associated):
                    prepared.append(marker)
                else:
                    raise ValueError('Unclassified outside marker: no deletion may begin')

        def finish():
            nonlocal after_attempted, phase
            after_attempted = True
            phase = 'protected_after'
            after = snapshot()
            if after != before:
                raise ValueError('Protected geometry/axes/text/cuts/pose changed')
            for key in keys:
                actual = list_markers(key)
                if sorted(actual, key=lambda m: m.reference) != sorted(retained[key], key=lambda m: m.reference):
                    raise ValueError('Retained markers changed or orphan remains')
            guard()

        for marker in reversed(prepared):
            phase = 'revalidate_before_delete'
            guard()
            frame = CutFrame.model_validate(adapter.read_cut_frame(marker.owner_view_key))
            current = Marker.model_validate(adapter.read_marker(marker.reference))
            if frame != frame_map[marker.owner_view_key] or current != marker:
                raise ValueError('Whitelisted marker or Local frame changed before Delete')
            phase = 'delete_marker'
            result['mutation_possible'] = True
            result['attempted_deletions'].append(marker.reference)
            if adapter.delete_marker(marker.reference) is not True or adapter.marker_valid(marker.reference):
                raise ValueError('Delete not confirmed or marker still valid')
            result['deleted'].append(marker.reference)
        finish()
        result['status'] = 'marker_batch_verified_in_adapter'
    except Exception as exc:  # noqa: BLE001 - retain partial deletes, never replay
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}')
        if before is not None and not after_attempted and result['mutation_possible']:
            try:
                finish()
            except Exception as diagnostic:  # noqa: BLE001
                result['exit_check_error'] = str(diagnostic)
        result['recovery'] = 'Reconcile the explicit owned partial batch; no automatic delete retry'
    return result
