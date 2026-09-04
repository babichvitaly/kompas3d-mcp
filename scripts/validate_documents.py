"""Live API7 lifecycle acceptance. Creates unique artifacts, closes only its own docs."""

import json
from pathlib import Path
from uuid import uuid4

from kompas_mcp import documents
from kompas_mcp.backend import Kompas


def main():
    import pythoncom

    pythoncom.CoInitialize()
    k = Kompas()
    folder = Path(__file__).resolve().parents[1] / "artifacts" / f"documents-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    report = []
    handles = []
    try:
        for kind in documents.KINDS:
            created = documents.create_document(k, kind)
            handle = created["document"]["handle"]
            handles.append(handle)
            if kind in {"part", "assembly"}:
                assert k.measure(created["document_id"])["body_count"] == 0
            extension = documents.KINDS[kind][1]
            result = documents.save_document(k, handle, str(folder / f"{kind}{extension}"))
            assert result["bytes"] > 0
            documents.close_document(k, handle)
            handles.remove(handle)
            reopened = documents.open_document(k, result["path"])
            handle = reopened["document"]["handle"]
            handles.append(handle)
            assert reopened["kind"] == kind
            documents.close_document(k, handle)
            handles.remove(handle)
            report.append({"kind": kind, **result})
        assembly = documents.open_document(k, str(folder / "assembly.a3d"))
        handle = assembly["document"]["handle"]
        handles.append(handle)
        part_sources = sorted((folder.parent).glob("acceptance-*/plate.m3d"))
        if part_sources:
            inserted = documents.insert_component(k, handle, str(part_sources[-1]))
            documents.save_document(k, handle, str(folder / "with-component.a3d"))
            report.append({"inserted": inserted})
        documents.close_document(k, handle, discard_changes=True)
        handles.remove(handle)
        if part_sources:
            drawing = documents.open_document(k, str(folder / "drawing.cdw"))
            handle = drawing["document"]["handle"]
            handles.append(handle)
            views = documents.create_standard_views(
                k, handle, str(part_sources[-1]), ["front", "top", "left"]
            )
            assert views["count_after"] - views["count_before"] == 3
            line = documents.draw_line(k, handle, 30, 30, 80, 30)
            assert line["length_mm"] == 50
            circle = documents.draw_circle(k, handle, 50, 60, 10)
            assert circle["radius_mm"] == 10
            dimension = documents.draw_linear_dimension(k, handle, 30, 30, 80, 30, 55, 20)
            assert dimension["nominal_value"] == 50
            text = documents.draw_text(k, handle, "Native editable text", 30, 90)
            assert text["text"] == "Native editable text"
            documents.save_document(k, handle, str(folder / "model-views.cdw"))
            documents.close_document(k, handle)
            handles.remove(handle)
            reopened = documents.open_document(k, str(folder / "model-views.cdw"))
            handle = reopened["document"]["handle"]
            handles.append(handle)
            assert k.handles[reopened["views"]["handle"]].Count == views["count_after"]
            view = documents._drawing_view(k, handle, 0)
            geometry = documents._cast(k, view, "IDrawingContainer")
            symbols = documents._cast(k, view, "ISymbols2DContainer")
            assert geometry.LineSegments.Count == 1
            assert geometry.Circles.Count == 1
            assert geometry.DrawingTexts.Count == 1
            assert symbols.LineDimensions.Count == 1
            documents.close_document(k, handle)
            handles.remove(handle)
            report.append({"associative_views": views})
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"folder": str(folder), "results": report}, indent=2))
    finally:
        for handle in handles:
            documents.close_document(k, handle, discard_changes=True)


if __name__ == "__main__":
    main()
