"""Read-only, bounded native connected-face diagnostics on the existing STA.

Face graph components describe connected boundary patches/shells. A solid with
an enclosed cavity can have several boundary shells while remaining connected;
only native MultiBodyParts is used as evidence of disconnected solid material.
No rebuild, rollback, edit, save, selection or suppression occurs here.
"""

import math

from .audit import array
from .backend import com_identity
from .documents import _cast, _document, _info


def union_boxes(boxes):
    if not boxes or any(len(b) != 6 or not all(math.isfinite(x) for x in b) or
                        any(b[i] > b[i + 3] for i in range(3)) for b in boxes):
        return None
    return [min(b[i] for b in boxes) for i in range(3)] + [
        max(b[i] for b in boxes) for i in range(3, 6)]


def graph_components(adjacency):
    """Only known nodes; callers must independently mark unknown neighbors."""
    unvisited, result = set(adjacency), []
    while unvisited:
        pending = [min(unvisited)]
        component = set()
        while pending:
            node = pending.pop()
            if node in component:
                continue
            if node not in adjacency:
                raise ValueError("Unknown graph endpoint")
            component.add(node)
            pending.extend(adjacency[node] - component)
        unvisited -= component
        result.append(sorted(component))
    return result


def face_bounds(face, remaining_edges):
    edges = face.EdgeCollection()
    count = int(edges.GetCount())
    if count > remaining_edges:
        raise ValueError("Edge traversal limit exceeded")
    boxes = []
    for i in range(count):
        raw = list(edges.GetByIndex(i).GetCurve3D().GetGabarit())
        if len(raw) != 7 or not raw[0]:
            raise ValueError("Native edge GetGabarit failed")
        boxes.append([float(v) for v in raw[1:]])
    return union_boxes(boxes), count


def analyze_body(body, index, max_faces, max_edges):
    """Native API5 own-body faces; all wrappers retained throughout this scan."""
    result = {"body_index": index, "solid": bool(body.IsSolid()), "status": "inconclusive",
              "face_graph_complete": False, "face_graph_component_count": None,
              "components_are": "connected boundary shells/patches, not a volumetric component count"}
    if not result["solid"]:
        result["reason"] = "Not a solid body"
        return result, 0
    try:
        result["native_multi_body_parts"] = bool(body.MultiBodyParts)
    except Exception as exc:  # noqa: BLE001 - unsupported native property is not False
        result["native_multi_body_parts"] = None
        result["multi_body_parts_error"] = str(exc)
    collection = body.FaceCollection()
    total = int(collection.GetCount())
    count = min(total, max_faces)
    result.update(face_count=total, scanned_faces=count, truncated=count != total)
    faces = [collection.GetByIndex(i) for i in range(count)]
    entities = [face.GetEntity() for face in faces]
    identities = [com_identity(entity) for entity in entities]
    by_identity = {key: i for i, key in enumerate(identities)}
    errors = []
    if len(by_identity) != len(identities):
        errors.append({"phase": "identity", "reason": "Duplicate canonical native face identity"})
    adjacency = {i: set() for i in range(count)}
    details, neighbor_keepers = [], []
    edges_seen = 0
    for i, face in enumerate(faces):
        row = {"index": i, "area_mm2": None, "bounds_mm": None}
        try:
            area = float(face.GetArea(1))
            if not math.isfinite(area) or area <= 0:
                raise ValueError("Native face area is zero or invalid")
            row["area_mm2"] = area
            row["bounds_mm"], edge_count = face_bounds(face, max_edges - edges_seen)
            edges_seen += edge_count
            if row["bounds_mm"] is None:
                row["bounds_status"] = "inconclusive: no bounded edges on this face"
        except Exception as exc:  # noqa: BLE001
            errors.append({"face": i, "phase": "geometry", "error": str(exc)})
        try:
            neighbors = face.ConnectedFaceCollection()
            if neighbors is None:
                raise ValueError("Null native adjacency collection")
            neighbor_count = int(neighbors.GetCount())
            if neighbor_count > max_faces:
                raise ValueError("Neighbor traversal limit exceeded")
            for j in range(neighbor_count):
                neighbor = neighbors.GetByIndex(j)
                entity = neighbor.GetEntity()
                neighbor_keepers.extend((neighbor, entity))
                other = by_identity.get(com_identity(entity))
                if other is None:
                    errors.append({"face": i, "phase": "adjacency", "reason": "Unknown/out-of-scope native neighbor"})
                elif other != i:
                    adjacency[i].add(other)
        except Exception as exc:  # noqa: BLE001
            errors.append({"face": i, "phase": "adjacency", "error": str(exc)})
        details.append(row)
    graph_errors = [e for e in errors if e["phase"] in {"adjacency", "identity"}]
    asymmetry = [(i, j) for i, neighbors in adjacency.items() for j in neighbors if i not in adjacency[j]]
    if asymmetry:
        graph_errors.append({"phase": "adjacency", "reason": "Asymmetric native face adjacency",
                             "sample": [list(edge) for edge in asymmetry[:20]]})
        errors.append(graph_errors[-1])
    # Symmetrize only to report candidate patches. If native adjacency is missing,
    # these candidates must never be reported as a verified component count.
    undirected = {i: set(values) for i, values in adjacency.items()}
    for i, values in adjacency.items():
        for j in values:
            undirected[j].add(i)
    groups = graph_components(undirected)
    components = []
    for group in groups:
        values = [details[i] for i in group]
        geometry_complete = all(r["area_mm2"] is not None and r["bounds_mm"] is not None for r in values)
        components.append({"face_indices": group, "face_count": len(group),
                           "area_mm2": sum(r["area_mm2"] or 0 for r in values),
                           "area_status": "measured" if all(r["area_mm2"] is not None for r in values) else "partial",
                           "bounds_mm": union_boxes([r["bounds_mm"] for r in values]) if geometry_complete else None,
                           "geometry_complete": geometry_complete})
    complete = not result["truncated"] and not graph_errors and total > 0
    result.update(face_graph_complete=complete,
                  face_graph_component_count=len(groups) if complete else None,
                  candidate_boundary_components=components, errors=errors[:200],
                  errors_truncated=len(errors) > 200, traversed_edges=edges_seen,
                  material_connectedness="disconnected" if result["native_multi_body_parts"] is True else
                  "connected_by_native_flag" if result["native_multi_body_parts"] is False else "inconclusive")
    result["status"] = "inconclusive" if not complete or errors or result["native_multi_body_parts"] is None else (
        "warning" if result["native_multi_body_parts"] else "passed")
    return result, count


