"""Interactive CAD acceptance. Synthetic files only, explicit new output directory.

Run: uv run python scripts/validate_audit.py C:/absolute/new-test-directory
Never run under SYSTEM. Does not close existing documents or save source models.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

from kompas_mcp import audit, collisions, documents, features
from kompas_mcp.backend import Kompas
from kompas_mcp.models import Circle, ExtrusionSpec, SketchSpec


def main():
    import pythoncom

    folder = Path(sys.argv[1])
    if not folder.is_absolute():
        raise ValueError("Use a new absolute output directory")
    folder.mkdir(parents=True, exist_ok=False)
    pythoncom.CoInitialize()
    k = Kompas()
    k.connect()
    app = k.app.ksGetApplication7()
    active, hide = app.ActiveDocument, app.HideMessage
    baseline = documents.list_documents(k)["documents"]
    baseline_count = app.Documents.Count
    owned = []
    report = {}
    try:
        app.HideMessage = 2
        part = documents.create_document(k, "part", visible=False)
        handle = part["document"]["handle"]
        owned.append(handle)
        doc_id = part["document_id"]
        sketch = k.sketch(doc_id, SketchSpec(curves=[Circle(radius=5)]))
        k.feature(doc_id, ExtrusionSpec(sketch_id=sketch["sketch_id"], depth=10))
        assert math.isclose(k.measure(doc_id)["volume_mm3"], math.pi * 250, rel_tol=1e-9)
        source = folder / "cylinder.m3d"
        documents.save_document(k, handle, str(source))
        first = features.entities(k, doc_id, "o3d_face", limit=1)
        second = features.entities(k, doc_id, "o3d_face", offset=1, limit=1,
                                   snapshot_id=first["snapshot_id"])
        assert second["snapshot_id"] == first["snapshot_id"]
        assert first["total"] == 3
        result = audit.audit_model(k, handle, str(folder / "part-audit"))
        assert result["checks"]["native_object_errors"] == "passed"
        assert result["counts"].get("failed", 0) == 0
        assert result["counts"]["body"] == 1
        documents.close_document(k, handle)
        owned.remove(handle)
        digest_before = hashlib.sha256(source.read_bytes()).hexdigest()
        sizes = []
        for _ in range(20):
            info = documents.open_document(k, str(source), read_only=True, visible=False)
            handle = info["document"]["handle"]
            owned.append(handle)
            reused = documents.open_document(k, str(source), read_only=True, visible=False)
            assert reused["reused"] and reused["document"]["handle"] == handle
            # Enumerate twice; stable identities must not add aliases.
            documents.list_documents(k)
            count = len(k.handles)
            documents.list_documents(k)
            assert len(k.handles) == count
            documents.close_document(k, handle)
            owned.remove(handle)
            assert handle not in k.handles
            assert app.Documents.Count == baseline_count
            sizes.append(len(k.handles))
        assert max(sizes) == min(sizes), sizes
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest_before
        report["lifecycle"] = {"cycles": 20, "handles_after_close": sizes,
                               "source_sha256_unchanged": True}
        assembly = documents.create_document(k, "assembly", visible=False)
        handle = assembly["document"]["handle"]
        owned.append(handle)
        assembly_path = folder / "pair.a3d"
        documents.save_document(k, handle, str(assembly_path))
        for _ in range(2):
            documents.insert_component(k, handle, str(source))
        doc = documents._document(k, handle)
        root = documents._cast(k, doc, "IKompasDocument3D").TopPart
        report["overlap"] = collisions.check_collisions(k, handle, [[0]], [[1]], str(folder))
        assert report["overlap"]["collisions_count"] == 1
        assert math.isclose(report["overlap"]["rows"][0]["value"], math.pi * 250, rel_tol=1e-7)
        part2 = root.Parts.Part(1)
        part2.Fixed = False
        placement = part2.Placement
        placement.SetOrigin(30, 0, 0)
        part2.UpdatePlacement(True)
        assert list(part2.Placement.GetMatrix3D())[12:15] == [30, 0, 0]
        report["separated"] = collisions.check_collisions(k, handle, [[0]], [[1]], str(folder))
        assert report["separated"]["collisions_count"] == 0
        assert report["separated"]["cleanup"]["count_after"] == 0
        assert k.document(assembly["document_id"]).RebuildDocument()
        documents.save_document(k, handle, str(assembly_path), overwrite=True)
        documents.close_document(k, handle)
        owned.remove(handle)
        reopened = documents.open_document(k, str(assembly_path), visible=False)
        handle = reopened["document"]["handle"]
        owned.append(handle)
        report["reopen"] = audit.audit_model(k, handle, str(folder / "assembly-audit"))
        assert report["reopen"]["counts"]["occurrence"] == 3
        assert report["reopen"]["counts"].get("diagnostic", 0) == 0
        assert report["reopen"]["checks"]["native_object_errors"] == "passed"
        assert report["reopen"]["counts"].get("failed", 0) == 0
        documents.close_document(k, handle, discard_changes=True)
        owned.remove(handle)
        # The same source twice, with a rotated parent: source-local handles and
        # names are insufficient to address a nested occurrence in root space.
        outer = documents.create_document(k, "assembly", visible=False)
        handle = outer["document"]["handle"]
        owned.append(handle)
        outer_path = folder / "nested.a3d"
        documents.save_document(k, handle, str(outer_path))
        for _ in range(2):
            documents.insert_component(k, handle, str(assembly_path))
        doc = documents._document(k, handle)
        root = documents._cast(k, doc, "IKompasDocument3D").TopPart
        second_parent = root.Parts.Part(1)
        second_parent.Fixed = False
        rotated = [-1., 0., 0., 0., 0., -1., 0., 0., 0., 0., 1., 0., 100., 20., 0., 1.]
        from win32com.client import VARIANT

        second_parent.Placement.InitByMatrix3D(
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, rotated)
        )
        second_parent.UpdatePlacement(True)
        assert k.document(outer["document_id"]).RebuildDocument()
        documents.save_document(k, handle, str(outer_path), overwrite=True)
        report["nested_audit"] = audit.audit_model(k, handle, str(folder / "nested-audit"))
        rows = audit.read_report(str(folder / "nested-audit"), limit=200)["rows"]
        child = next(r for r in rows if r["kind"] == "occurrence" and r["path"] == [1, 1])
        assert child["bounds_root_envelope_mm"] == [65., 15., 0., 75., 25., 10.]
        report["nested_bounds"] = child["bounds_root_envelope_mm"]
        report["nested_collision"] = collisions.check_collisions(
            k, handle, [[0, 0]], [[1, 1]], str(folder)
        )
        assert report["nested_collision"]["status"] == "inconclusive"
        assert report["nested_collision"]["collisions_count"] == 0
        documents.close_document(k, handle, discard_changes=True)
        owned.remove(handle)
        after = documents.list_documents(k)["documents"]
        assert len(after) == len(baseline)
        assert [(d["path"], d["changed"]) for d in after] == [
            (d["path"], d["changed"]) for d in baseline
        ]
        report["passed"] = True
    finally:
        for handle in reversed(owned):
            if handle in k.handles:
                documents.close_document(k, handle, discard_changes=True)
        app.HideMessage = hide
        if active:
            active.Active = True
        audit.write_json(folder / "acceptance.json", report)
        k = None
        pythoncom.CoUninitialize()
    print(json.dumps({"passed": report.get("passed", False), "report": str(folder / "acceptance.json")}))


if __name__ == "__main__":
    main()
