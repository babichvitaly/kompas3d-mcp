"""Live proof of editable sketch horizontal and length constraints via native API7."""

import json
import math
from pathlib import Path
from uuid import uuid4

from kompas_mcp.backend import Kompas, require
from kompas_mcp.documents import _cast
from kompas_mcp.models import SketchSpec


def main():
    k = Kompas()
    folder = Path(__file__).resolve().parents[1] / "artifacts" / f"constraints-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    document_id = k.new_document("Native sketch constraints acceptance")["document_id"]
    report = {}
    try:
        sketch = k.sketch(
            document_id,
            SketchSpec(curves=[{"kind": "polyline", "points": [[0, 0], [20, 5]], "closed": False}]),
        )
        definition = k.entity(document_id, sketch["sketch_id"]).GetDefinition()
        drawing = require(definition.BeginEdit(), "edit sketch")
        try:
            reference = drawing.ksLineSeg(40, 0, 60, 10, 1)
            line = _cast(k, k.app.TransferReference(reference, drawing.reference), "ILineSegment")
            extra = _cast(k, line, "IDrawingObject1")
            horizontal = extra.NewConstraint()
            horizontal.ConstraintType = k.constants["ksCHorizontal"]
            require(horizontal.Create(), "create horizontal constraint")
            assert horizontal.Valid and math.isclose(line.Y1, line.Y2)
            line.Length = 30
            require(line.Update(), "set line length before locking")
            length = extra.NewConstraint()
            length.ConstraintType = k.constants["ksCFixedLenght"]
            require(length.Create(), "create fixed length constraint")
            assert length.Valid and math.isclose(line.Length, 30)
            report["created"] = {
                "length": line.Length,
                "y1": line.Y1,
                "y2": line.Y2,
                "constraint_count": len(extra.Constraints),
            }
        finally:
            require(definition.EndEdit(), "end sketch edit")
        target = folder / "constrained.m3d"
        k.document(document_id).SaveAs(str(target))
        assert target.stat().st_size > 0
        k.document(document_id).close()
        document_id = k.open_document(str(target))["document_id"]
        collection = k.document(document_id).GetPart(-1).EntityCollection(k.constants["o3d_sketch"])
        definition = collection.GetByIndex(0).GetDefinition()
        drawing = require(definition.BeginEdit(), "reopen sketch edit")
        try:
            api7 = _cast(
                k,
                k.app.TransferInterface(drawing, k.constants["ksAPI7Dual"], 0),
                "IKompasDocument2D",
            )
            view = api7.ViewsAndLayersManager.Views.ActiveView
            lines = _cast(k, view, "IDrawingContainer").LineSegments
            candidates = [_cast(k, lines.Item(i), "ILineSegment") for i in range(lines.Count)]
            line = next(item for item in candidates if math.isclose(item.Length, 30))
            extra = _cast(k, line, "IDrawingObject1")
            constraints = extra.Constraints
            assert len(constraints) == 2
            assert math.isclose(line.Y1, line.Y2)
            assert {c.ConstraintType for c in constraints} == {
                k.constants["ksCHorizontal"],
                k.constants["ksCFixedLenght"],
            }
            report["reopened"] = {
                "length": line.Length,
                "y1": line.Y1,
                "y2": line.Y2,
                "constraint_count": len(constraints),
            }
        finally:
            require(definition.EndEdit(), "finish reopened sketch")
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"folder": str(folder), "report": report}, indent=2))
    finally:
        k.document(document_id).close()


if __name__ == "__main__":
    main()
