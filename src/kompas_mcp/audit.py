"""Bounded, non-rebuilding native audit. No COM objects leave the existing STA.

State flag meanings: installed SDK ksfeaturestateenum.html. A clean cached
feature tree is not proof of successful rebuild, BRep accuracy or assembly fit.
"""

import itertools
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .backend import com_identity
from .documents import _cast, _document

IDENTITY = [float(i % 5 == 0) for i in range(16)]
STATE_FLAGS = {
    1: "locked", 2: "rebuild_required", 4: "inside_macro", 8: "lcs_dependent",
    16: "comprised_of_parts", 32: "current_cs", 64: "source_part_read_only",
    128: "detailed_fold", 256: "sketch_undefined", 512: "sketch_defined",
    1024: "sketch_redefined", 2048: "edit_restricted", 4096: "edit_impossible",
    8192: "fixed_component", 16384: "recalculated_insertion",
    32768: "source_assembly_read_only", 65536: "uncuttable",
    1048576: "update_required", 2097152: "broken_geometry_link",
    16777216: "reveal_composition", 33554432: "deformations",
    67108864: "flexible_subassembly", 134217728: "inherited_mate",
    268435456: "external_reference",
}


def array(value):
    return [] if value is None else list(value) if isinstance(value, (list, tuple)) else [value]


def matrix(value):
    result = [float(v) for v in value]
    if len(result) != 16 or not all(math.isfinite(v) for v in result):
        raise ValueError("Invalid placement matrix")
    return result


def multiply(a, b):
    """Row-vector SDK convention: local-to-parent followed by parent-to-root."""
    return [sum(a[r * 4 + n] * b[n * 4 + c] for n in range(4))
            for r in range(4) for c in range(4)]


def transform_bounds(bounds, transform):
    if len(bounds) != 7 or not bounds[0] or not all(math.isfinite(v) for v in bounds[1:]):
        return None
    if any(bounds[i] > bounds[i + 3] for i in range(1, 4)):
        return None
    corners = itertools.product(*[(bounds[i], bounds[i + 3]) for i in range(1, 4)])
    points = [[sum([*p, 1][r] * transform[r * 4 + c] for r in range(4))
               for c in range(3)] for p in corners]
    return [min(p[c] for p in points) for c in range(3)] + [
        max(p[c] for p in points) for c in range(3)
    ]


def feature_state(feature, sketch_type=None, native_type=None):
    state = int(feature.State)
    kind = int(feature.FeatureType) if native_type is None else native_type
    result = {
        "name": feature.Name, "type": kind, "feature_interface_type": int(feature.FeatureType),
        "valid": bool(feature.Valid),
        "object_error": int(feature.ObjectError), "state": state,
        "flags": [name for flag, name in STATE_FLAGS.items() if state & flag],
        "excluded": bool(feature.Excluded), "rolled_back": bool(feature.IsRollBacked),
    }
    result["issues"] = []
    if result["excluded"] or result["rolled_back"]:
        result["status"] = "inactive"
        return result
    if result["object_error"]:
        result["issues"].append("native_object_error")
    if state & 2097152:
        result["issues"].append("broken_geometry_link")
    for flag in (2, 16, 1048576):
        if state & flag:
            result["issues"].append(STATE_FLAGS[flag])
    if kind == sketch_type:
        for flag in (256, 1024):
            if state & flag:
                result["issues"].append(STATE_FLAGS[flag])
    # A service folder has no geometric result. Do not manufacture a solid error.
    if not result["valid"] and kind != 143:
        result["issues"].append("invalid_native_object")
    hard = {"native_object_error", "broken_geometry_link", "invalid_native_object",
            "sketch_redefined"}
    result["status"] = "failed" if hard.intersection(result["issues"]) else (
        "warning" if result["issues"] else "passed"
    )
    return result


def identity(obj):
    return com_identity(obj)


def body_state(body):
    """Check disconnected lumps separately from body count (SDK v23+).

    Unsupported/read failures are explicit, not a false clean result. Surfaces
    remain inconclusive because zero volume can be intentional.
    """
    bounds = list(body.GetGabarit())
    solid = bool(body.IsSolid)
    try:
        multipart = bool(body.MultiBodyParts)
        multipart_error = None
    except Exception as exc:  # noqa: BLE001 - older editions may not expose v23 property
        multipart, multipart_error = None, str(exc)
    issues = ["comprised_of_parts"] if multipart else []
    status = "warning" if multipart else "passed" if (
        multipart is False and solid and transform_bounds(bounds, IDENTITY) is not None
    ) else "inconclusive"
    return {
        "solid": solid, "bounds_raw": bounds, "multi_body_parts": multipart,
        "multi_body_parts_error": multipart_error, "issues": issues, "status": status,
    }


