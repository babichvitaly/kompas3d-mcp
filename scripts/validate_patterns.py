"""Live native pattern acceptance through the document-scoped feature bridge."""

import json
import math
from pathlib import Path
from uuid import uuid4

from kompas_mcp import features
from kompas_mcp.advanced_models import DefinitionCall, FeatureSettings
from kompas_mcp.backend import Kompas
from kompas_mcp.models import Circle, ExtrusionSpec, Polyline, SketchSpec


def main():
    import pythoncom

    pythoncom.CoInitialize()
    k = Kompas()
    folder = Path(__file__).resolve().parents[1] / "artifacts" / f"patterns-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    report = {"folder": str(folder), "steps": []}
    owned = []
    try:
        report["version"] = k.connect()["version"]
        did = k.new_document("Native pattern bridge acceptance")["document_id"]
        doc = k.document(did)
        owned.append(doc)
        sid = k.sketch(
            did, SketchSpec(curves=[Polyline(points=[(-50, -25), (50, -25), (50, 25), (-50, 25)])])
        )["sketch_id"]
        k.feature(did, ExtrusionSpec(sketch_id=sid, depth=5))
        sid = k.sketch(did, SketchSpec(curves=[Circle(center=(-30, 10), radius=3)]))["sketch_id"]
        seed = k.feature(did, ExtrusionSpec(sketch_id=sid, operation="cut", depth=5))["feature_id"]
        linear = features.create(
            k,
            did,
            "o3d_meshCopy",
            "Three holes",
            FeatureSettings(
                properties={
                    "count1": 3,
                    "count2": 1,
                    "step1": 20,
                    "step2": 10,
                    "factor1": False,
                    "factor2": False,
                    "angle1": 0,
                    "angle2": 90,
                    "insideFlag": True,
                    "geomArray": False,
                },
                calls=[
                    DefinitionCall(
                        via=["OperationArray"], member="Add", arguments=[{"entity_id": seed}]
                    )
                ],
            ),
        )
        expected = 25000 - 3 * math.pi * 9 * 5
        assert abs(linear["measurements"]["volume_mm3"] - expected) < 1e-4, linear
        report["steps"].append({"linear": linear["measurements"], "holes": 3})
        plane = doc.GetPart(-1).GetDefaultEntity(k.constants["o3d_planeXOZ"])
        mirror = features.create(
            k,
            did,
            "o3d_mirrorOperation",
            "Six symmetric holes",
            FeatureSettings(
                calls=[
                    DefinitionCall(
                        member="SetPlane", arguments=[{"handle": k.pack(plane)["handle"]}]
                    ),
                    DefinitionCall(
                        via=["GetOperationArray"], member="Add", arguments=[{"entity_id": seed}]
                    ),
                    DefinitionCall(
                        via=["GetOperationArray"],
                        member="Add",
                        arguments=[{"entity_id": linear["feature_id"]}],
                    ),
                ]
            ),
        )
        expected = 25000 - 6 * math.pi * 9 * 5
        assert abs(mirror["measurements"]["volume_mm3"] - expected) < 1e-4, mirror
        report["steps"].append({"mirror": mirror["measurements"], "holes": 6})
        path = folder / "pattern.m3d"
        k.save(did, str(path))
        assert doc.close()
        owned.remove(doc)
        rid = k.open_document(str(path))["document_id"]
        owned.append(k.document(rid))
        measure = k.measure(rid)
        assert abs(measure["volume_mm3"] - expected) < 1e-4, measure
        assert measure["body_count"] == 1
        report["steps"].append({"reopened": measure, "path": str(path)})
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        for doc in owned:
            try:
                doc.close()
            except (pythoncom.com_error, AttributeError, KeyError) as exc:
                print(f"Could not close owned test document: {exc}", flush=True)


if __name__ == "__main__":
    main()
