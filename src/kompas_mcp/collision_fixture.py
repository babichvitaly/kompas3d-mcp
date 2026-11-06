"""Flatten explicit nested occurrences into a saved top-level collision fixture.

World matrices use the SDK row-vector convention, as independently exercised in
the native angle sweep. This tool establishes input provenance, not native
collision endpoint identity or a universal fit certificate.
"""

from pathlib import Path

from .assemblies import rigid_matrix
from .audit import IDENTITY, matrix, multiply, resolve_occurrence, write_json
from .backend import require
from .collisions import verify_copy_tree
from .documents import _cast, _document
from .project_copy import (
    assert_occurrences,
    canonical,
    digest,
    native_document,
    occurrence_snapshot,
    path_key,
    verify_external_isolation,
)


def validate_paths(paths):
    if not 1 <= len(paths) <= 1000:
        raise ValueError("Select 1..1000 explicit component occurrence paths")
    values = []
    for path in paths:
        if not path or len(path) > 64 or any(isinstance(i, bool) or not isinstance(i, int) or i < 0
                                            for i in path):
            raise ValueError("Use nonempty bounded integer occurrence paths, not the root")
        value = tuple(path)
        for other in values:
            if value[:len(other)] == other or other[:len(value)] == value:
                raise ValueError("Overlapping/duplicate occurrence paths would double-count geometry")
        values.append(value)
    return values


def occurrence_world(k, root, path):
    current, world = root, list(IDENTITY)
    for depth in range(1, len(path) + 1):
        current = resolve_occurrence(k, root, path[:depth])
        feature = _cast(k, current, "IFeature7")
        if feature.Excluded or feature.IsRollBacked:
            raise ValueError("An excluded or rolled-back occurrence is not an active collision input")
        world = multiply(matrix(current.Placement.GetMatrix3D()), world)
    return current, rigid_matrix(world)


def set_native_matrix(k, part, value):
    """API5 placement self-assignment is intentionally avoided (tested in v25)."""
    import pythoncom
    from win32com.client import VARIANT

    value = rigid_matrix(value)
    fixed_before = bool(part.Fixed)
    unfix_update = None
    if fixed_before:
        part.Fixed = False
        unfix_update = bool(part.Update())
    if part.Fixed:
        raise RuntimeError("Fixture occurrence remains fixed")
    native = k.api.ksPart(k.app.TransferInterface(part, k.constants["ksAPI5Auto"], 0))
    placement = native.GetPlacement()
    require(placement.InitByMatrix3D(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, value)),
            "initialize fixture world placement")
    # False can occur even though matrix readback succeeds. Preserve the native
    # return and require independent readback/reopen, rather than inventing True.
    updated = bool(native.UpdatePlacement())
    part.Fixed = True
    fix_update = bool(part.Update())
    if not part.Fixed:
        raise RuntimeError("Fixture occurrence fixed state readback failed")
    actual = matrix(part.Placement.GetMatrix3D())
    if any(abs(a - b) > 1e-8 for a, b in zip(value, actual, strict=True)):
        raise RuntimeError("Fixture world placement readback mismatch")
    return {"native_update_return": updated, "matrix_readback_verified": True,
            "fixed_before": fixed_before, "unfix_update_return": unfix_update,
            "fix_update_return": fix_update, "fixed_readback_verified": True}


