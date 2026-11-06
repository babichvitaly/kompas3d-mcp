"""Exact collision scopes on explicitly isolated copies, with honest provenance."""

from pathlib import Path

from .audit import IDENTITY, resolve_occurrence, transform_bounds
from .documents import _cast, _document


def verify_copy_tree(k, doc, root, copy_root):
    folder = Path(copy_root)
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError("copy_root must be an existing absolute directory of isolated copies")
    folder = folder.resolve()
    if not doc.PathName or not Path(doc.PathName).resolve().is_relative_to(folder):
        raise ValueError("Document is outside copy_root")
    pending = [(root, 0)]
    visited = 0
    while pending:
        part, depth = pending.pop()
        visited += 1
        if depth > 64 or visited > 50000:
            raise ValueError("Dependency traversal limit; isolation cannot be verified")
        if part.FileName and not Path(part.FileName).resolve().is_relative_to(folder):
            raise ValueError("Dependency outside copy_root; copy/rebind before mutation")
        pending.extend((part.Parts.Part(i), depth + 1) for i in range(part.Parts.Count))
    return folder


def endpoint(k, obj):
    """A body-shaped COM wrapper is not sufficient evidence of an occurrence."""
    try:
        body = _cast(k, obj, "IBody7")
        bounds = list(body.GetGabarit())
        solid = bool(body.IsSolid)
        usable = solid and transform_bounds(bounds, IDENTITY) is not None
        return {
            "usable_body": usable, "solid": solid, "bounds_raw": bounds,
            "occurrence_resolved": False,
            "status": "inconclusive: root/occurrence identity is not established",
        }
    except Exception as exc:  # noqa: BLE001 - native result may be an unusable ghost object
        return {"usable_body": False, "occurrence_resolved": False, "error": str(exc)}


def check_collisions(k, handle, paths1, paths2, copy_root, assembly_as_one=True, limit=200):
    import pythoncom
    from win32com.client import VARIANT

    if not paths1 or not 1 <= limit <= 500 or (not paths2 and len(paths1) < 2):
        raise ValueError("Two groups, or at least two paths in group 1; limit 1..500 required")
    if len(paths1) + len(paths2) > 1000:
        raise ValueError("At most 1000 input occurrences")
    doc = _document(k, handle)
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    verify_copy_tree(k, doc, root, copy_root)
    if doc.ReadOnly:
        raise ValueError("Temporary diagnostic needs a writable test copy")
    groups = [[resolve_occurrence(k, root, p) for p in paths] for paths in (paths1, paths2)]
    paths = [tuple(p) for p in [*paths1, *paths2]]
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            if a[:len(b)] == b or b[:len(a)] == a:
                raise ValueError("Overlapping/redundant occurrence selections are not a valid scope")
    if any(not path for path in [*paths1, *paths2]):
        raise ValueError("Select component paths, not the root assembly itself")
    for path in [*paths1, *paths2]:
        for depth in range(1, len(path) + 1):
            part = resolve_occurrence(k, root, path[:depth])
            if _cast(k, part, "IFeature7").Excluded:
                raise ValueError("Excluded inputs are not an active collision scope")
    measurements = _cast(k, root, "IMeasurementContainer")
    before = measurements.Collisions.Count
    changed = bool(doc.Changed)
    check = measurements.Collisions.Add()
    feature = _cast(k, check, "IFeature7")
    result = {"scope1": paths1, "scope2": paths2, "assembly_as_one": assembly_as_one}
    try:
        check.Regime = 1 if paths2 else 0
        check.AssemblyAsOneObject = assembly_as_one
        check.Simplify = False
        check.CheckTangent = False
        check.CheckGaps = False
        check.CheckThreads = False
        check.ExcludeHiddenObjects = False
        check.ExcludeLayoutGeometry = False
        check.Objects1 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, groups[0])
        if paths2:
            check.Objects2 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, groups[1])
        calculated = check.CalculateCollisions()
        if calculated is None:
            result.update(status="inconclusive", reason="null native calculation result")
        else:
            count = calculated.CollisionsCount
            rows = []
            for i in range(min(count, limit)):
                rows.append({
                    "type": calculated.CollisionType(i), "value": calculated.CollisionValue(i),
                    "endpoint1": endpoint(k, calculated.CollisionObject1(i)),
                    "endpoint2": endpoint(k, calculated.CollisionObject2(i)),
                })
            nested = any(len(path) > 1 for path in [*paths1, *paths2])
            result.update(
                status="failed" if count else "inconclusive" if nested else "passed",
                selection_context="inconclusive" if nested else "top-level input scope",
                collisions_count=count,
                rows=rows, truncated=count > limit,
                attribution="inconclusive: counts refer to input scopes; per-pair identity unproved",
                acceptance="No thread/weld exceptions applied; no assembly-fit certification",
            )
    finally:
        # Never leave a diagnostic that turns a customer's tree red after a query.
        # Delete only the exact temporary object owned by this invocation.
        feature.Delete()
        remaining = measurements.Collisions.Count
        result["cleanup"] = {"count_before": before, "count_after": remaining,
                             "changed_before": changed, "changed_after": bool(doc.Changed)}
        if remaining != before:
            raise RuntimeError("Temporary collision cleanup failed; inspect test copy before retry")
        k.invalidate_topology()
    return result