def history_flags(k, root, limit=5000):
    """Advanced helper with a known native cache mutation; NOT a read-only query.

    Not exposed by inspect_body_components. Historical MultiBodyParts getters can
    set Changed=True even on read-only documents. Use only in a separate explicit
    mutation experiment on owned copies, never as a causal rollback proof.
    """
    pending = [(_cast(k, root, "IFeature7"), [])]
    seen, keepers, rows, errors = set(), [], [], []
    visited = 0
    while pending:
        feature, path = pending.pop()
        visited += 1
        if visited > limit or len(path) > 64:
            return rows, [*errors, {"phase": "history", "reason": "Feature traversal limit"}], True
        obj = _cast(k, feature, "IModelObject")
        kind = int(obj.ModelObjectType)
        key = (int(obj.Reference), kind)
        if key in seen:
            continue
        seen.add(key)
        keepers.extend((feature, obj))
        if kind in {6, 7, 8, 115, 143} or (path and kind == 104):
            continue
        if path and kind not in {1, 2, 3, 4, 5, 14, 71, 72, 73}:
            row = {"tree_path": path, "name": str(feature.Name), "type": kind,
                   "excluded": bool(feature.Excluded), "rolled_back": bool(feature.IsRollBacked),
                   "native_multi_body_parts": None}
            try:
                # Use the documented API7 extension on the actual feature object.
                # An API5 entity alias need not expose this property in v25 even
                # when its wrapper advertises a similarly named SDK member.
                native = _cast(k, feature, "IModelObject1")
                keepers.append(native)
                row["native_multi_body_parts"] = bool(native.MultiBodyParts)
            except Exception as exc:  # noqa: BLE001
                row["read_error"] = str(exc)
                errors.append({"phase": "history", "tree_path": path, "error": str(exc)})
            rows.append(row)
        children = array(feature.SubFeatures(0, True, True))
        if visited + len(pending) + len(children) > limit:
            return rows, [*errors, {"phase": "history", "reason": "Feature traversal limit"}], True
        for i, child in reversed(list(enumerate(children))):
            pending.append((_cast(k, child, "IFeature7"), [*path, i]))
    return rows, errors, False


