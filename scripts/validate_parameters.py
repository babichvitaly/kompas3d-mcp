"""Live variable acceptance: drive native geometry, save, reopen and measure again."""

import json
import math
from pathlib import Path
from uuid import uuid4

from kompas_mcp import parameters
from kompas_mcp.backend import Kompas
from kompas_mcp.models import ExtrusionSpec, SketchSpec


def main():
    k = Kompas()
    folder = Path(__file__).resolve().parents[1] / "artifacts" / f"parameters-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    document_id = k.new_document("Driving variables acceptance")["document_id"]
    report = []
    try:
        sketch = k.sketch(
            document_id,
            SketchSpec(
                curves=[{"kind": "polyline", "points": [[0, 0], [10, 0], [10, 10], [0, 10]]}]
            ),
        )
        feature = k.feature(document_id, ExtrusionSpec(sketch_id=sketch["sketch_id"], depth=8))
        feature_id = feature["feature_id"]
        variables = parameters.list_variables(k, document_id, feature_id)["variables"]
        depth = next(v["name"] for v in variables if v["value"] == 8)
        assert math.isclose(k.measure(document_id)["volume_mm3"], 800)
        result = parameters.set_variable(k, document_id, depth, value=20, feature_id=feature_id)
        assert math.isclose(result["measurements"]["volume_mm3"], 2000)
        report.append(result)
        parameters.set_variable(k, document_id, "height", value=30, create=True)
        assert any(
            v["name"] == "height" for v in parameters.list_variables(k, document_id)["variables"]
        )
        result = parameters.set_variable(
            k, document_id, depth, expression="height", feature_id=feature_id
        )
        assert math.isclose(result["measurements"]["volume_mm3"], 3000)
        report.append(result)
        target = folder / "driven.m3d"
        k.document(document_id).SaveAs(str(target))
        assert target.stat().st_size > 0
        k.document(document_id).close()
        document_id = k.open_document(str(target))["document_id"]
        assert math.isclose(k.measure(document_id)["volume_mm3"], 3000)
        result = parameters.set_variable(k, document_id, "height", value=40)
        assert math.isclose(result["measurements"]["volume_mm3"], 4000)
        report.append(result)
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"folder": str(folder), "report": report}, indent=2))
    finally:
        k.document(document_id).close()


if __name__ == "__main__":
    main()
