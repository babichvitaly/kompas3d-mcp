"""Read-only associative view state and visible anchors on the existing STA.

No activation, update, rebuild, save, implicit pose repair or COM references in
results. A source-file hash is disk provenance, not proof of regenerated geometry.
"""

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .documents import _cast, _document

Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class ViewState(BaseModel):
    """Serializable comparison contract; references are deliberately session-local."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["view-state/1"] = "view-state/1"
    number: PositiveInt
    view_type: PositiveInt
    source: Annotated[str, Field(min_length=1)]
    source_sha256: Sha256
    matrix: Annotated[list[Finite], Field(min_length=16, max_length=16)]
    scale: Annotated[Finite, Field(gt=0)]
    x: Finite
    y: Finite
    angle: Finite
    bounds: tuple[Finite, Finite, Finite, Finite]
    objects: PositiveInt
    unfold: StrictBool
    geometry_digest: Sha256

    @model_validator(mode="after")
    def valid_geometry(self):
        rotation_matrix(self.matrix)
        if self.bounds[2] <= self.bounds[0] or self.bounds[3] <= self.bounds[1]:
            raise ValueError("Native view bounds must have positive width and height")
        return self


def rotation_matrix(values):
    """Accepted convention: screen vector q = M @ source vector p."""
    result = list(values)
    if len(result) != 16 or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                or not math.isfinite(x) for x in result):
        raise ValueError("Expected a finite 4x4 rotation matrix")
    result = [float(x) for x in result]
    if any(abs(result[i]) > 1e-10 for i in (3, 7, 11, 12, 13, 14)) or abs(result[15]-1) > 1e-10:
        raise ValueError("Projection matrix must have zero translation")
    rows = [result[i*4:i*4+3] for i in range(3)]
    for i in range(3):
        for j in range(3):
            if abs(sum(rows[i][k]*rows[j][k] for k in range(3))-(1 if i == j else 0)) > 1e-8:
                raise ValueError("Projection basis must be orthonormal")
    det = sum(rows[0][i] * (rows[1][(i+1)%3]*rows[2][(i+2)%3]
                          - rows[1][(i+2)%3]*rows[2][(i+1)%3]) for i in range(3))
    if abs(det-1) > 1e-8:
        raise ValueError("Projection basis must be right-handed")
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _hash_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _path_key(path):
    return os.path.normcase(os.path.realpath(path))


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Native view returned a non-finite numeric value")
    return float(value)


def _limit(max_objects):
    if isinstance(max_objects, bool) or not isinstance(max_objects, int) or not 1 <= max_objects <= 200000:
        raise ValueError("max_objects must be 1..200000")


def _view(k, handle, number):
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise ValueError("Expected a positive associative view number")
    doc = _document(k, handle)
    if doc.DocumentType != k.constants["ksDocumentDrawing"]:
        raise ValueError("Expected a native drawing")
    drawing = _cast(k, doc, "IKompasDocument2D")
    view = drawing.ViewsAndLayersManager.Views.ViewByNumber(number)
    if view is None or not view.Valid:
        raise ValueError("Associative view is missing or invalid")
    types = {k.constants[name] for name in (
        "vt_Arbitrary", "vt_Standart", "vt_Projected", "vt_Arrow", "vt_Remote", "vt_Section"
    )}
    if view.ViewType not in types:
        raise ValueError("Expected an associative view")
    association = _cast(k, view, "IAssociationView")
    if not association.Valid or int(view.ObjectCount) <= 0:
        raise ValueError("Native associative view is empty or invalid")
    return doc, view, association


def _geometry(k, view, max_objects):
    container = _cast(k, view, "IDrawingContainer")
    geometry, consumed = {}, 0
    for key, collection, getter, props in (
        ("lines", "LineSegments", "LineSegment", ("X1", "Y1", "X2", "Y2", "Style")),
        ("circles", "Circles", "Circle", ("Xc", "Yc", "Radius", "Style")),
        ("arcs", "Arcs", "Arc", ("Xc", "Yc", "Radius", "X1", "Y1", "X2", "Y2", "Direction", "Style")),
    ):
        items = getattr(container, collection)
        consumed += int(items.Count)
        if consumed > max_objects:
            raise ValueError("View geometry exceeds max_objects; no partial acceptance")
        rows = []
        for index in range(items.Count):
            item = getattr(items, getter)(index)
            if not item.Valid:
                raise ValueError("Native view contains invalid projected geometry")
            row = {name: (bool(getattr(item, name)) if name == "Direction"
                          and isinstance(getattr(item, name), bool)
                          else _number(getattr(item, name))) for name in props}
            row["visible"] = bool(_cast(k, item, "IDrawingObject1").IsVisibleInAssociationView)
            rows.append(row)
        # Do not use session references or collection order as saved geometry proof.
        geometry[key] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
    if consumed == 0:
        raise ValueError("View has no supported projected curves; bounds/count alone are insufficient")
    return geometry, consumed


def inspect_view_state(k, handle, view_number, max_objects=50000):
    """Capture camera, unfold, positive pose, bounds and actual supported curves."""
    _limit(max_objects)
    doc, view, association = _view(k, handle, view_number)
    source = str(association.SourceFileName)
    if not Path(source).is_absolute() or not Path(source).is_file():
        raise ValueError("View source file is missing or not absolute")
    source_hash = _hash_file(source)
    geometry, count = _geometry(k, view, max_objects)
    raw = list(_cast(k, doc, "IKompasDocument2D1").GetObjectsGabarit(view))
    if len(raw) < 5 or not raw[0]:
        raise ValueError("Native view bounds unavailable")
    state = ViewState(
        number=int(view.Number), view_type=int(view.ViewType), source=source,
        source_sha256=source_hash, matrix=rotation_matrix(association.ProjectionMatrix),
        scale=_number(association.Scale), x=_number(association.X), y=_number(association.Y),
        angle=_number(association.Angle), bounds=tuple(_number(x) for x in raw[-4:]),
        objects=int(view.ObjectCount), unfold=bool(association.Unfold),
        geometry_digest=_digest(geometry),
    ).model_dump(mode="json")
    if _hash_file(source) != source_hash:
        raise ValueError("View source changed during inspection")
    return {
        "state": state, "fingerprint": _digest(state), "view_reference": str(view.Reference),
        "supported_geometry_objects": count,
        "geometry_scope": "line segments, circles and circular arcs with native visibility",
        "source_geometry_current_verified": False,
        "read_only_operation": True,
        "limitations": "Disk SHA and projected-curve state; no rebuild, material, local-cut lineage, "
                       "full 2D coverage, saved-file or visual acceptance claim.",
    }


def compare_view_states(actual, expected, pose_tolerance=1e-6, geometry_tolerance=1e-5,
                        camera_tolerance=1e-8):
    """Compare serializable states, usable after each independent RO reopening."""
    for tolerance in (pose_tolerance, geometry_tolerance, camera_tolerance):
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0 < tolerance <= .1:
            raise ValueError("Tolerances must be finite, positive and <=0.1")
    a = ViewState.model_validate(actual).model_dump(mode="json")
    e = ViewState.model_validate(expected).model_dump(mode="json")
    differences = []
    for key in ("number", "view_type", "source_sha256", "objects", "unfold", "geometry_digest"):
        if a[key] != e[key]:
            differences.append(key)
    if _path_key(a["source"]) != _path_key(e["source"]):
        differences.append("source")
    for key in ("scale", "x", "y", "angle"):
        if abs(a[key]-e[key]) > pose_tolerance:
            differences.append(key)
    for key, tolerance in (("matrix", camera_tolerance), ("bounds", geometry_tolerance)):
        if any(abs(x-y) > tolerance for x, y in zip(a[key], e[key], strict=True)):
            differences.append(key)
    return {"matches": not differences, "differences": differences,
            "actual_fingerprint": _digest(a), "expected_fingerprint": _digest(e),
            "comparison_scope": "explicit view state only; not saved/visual/physical acceptance"}


def compare_view_state(k, handle, view_number, expected, max_objects=50000):
    actual = inspect_view_state(k, handle, view_number, max_objects)
    return {**compare_view_states(actual["state"], expected), "actual": actual}


def _values(value):
    if value is None:
        return ()
    return value if isinstance(value, (tuple, list)) else (value,)


def _optional_curve_interface(k, obj, interface):
    try:
        return _cast(k, obj, interface)
    except Exception as error:
        # Only E_NOINTERFACE is an unsupported SDK interface. TypeError is the
        # equivalent used by platform-independent adapters/fixtures. Disconnection,
        # getters, invalid numbers and every other native failure remain errors.
        if isinstance(error, TypeError) or getattr(error, "hresult", None) == -2147467262:
            return None
        raise


def _curve_anchor(k, obj, view_reference, near_point):
    draw = _cast(k, obj, "IDrawingObject")
    ext = _cast(k, obj, "IDrawingObject1")
    owner = ext.GetView()
    if not draw.Valid:
        return {"skip_reason": "invalid"}
    if draw.Temp:
        return {"skip_reason": "temporary"}
    if not ext.IsVisibleInAssociationView:
        return {"skip_reason": "hidden"}
    if owner is None or str(owner.Reference) != view_reference:
        return {"skip_reason": "other_view"}
    line = _optional_curve_interface(k, obj, "ILineSegment")
    if line is None:
        circle = _optional_curve_interface(k, obj, "ICircle")
        if circle is None:
            return {"skip_reason": "unsupported_curve_type"}
        x, y, radius = [_number(getattr(circle, key)) for key in ("Xc", "Yc", "Radius")]
        if radius <= 0:
            raise ValueError("Visible circle returned a non-positive radius")
        if near_point is None:
            point, score = [x+radius, y], radius*2
        else:
            dx, dy = near_point[0]-x, near_point[1]-y
            angle = math.atan2(dy, dx)
            point = [x+radius*math.cos(angle), y+radius*math.sin(angle)]
            score = -math.dist(point, near_point)
        return {"kind": "circle", "point": point, "score": score,
                "reference": str(draw.Reference)}
    x1, y1, x2, y2 = [_number(getattr(line, key)) for key in ("X1", "Y1", "X2", "Y2")]
    dx, dy = x2-x1, y2-y1
    length = math.hypot(dx, dy)
    if length <= 1e-5:
        return {"skip_reason": "degenerate_line"}
    t = .5 if near_point is None else max(0., min(1., (
        (near_point[0]-x1)*dx + (near_point[1]-y1)*dy)/(length*length)))
    point = [x1+t*dx, y1+t*dy]
    return {"kind": "line", "point": point,
            "score": length if near_point is None else -math.dist(point, near_point),
            "reference": str(draw.Reference)}


def find_visible_anchor(k, handle, view_number, source_document_handle, component_handle,
                        expected_fingerprint, near_point=None, max_objects=5000):
    """Resolve only real visible AssociationObjects of an explicit scoped component.

    The caller must already have made this view Current on its owned drawing copy
    and captured/restored its positive pose. This function never toggles Current.
    Returned references expire after update/reopen; resolve again, do not persist.
    """
    _limit(max_objects)
    if near_point is not None:
        if len(near_point) != 2:
            raise ValueError("near_point must be an explicit finite view-space XY pair")
        near_point = [_number(x) for x in near_point]
    before = inspect_view_state(k, handle, view_number)
    if expected_fingerprint != before["fingerprint"]:
        raise ValueError("Stale view fingerprint; resolve state and anchor again")
    drawing_doc, view, association = _view(k, handle, view_number)
    drawing_identity = (str(drawing_doc.Reference), _path_key(drawing_doc.PathName),
                        str(view.Reference))
    if not view.Current:
        raise ValueError("View must already be Current; this read-only operation does not activate it")
    source_doc = _document(k, source_document_handle)
    source_identity = (str(source_doc.Reference), _path_key(source_doc.PathName))
    if (_path_key(source_doc.PathName) != _path_key(before["state"]["source"])
            or source_doc.Changed):
        raise ValueError("Explicit source document differs from the saved view source or is dirty")
    if k.handle_scopes.get(component_handle) != str(source_doc.Reference):
        raise ValueError("Component handle must be scoped to the explicit source document")
    component = k.get_handle(component_handle)
    choices, scanned, skipped = [], 0, {}
    for obj in _values(association.AssociationObjects(component)):
        scanned += 1
        if scanned > max_objects:
            raise ValueError("AssociationObjects exceeds max_objects; no partial anchor acceptance")
        item = _curve_anchor(k, obj, str(view.Reference), near_point)
        reason = item.get("skip_reason")
        if reason:
            skipped[reason] = skipped.get(reason, 0)+1
        else:
            choices.append(item)
    after = inspect_view_state(k, handle, view_number)
    final_doc, final_view, _ = _view(k, handle, view_number)
    final_source = _document(k, source_document_handle)
    if (drawing_identity != (str(final_doc.Reference), _path_key(final_doc.PathName),
                             str(final_view.Reference)) or not final_view.Current):
        raise RuntimeError("Drawing identity or Current view changed during anchor resolution")
    if (source_identity != (str(final_source.Reference), _path_key(final_source.PathName))
            or final_source.Changed
            or k.handle_scopes.get(component_handle) != source_identity[0]):
        raise RuntimeError("Source document identity, scope or Changed state changed during anchor resolution")
    if after["fingerprint"] != before["fingerprint"]:
        raise RuntimeError("View changed while resolving anchor; no pose repair was attempted")
    if not choices:
        raise ValueError("Component has no supported visible native projection in this view")
    selected = max(choices, key=lambda row: (row["score"], row["reference"]))
    return {"view_number": view_number, "source": before["state"]["source"],
            "source_sha256": before["state"]["source_sha256"],
            "view_fingerprint": before["fingerprint"], "anchor_model_xy": selected["point"],
            "anchor_ref": selected["reference"], "curve_kind": selected["kind"],
            "actual_visible_native_projection": True, "scanned": scanned,
            "skipped_candidates": skipped,
            "reference_lifetime": "session-local; re-resolve after update or reopen",
            "read_only_operation": True}