def create_collision_fixture(k, handle, occurrence_paths, copy_root, destination, dry_run=True):
    doc = _document(k, handle)
    if doc.DocumentType != k.constants["ksDocumentAssembly"]:
        raise ValueError("Select an explicit assembly document")
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    folder = verify_copy_tree(k, doc, root, copy_root)
    external = verify_external_isolation(k, doc, folder)
    if doc.Changed:
        raise ValueError("Save the isolated source before creating a fixture from its disk sources")
    paths = validate_paths(occurrence_paths)
    output = Path(destination)
    if not output.is_absolute() or output.suffix.lower() != ".a3d" or output.exists():
        raise ValueError("Use a new absolute native assembly destination")
    output = output.resolve()
    if not output.is_relative_to(folder):
        raise ValueError("Fixture destination must be inside copy_root")
    rows = []
    sources = [doc.PathName, *(row["path"] for row in external)]
    hashes = {path_key(path): {"source": str(canonical(path)), "sha256": digest(path)}
              for path in sources}
    for path in paths:
        part, world = occurrence_world(k, root, path)
        source = canonical(part.FileName, doc.PathName) if part.FileName else None
        if source is None or not source.is_file() or not source.is_relative_to(folder):
            raise ValueError("Embedded or outside-copy sources cannot be inserted as independent occurrences")
        if source.suffix.lower() not in {".m3d", ".a3d"}:
            raise ValueError("Fixture inputs need native file-backed models")
        # A transform alone cannot carry context-dependent external cuts/mates.
        # Such inputs remain limited by this explicit source-file representation.
        hashes[path_key(source)] = {"source": str(source), "sha256": digest(source)}
        rows.append({"fixture_index": len(rows), "occurrence_path": list(path),
                     "source": str(source), "local_to_root": world,
                     "representation": "linked native source file at composed world placement"})
    before = occurrence_snapshot(k, doc)
    report = {"schema": 1, "operation": "create_collision_fixture", "status": "planned",
              "dry_run": dry_run, "source_assembly": doc.PathName, "destination": str(output),
              "occurrences": rows, "source_hashes": list(hashes.values()),
              "persistence_verified": False, "source_memory_unchanged": None,
              "collision_result": "not_run", "pair_attribution": "not_established",
              "verification_scope": "Input sources and transforms only; no collision/fit certificate",
              "geometry_context": "inconclusive: source-file shape may omit assembly-context operations",
              "limits": "No contextual geometry transfer, mate solving, or pair certainty inferred; "
                        "run native checks on the explicit top-level fixture scopes"}
    if dry_run:
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".fixture.json")
    if manifest.exists():
        raise FileExistsError("Fixture manifest already exists")
    created = None
    phase = "create_fixture"
    try:
        write_json(manifest, report)
        created = require(k.app.ksGetApplication7().Documents.Add(
            k.constants["ksDocumentAssembly"], False), "create fixture assembly")
        created.SaveAs(str(output))
        new_root = _cast(k, created, "IKompasDocument3D").TopPart
        for row in rows:
            phase = f"insert:{row['fixture_index']}"
            part = require(new_root.Parts.AddFromFile(row["source"], True, False),
                           "insert independent fixture occurrence")
            if new_root.Parts.Count != row["fixture_index"] + 1:
                raise RuntimeError("Unexpected fixture insertion count")
            row["native_placement"] = set_native_matrix(k, part, row["local_to_root"])
            hidden_update = None
            if part.Hidden:
                part.Hidden = False
                hidden_update = bool(part.Update())
            if part.Hidden:
                raise RuntimeError("Fixture occurrence remains hidden")
            row["visibility"] = {"native_update_return": hidden_update,
                                 "hidden_readback_verified": True}
            write_json(manifest, report)
        created.SaveAs(str(output))
        if created.Changed or not output.is_file() or not output.stat().st_size:
            raise RuntimeError("Fixture save did not produce a clean nonempty document")
        expected = occurrence_snapshot(k, created)
        scope = str(created.Reference)
        require(created.Close(k.constants["kdDoNotSaveChanges"]), "close saved fixture")
        k.release_scope(scope)
        created = None
        phase = "reopen_fixture"
        with native_document(k, output, True) as reopened:
            new_root = _cast(k, reopened, "IKompasDocument3D").TopPart
            verify_copy_tree(k, reopened, new_root, copy_root)
            verify_external_isolation(k, reopened, folder)
            actual = occurrence_snapshot(k, reopened)
            assert_occurrences(expected, actual)
            if new_root.Parts.Count != len(rows):
                raise RuntimeError("Reopened top-level fixture count mismatch")
            for row in rows:
                part = new_root.Parts.Part(row["fixture_index"])
                if path_key(part.FileName) != path_key(row["source"]):
                    raise RuntimeError("Reopened fixture source mismatch")
                if any(abs(a - b) > 1e-8 for a, b in zip(
                        row["local_to_root"], matrix(part.Placement.GetMatrix3D()), strict=True)):
                    raise RuntimeError("Reopened fixture placement mismatch")
        report.update(status="passed", persistence_verified=True, outside_links=[],
                      fixture_sha256=digest(output), top_level_count=len(rows))
    except Exception as exc:  # noqa: BLE001 - fixture remains inspectable, never promoted
        report.update(status="failed", error=str(exc), failed_phase=phase, partial_output=True,
                      acceptance="Inspect partial fixture and manifest before retrying")
    finally:
        if created is not None:
            scope = str(created.Reference)
            try:
                require(created.Close(k.constants["kdDoNotSaveChanges"]), "close partial fixture")
                k.release_scope(scope)
            except Exception as exc:  # noqa: BLE001 - preserve cleanup failure explicitly
                report.update(status="failed", cleanup_error=str(exc))
        try:
            assert_occurrences(before, occurrence_snapshot(k, doc))
            report["source_memory_unchanged"] = not bool(doc.Changed)
        except Exception as exc:  # noqa: BLE001 - original state is acceptance evidence
            report.update(source_memory_unchanged=False, source_state_error=str(exc))
        report["source_files_unchanged"] = all(Path(r["source"]).is_file() and
                                               digest(r["source"]) == r["sha256"]
                                               for r in hashes.values())
        if not report["source_memory_unchanged"] or not report["source_files_unchanged"]:
            report["status"] = "failed"
        write_json(manifest, report)
    return report