def resolve_occurrence(k, root, path):
    """Resolve an index path anew, never by a component name or cached source handle."""
    current = root
    for index in path:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Occurrence path must contain nonnegative integer indices")
        if index >= current.Parts.Count:
            raise ValueError("stale_occurrence: tree path no longer exists; refresh audit")
        current = current.Parts.Part(index)
    return current


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def audit_model(k, handle, report_dir, include_excluded=False, max_nodes=10000):
    if not 1 <= max_nodes <= 50000:
        raise ValueError("max_nodes must be 1..50000")
    folder = Path(report_dir)
    if not folder.is_absolute():
        raise ValueError("Use an absolute, new report directory")
    doc = _document(k, handle)
    model = _cast(k, doc, "IKompasDocument3D")
    root = model.TopPart
    folder.mkdir(parents=True, exist_ok=False)
    changed_before = bool(doc.Changed)
    summary = {
        "schema": 1, "document": doc.PathName, "reference": doc.Reference,
        "started": datetime.now(UTC).isoformat(), "state": "running",
        "mode": "read cached native state; no rebuild/save/activation",
        "changed_before": changed_before, "include_excluded": include_excluded,
        "checks": {}, "counts": {},
        "feature_coverage": "reachable feature tree in each source's first assembly occurrence",
    }
    rows = []
    sources = set()
    bodies_seen = {}
    errors = []
    counts = Counter()
    limited = False

    def emit(row):
        nonlocal limited
        if len(rows) >= max_nodes:
            limited = True
            return False
        rows.append(row)
        counts[row["kind"]] += 1
        counts[row["status"]] += 1
        journal.write(json.dumps(row, ensure_ascii=False) + "\n")
        journal.flush()
        if len(rows) % 25 == 0:
            summary["counts"] = dict(counts)
            write_json(folder / "status.json", summary)
        return True

    def scan_features(part, path):
        # Retain wrappers while pointer identities are keys: otherwise a released
        # Automation proxy address can be reused by a different native feature.
        features_seen = {}
        pending = [( _cast(k, part, "IFeature7"), [])]
        while pending and not limited:
            feature, feature_path = pending.pop()
            model_object = _cast(k, feature, "IModelObject")
            kind = int(model_object.ModelObjectType)
            # SubFeatures can expose a body's complete face/edge/vertex tree.
            # It is not the parametric operation history and can contain millions
            # of wrappers. Own final bodies are inspected separately below.
            if kind in {6, 7, 8, 115}:
                counts["topology_tree_nodes_skipped"] += 1
                continue
            if feature_path and kind == 104:
                # Component occurrences have their own explicit visit and source scope.
                continue
            key = (int(model_object.Reference), kind)
            if key in features_seen:
                continue
            features_seen[key] = feature
            info = feature_state(feature, k.constants.get("o3d_sketch"), kind)
            emit({"kind": "feature", "occurrence": path, "feature_path": feature_path,
                  "reference": key[0], **info})
            if not include_excluded and info["status"] == "inactive":
                continue
            if len(feature_path) >= 64:
                errors.append({"path": path, "error": "maximum_feature_depth"})
                continue
            for i, sub in reversed(list(enumerate(array(feature.SubFeatures(0, True, True))))):
                pending.append((_cast(k, sub, "IFeature7"), [*feature_path, i]))
        # Diagnostic objects are not necessarily in the operational feature tree.
        measurements = _cast(k, part, "IMeasurementContainer")
        for name in ("Collisions", "CheckGeometries"):
            collection = getattr(measurements, name)
            for i in range(collection.Count):
                diagnostic = collection.Item(i)
                emit({
                    "kind": "diagnostic", "occurrence": path, "collection": name,
                    "index": i,
                    **feature_state(_cast(k, diagnostic, "IFeature7"), native_type=int(
                        _cast(k, diagnostic, "IModelObject").ModelObjectType
                    )),
                })

    def visit(part, path, parent_matrix, inherited_excluded, ancestors):
        if limited:
            return
        feature = _cast(k, part, "IFeature7")
        info = feature_state(feature, k.constants.get("o3d_sketch"))
        excluded = inherited_excluded or info["excluded"] or info["rolled_back"]
        local = matrix(part.Placement.GetMatrix3D()) if path else IDENTITY
        composed = multiply(local, parent_matrix)
        bounds = list(part.GetGabarit(False, False))
        source = str(part.FileName or "")
        row = {
            "kind": "occurrence", "path": path, "source": source,
            "reference": part.Reference, "fixed": bool(part.Fixed),
            "hidden": bool(part.Hidden), "load_state": int(part.LoadState),
            "local_to_parent": local, "local_to_root": composed,
            "bounds_parent_raw": bounds,
            # Native GetGabarit already includes this occurrence's placement.
            "bounds_root_envelope_mm": transform_bounds(bounds, parent_matrix),
            "inherited_excluded": inherited_excluded, **info,
        }
        if excluded:
            row["status"] = "inactive"
        elif path and source and not Path(source).is_file():
            row["status"] = "failed"
            row["issues"].append("missing_source_file")
        if not emit(row) or (excluded and not include_excluded):
            return
        source_key = str(Path(source).resolve()).casefold() if source else f"embedded:{path}"
        if source_key not in sources:
            sources.add(source_key)
            try:
                scan_features(part, path)
                # Own bodies, not just root BodyCollection or leaf components.
                for i, raw in enumerate(array(feature.ResultBodies)):
                    body = _cast(k, raw, "IBody7")
                    key = (source_key, identity(body))
                    if key in bodies_seen:
                        continue
                    bodies_seen[key] = body
                    emit({
                        "kind": "body", "occurrence": path, "index": i,
                        **body_state(body),
                    })
            except Exception as exc:  # noqa: BLE001 - retain per-source native failures
                errors.append({"path": path, "phase": "features_or_bodies", "error": str(exc)})
        if source_key in ancestors:
            errors.append({"path": path, "error": "cyclic_source_reference"})
            return
        if len(path) >= 64:
            errors.append({"path": path, "error": "maximum_occurrence_depth"})
            return
        for i in range(part.Parts.Count):
            try:
                visit(part.Parts.Part(i), [*path, i], composed, excluded, ancestors | {source_key})
            except Exception as exc:  # noqa: BLE001 - continue independent occurrences
                errors.append({"path": [*path, i], "phase": "occurrence", "error": str(exc)})

    write_json(folder / "status.json", summary)
    try:
        with (folder / "journal.jsonl").open("x", encoding="utf-8") as journal:
            visit(root, [], IDENTITY, False, set())
        summary.update(
            state="completed", counts=dict(counts), source_files=len(sources),
            truncated=limited, errors=errors, changed_after=bool(doc.Changed),
            unfixed_top_occurrences=sum(
                r["kind"] == "occurrence" and len(r["path"]) == 1 and
                r["status"] != "inactive" and not r["fixed"] for r in rows
            ),
        )
        state_status = "failed" if counts["failed"] else (
            "inconclusive" if errors or limited or counts["inconclusive"] or
            counts["warning"] else "passed"
        )
        summary["checks"] = {
            "cached_native_state": state_status,
            "native_object_errors": "failed" if any(
                r.get("object_error", 0) and r["status"] != "inactive" for r in rows
            ) else "inconclusive" if errors or limited else "passed",
            "rebuild_state": "inconclusive" if any(
                set(r.get("issues", [])) & {"rebuild_required", "update_required"}
                for r in rows if r["status"] != "inactive"
            ) or errors or limited else "passed",
            "sketch_constraints": "inconclusive" if any(
                "sketch_undefined" in r.get("issues", []) for r in rows
            ) else "passed",
            "independent_rebuild": "inconclusive: not run; use isolated copies",
            "brep_accuracy": "inconclusive: not run; null SDK result is not a pass",
            "collisions": "inconclusive: not run; use check_collisions on isolated copies",
            "body_connectedness": "warning" if any(
                "comprised_of_parts" in r.get("issues", [])
                for r in rows if r["status"] != "inactive"
            ) else "inconclusive" if errors or limited or any(
                r["kind"] == "body" and r.get("multi_body_parts") is None for r in rows
            ) else "passed",
            "unchanged_memory": "passed" if changed_before == bool(doc.Changed) else "failed",
        }
        write_json(folder / "details.json", rows)
    except BaseException as exc:
        summary.update(state="failed", error=str(exc), counts=dict(counts))
        raise
    finally:
        write_json(folder / "status.json", summary)
    return {"report_dir": str(folder), **summary}


def read_report(report_dir, offset=0, limit=100):
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("offset >= 0, limit 1..200 required")
    folder = Path(report_dir)
    if not folder.is_absolute():
        raise ValueError("Use an absolute report directory")
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    with (folder / "journal.jsonl").open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in itertools.islice(stream, offset, offset + limit)]
    return {"summary": status, "offset": offset, "rows": rows}
