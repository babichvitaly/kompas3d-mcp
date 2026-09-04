"""Live API7 sheet-metal creation/edit/persistence acceptance; owns its documents."""

import json
from pathlib import Path
from uuid import uuid4

from kompas_mcp import bridge
from kompas_mcp.backend import Kompas
from kompas_mcp.models import Polyline, SketchSpec


def main():
    import pythoncom

    pythoncom.CoInitialize()
    k = Kompas()
    folder = Path(__file__).resolve().parents[1] / "artifacts" / f"sheet-metal-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    report = {"folder": str(folder), "steps": []}
    owned = []

    def cast(obj, interface):
        packed = bridge.cast(k, k.pack(obj)["handle"], "kAPI7", interface)
        return k.handles[packed["handle"]]

    def transfer(obj, interface):
        return cast(k.app.TransferInterface(obj, k.constants["ksAPI7Dual"], 0), interface)

    try:
        report["version"] = k.connect()["version"]
        did = k.new_document("Sheet metal bridge acceptance")["document_id"]
        doc = k.document(did)
        owned.append(doc)
        sketch_id = k.sketch(
            did,
            SketchSpec(
                name="Plate outline", curves=[Polyline(points=[(0, 0), (60, 0), (60, 40), (0, 40)])]
            ),
        )["sketch_id"]
        part7 = transfer(doc.GetPart(-1), "IPart7")
        container = cast(part7, "ISheetMetalContainer")
        body = container.SheetMetalBodies.Add()
        body.Name = "Native sheet 2 mm"
        body.Sketch = transfer(k.entity(did, sketch_id), "ISketch")
        body.Thickness = 2.0
        body.Radius = 2.0
        body.ThicknessDirection = True
        assert body.Update(), "Sheet body Update rejected"
        measured = k.measure(did)
        report["steps"].append({"created": measured, "thickness": body.Thickness})
        assert measured["body_count"] == 1
        assert abs(measured["volume_mm3"] - 4800) < 1e-4, measured
        body.Thickness = 3.0
        assert body.Update(), "Thickness edit rejected"
        measured = k.measure(did)
        assert abs(measured["volume_mm3"] - 7200) < 1e-4, measured
        report["steps"].append({"edited": measured, "thickness": body.Thickness})
        path = folder / "sheet.m3d"
        k.save(did, str(path))
        assert doc.close(), "Close own saved document rejected"
        owned.remove(doc)
        rid = k.open_document(str(path))["document_id"]
        reopened = k.document(rid)
        owned.append(reopened)
        sheets = cast(
            transfer(reopened.GetPart(-1), "IPart7"), "ISheetMetalContainer"
        ).SheetMetalBodies
        restored = sheets.SheetMetalBody(0)
        measured = k.measure(rid)
        assert abs(restored.Thickness - 3) < 1e-8
        assert abs(measured["volume_mm3"] - 7200) < 1e-4
        report["steps"].append(
            {"reopened": measured, "thickness": restored.Thickness, "path": str(path)}
        )
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        for doc in owned:
            # Only documents created/opened by this acceptance run.
            try:
                doc.close()
            except (pythoncom.com_error, AttributeError, KeyError) as cleanup_error:
                print(f"Could not close owned test document: {cleanup_error}", flush=True)


if __name__ == "__main__":
    main()
