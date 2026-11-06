"""Native API5 sketch plane coordinates; checked with API7 GetPoint3D."""

import math

from .backend import require
from .collisions import verify_copy_tree
from .documents import _cast, _document, _info
from .project_copy import verify_external_isolation
from .sketches import selected_sketches


def finite_vector(value, size):
    if len(value) != size or any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                                 not math.isfinite(v) for v in value):
        raise ValueError(f"Expected {size} finite coordinates")
    return [float(v) for v in value]


def frame_snapshot(k, entity):
    definition = entity.GetDefinition()
    location = definition.GetLocation()
    if not isinstance(location, (list, tuple)) or len(location) != 3 or not location[0]:
        raise RuntimeError("Native GetLocation did not return checked plane coordinates")
    native = _cast(k, k.app.TransferInterface(entity, k.constants["ksAPI7Dual"], 0), "ISketch")
    points = []
    for x, y in ((0., 0.), (1., 0.), (0., 1.)):
        point = native.GetPoint3D(x, y)
        if not isinstance(point, (list, tuple)) or len(point) != 4 or not point[0]:
            raise RuntimeError("Native GetPoint3D did not return a checked point")
        points.append(finite_vector(point[1:], 3))
    angle = float(definition.angle)
    finite_vector([angle], 1)
    return {"translation": finite_vector(location[1:], 2), "angle": angle, "points": points}


def compare_frame(expected, actual, tolerance=1e-7):
    if set(expected) != {"translation", "angle", "points"}:
        raise ValueError("expected_frame requires translation[2], angle, and three GetPoint3D points")
    a = finite_vector(expected["translation"], 2)
    b = finite_vector(actual["translation"], 2)
    delta = abs((float(expected["angle"]) - actual["angle"] + 180) % 360 - 180)
    if not math.isfinite(delta) or delta > tolerance or any(abs(x - y) > tolerance
                                                          for x, y in zip(a, b, strict=True)):
        raise ValueError("Stale sketch frame: translation/angle do not match")
    if len(expected["points"]) != 3 or len(actual["points"]) != 3:
        raise ValueError("Frame verification requires origin and both unit-axis points")
    for wanted, measured in zip(expected["points"], actual["points"], strict=True):
        if any(abs(x - y) > tolerance for x, y in zip(finite_vector(wanted, 3), measured, strict=True)):
            raise ValueError("Sketch world frame does not match expected GetPoint3D points")


def target_frame(before, translation, angle):
    """Remove old in-plane rotation, apply requested absolute plane coordinates."""
    translation = finite_vector(translation, 2)
    angle = finite_vector([angle], 1)[0]
    p, pu, pv = before["points"]
    u = [a - b for a, b in zip(pu, p, strict=True)]
    v = [a - b for a, b in zip(pv, p, strict=True)]
    # Reject degenerate/nonorthonormal inputs before any mutation.
    if (abs(sum(a*a for a in u) - 1) > 1e-7 or abs(sum(a*a for a in v) - 1) > 1e-7 or
            abs(sum(a*b for a, b in zip(u, v, strict=True))) > 1e-7):
        raise ValueError("GetPoint3D frame is not a rigid orthonormal plane")
    c, s = math.cos(math.radians(before["angle"])), math.sin(math.radians(before["angle"]))
    base_u = [c*a - s*b for a, b in zip(u, v, strict=True)]
    base_v = [s*a + c*b for a, b in zip(u, v, strict=True)]
    dx, dy = [a - b for a, b in zip(translation, before["translation"], strict=True)]
    origin = [q + dx*a + dy*b for q, a, b in zip(p, base_u, base_v, strict=True)]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    new_u = [c*a + s*b for a, b in zip(base_u, base_v, strict=True)]
    new_v = [-s*a + c*b for a, b in zip(base_u, base_v, strict=True)]
    return {"translation": translation, "angle": angle,
            "points": [origin, [p + a for p, a in zip(origin, new_u, strict=True)],
                       [p + a for p, a in zip(origin, new_v, strict=True)]]}


def set_sketch_frame(k, handle, copy_root, name, expected_frame, translation, angle, dry_run=True):
    """Move/rotate one native sketch frame without editing primitive coordinates.

    Translation and angle are absolute with respect to the sketch support plane;
    support and offset are retained. This intentionally changes world geometry.
    The tool neither saves nor claims unchanged body bounds/volume. Save/reopen
    is an explicit subsequent acceptance step. On partial failure do not retry.
    """
    doc = _document(k, handle)
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    verify_copy_tree(k, doc, root, copy_root)
    verify_external_isolation(k, doc, copy_root)
    if doc.ReadOnly or root.Parts.Count:
        raise ValueError("Use a writable isolated part copy, not an assembly")
    info = _info(k, doc)
    entity = selected_sketches(k, info["document_id"], [name])[0]
    before = frame_snapshot(k, entity)
    if expected_frame is not None:
        compare_frame(expected_frame, before)
    elif not dry_run:
        raise ValueError("Apply requires expected_frame from a fresh dry run")
    wanted = target_frame(before, translation, angle)
    result = {"operation": "set_sketch_frame", "document": doc.PathName, "name": name,
              "dry_run": dry_run, "before": before, "target": wanted,
              "status": "planned", "saved": False, "persistence_verified": False,
              "verification": "native origin and both unit axes in world coordinates",
              "limits": "Support plane/offset retained; geometry changes intentionally; "
                        "body validity, downstream features and persistence need separate acceptance"}
    if dry_run:
        return result
    phase = "set_location"
    try:
        definition = entity.GetDefinition()
        require(definition.SetLocation(*wanted["translation"]), "set native sketch plane translation")
        phase = "set_angle"
        definition.angle = wanted["angle"]
        require(entity.Update(), "update native sketch frame")
        phase = "rebuild"
        require(k.document(info["document_id"]).RebuildDocument(), "rebuild moved sketch copy")
        phase = "verify_GetPoint3D"
        after = frame_snapshot(k, entity)
        compare_frame(wanted, after)
        result.update(status="passed", after=after, frame_verified=True,
                      intentional_world_geometry_change=True)
    except Exception as exc:  # noqa: BLE001 - retain partial native mutation evidence
        result.update(status="failed", failed_phase=phase, error=str(exc), mutation_possible=True,
                      acceptance="Inspect/discard this copy's unsaved changes before retrying")
        try:
            result["after_failure"] = frame_snapshot(k, entity)
        except Exception as read_error:  # noqa: BLE001
            result["readback_error"] = str(read_error)
    finally:
        k.invalidate_topology()
    return result
