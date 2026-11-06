"""Synthetic live MCP acceptance; a new absolute output directory is mandatory.

Run interactively beside KOMPAS: uv run python scripts/validate_sketches.py C:/new/path
No existing documents are closed or saved. All mutations belong to created copies.
"""

import asyncio
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kompas_mcp.sketches import assert_same_geometry


def line(a, b):
    return {"kind": "polyline", "points": [a, b], "closed": False}


def arc(center, radius, start, end, ccw=True):
    return {"kind": "arc", "center": center, "radius": radius,
            "start_angle": start, "end_angle": end, "counterclockwise": ccw}


def cases():
    holes = [{"kind": "circle", "center": [x, y], "radius": 5}
             for x, y in [(0, 0), (40, 0), (0, 20), (40, 20)]]
    rounded = [line((5, 0), (75, 0)), arc((75, 5), 5, 270, 0),
               line((80, 5), (80, 45)), arc((75, 45), 5, 0, 90),
               line((75, 50), (5, 50)), arc((5, 45), 5, 90, 180),
               line((0, 45), (0, 5)), arc((5, 5), 5, 180, 270)]
    bent = [line((24, 0), (5, 0)), arc((5, 5), 5, 270, 180, False),
            line((0, 5), (0, 45)), line((0, 45), (2, 45)),
            line((2, 45), (2, 5)), arc((5, 5), 3, 180, 270),
            line((5, 2), (24, 2)), line((24, 2), (24, 0))]
    slot = [line((-4, -6), (4, -6)), arc((4, 0), 6, 270, 90),
            line((4, 6), (-4, 6)), arc((-4, 0), 6, 90, 270)]
    vertical = []
    for curve in slot:
        curve = dict(curve)
        if curve["kind"] == "polyline":
            curve["points"] = [(40-y, x) for x, y in curve["points"]]
        else:
            x, y = curve["center"]
            curve["center"] = (40-y, x)
            curve["start_angle"] = (curve["start_angle"]+90) % 360
            curve["end_angle"] = (curve["end_angle"]+90) % 360
        vertical.append(curve)
    return [("hole-grid", holes), ("rounded-profile", rounded), ("bend-profile", bent),
            ("semicircular-slots", slot+vertical)]


async def main():
    folder = Path(sys.argv[1])
    if not folder.is_absolute():
        raise ValueError("Use a new absolute output directory")
    folder.mkdir(parents=True, exist_ok=False)
    report = {"cases": []}
    async with stdio_client(StdioServerParameters(command=sys.executable,
        args=["-m", "kompas_mcp.server"])) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(tool, **args):
            r = await session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=180))
            if r.isError:
                raise RuntimeError(str(r.content))
            data = r.structuredContent
            if data is None:
                data = json.loads(r.content[0].text)
            return data["result"] if isinstance(data, dict) and "result" in data else data

        report["tools"] = [tool.name for tool in (await session.list_tools()).tools]
        for i, (name, curves) in enumerate(cases(), 1):
            item = {"name": name}
            report["cases"].append(item)
            info = await call("create_document", kind="part", visible=False)
            handle = info["document"]["handle"]
            target = folder / (name + ".m3d")
            try:
                doc_id = info["document_id"]
                sketch = await call("create_sketch", document_id=doc_id,
                                    spec={"name": name, "curves": curves})
                await call("extrude", document_id=doc_id,
                           spec={"sketch_id": sketch["sketch_id"], "depth": 3})
                await call("save_document", handle=handle, path=str(target))
                before = await call("inspect_model", document_id=doc_id)
                inventory = await call("inspect_sketches", handle=handle, copy_root=str(folder),
                                       names=[name])
                source = inventory["sketches"][0]["geometry"]
                item["result"] = await call("constrain_sketch", handle=handle,
                    copy_root=str(folder), name=name, expected_geometry=source,
                    prefix=f"C{i}", dry_run=False)
                after = await call("inspect_model", document_id=doc_id)
                assert before["bounds_raw"] == after["bounds_raw"]
                assert math.isclose(before["measurements"]["volume_mm3"],
                                    after["measurements"]["volume_mm3"], rel_tol=1e-10)
                item["audit_before_edit"] = await call("audit_model", handle=handle,
                    report_dir=str(folder / (name + "-before-edit-audit")))
                if name == "hole-grid":
                    driven = await call("set_variable", document_id=doc_id,
                        feature_id=sketch["sketch_id"], name="C1_D0", value=12)
                    delta = driven["measurements"]["volume_mm3"] - before["measurements"]["volume_mm3"]
                    assert math.isclose(delta, math.pi * 33, rel_tol=1e-9), delta
                    await call("set_variable", document_id=doc_id,
                        feature_id=sketch["sketch_id"], name="C1_D0", value=10)
                    item["diameter_edit_restore"] = {"values": [10, 12, 10],
                                                      "volume_delta_mm3": delta}
                if name == "semicircular-slots":
                    driven = await call("set_variable", document_id=doc_id,
                        feature_id=sketch["sketch_id"], name="C4_Y2", value=14)
                    delta = driven["measurements"]["volume_mm3"] - before["measurements"]["volume_mm3"]
                    assert math.isclose(delta, 3*(16+13*math.pi), rel_tol=1e-8), delta
                    await call("set_variable", document_id=doc_id,
                        feature_id=sketch["sketch_id"], name="C4_Y2", value=12)
                    item["slot_width_edit_restore"] = {"values": [12, 14, 12],
                                                       "volume_delta_mm3": delta}
                await call("save_document", handle=handle, path=str(target), overwrite=True)
                await call("close_document", handle=handle)
                handle = None
                reopened = await call("open_document", path=str(target), visible=False)
                handle = reopened["document"]["handle"]
                final = await call("inspect_sketches", handle=handle, copy_root=str(folder), names=[name])
                assert_same_geometry(source, final["sketches"][0]["geometry"])
                assert final["changed_before"] == final["changed_after"]
                assert final["sketches"][0]["constraints_state_before"] == 1
                assert final["sketches"][0]["constraints_state_after"] == 1
                item["reopened_inventory"] = final
                reopened_model = await call("inspect_model", document_id=reopened["document_id"])
                await call("api_invoke", handle=reopened_model["document"]["handle"],
                           member="RebuildDocument", action="call")
                item["audit"] = await call("audit_model", handle=handle,
                                            report_dir=str(folder / (name + "-audit")))
                assert item["audit"]["counts"].get("failed", 0) == 0
                item["fully_defined_after_reentry"] = item["audit"]["counts"].get("warning", 0) == 0
                item["passed"] = True
                print(name + " geometry passed; fully defined after reentry=" +
                      str(item["fully_defined_after_reentry"]), flush=True)
            finally:
                if handle:
                    await call("close_document", handle=handle, discard_changes=True)
                (folder / "report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        report["passed"] = True
        report["full_solver_acceptance"] = all(
            item["fully_defined_after_reentry"] for item in report["cases"])
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    asyncio.run(main())