def history_outline(k, root, limit=5000):
    """Safe cached tree outline; never queries historical MultiBodyParts."""
    pending = [(_cast(k, root, "IFeature7"), [])]
    seen, keepers, rows, errors = set(), [], [], []
    visited = 0
    while pending:
        feature, path = pending.pop()
        visited += 1
        if visited > limit or len(path) > 64:
            return rows, [*errors, {"phase": "history_outline", "reason": "Feature traversal limit"}], True
        try:
            obj = _cast(k, feature, "IModelObject")
            kind = int(obj.ModelObjectType)
            identity = (int(obj.Reference), kind)
            if identity in seen:
                continue
            seen.add(identity)
            keepers.extend((feature, obj))
            if kind in {6, 7, 8, 115, 143} or (path and kind == 104):
                continue
            if path and kind not in {1, 2, 3, 4, 5, 14, 71, 72, 73}:
                rows.append({"tree_path": path, "name": str(feature.Name), "type": kind,
                             "excluded": bool(feature.Excluded), "rolled_back": bool(feature.IsRollBacked),
                             "native_multi_body_parts": None,
                             "multi_body_parts_status": "not_queried: historical getter can change native dirty state"})
            children = array(feature.SubFeatures(0, True, True))
            if visited + len(pending) + len(children) > limit:
                return rows, [*errors, {"phase": "history_outline", "reason": "Feature traversal limit"}], True
            for i, child in reversed(list(enumerate(children))):
                pending.append((_cast(k, child, "IFeature7"), [*path, i]))
        except Exception as exc:  # noqa: BLE001 - report unknown outline without hiding body evidence
            errors.append({"phase": "history_outline", "tree_path": path, "error": str(exc)})
    return rows, errors, False


def inspect_body_components(k, handle, max_faces=5000):
    """Inspect own solid bodies and native feature flags without changing CAD."""
    if not 1 <= max_faces <= 50000:
        raise ValueError("max_faces must be 1..50000")
    doc = _document(k, handle)
    changed = bool(doc.Changed)
    info = _info(k, doc)
    if info["kind"] not in {"part", "assembly"}:
        raise ValueError("Select an explicit native part or assembly document")
    native = k.document(info["document_id"]).GetPart(-1)
    bodies = native.BodyCollection()
    total = int(bodies.GetCount())
    result = {"operation": "inspect_body_components", "document": doc.PathName,
              "scope": "own solid bodies only; child occurrences are not inspected",
              "changed_before": changed, "body_count": total, "bodies": [],
              "limits": "Boundary graph components are shells, not volumetric parts. "
                        "MultiBodyParts is the native material-connectedness flag. "
                        "Historical feature getters are skipped because they can change dirty state. "
                        "No rebuild/rollback/BRep certification is performed."}
    try:
        remaining, max_edges = max_faces, max_faces * 40
        for index in range(min(total, max_faces)):
            try:
                row, consumed = analyze_body(bodies.GetByIndex(index), index, remaining, max_edges)
                remaining -= consumed
                max_edges -= row.get("traversed_edges", 0)
            except Exception as exc:  # noqa: BLE001 - preserve every independent body failure
                row = {"body_index": index, "status": "inconclusive", "error": str(exc)}
            result["bodies"].append(row)
            if remaining <= 0 or max_edges <= 0:
                break
        result["truncated"] = len(result["bodies"]) != total or any(r.get("truncated") for r in result["bodies"])
        # IModelObject1.MultiBodyParts on historical operations has a live-tested
        # lazy side effect: even a read-only document becomes Changed=True. Keep
        # this read-only tool strictly on own-body API5 geometry and flags. The
        # historical query is not invoked, including on nominally read-only files.
        history, history_errors, history_limited = history_outline(k, _cast(k, doc, "IKompasDocument3D").TopPart)
        result.update(feature_history=history, history_errors=history_errors, history_truncated=history_limited,
                      history_status="inconclusive_outline" if history_errors or history_limited else "cached_outline_only",
                      historical_multi_body_parts="not_queried: native getter can change document dirty state",
                      flagged_features=[])
        states = [r["status"] for r in result["bodies"]]
        # Unknown causal/history flags do not erase a proven native body warning.
        # Keep that separate uncertainty visible in history_status/history_errors.
        result["status"] = "inconclusive" if result["truncated"] or "inconclusive" in states else (
            "warning" if "warning" in states else "passed")
    finally:
        result["changed_after"] = bool(doc.Changed)
        result["memory_unchanged"] = changed == result["changed_after"]
        if not result["memory_unchanged"]:
            result.update(status="failed", acceptance="Read-only diagnosis changed dirty state; do not save")
    return result
