"""Live MCP acceptance for topology, feature editing, shells, lofts and API7 batches."""

import asyncio
import json
import math
import sys
from pathlib import Path
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    output = (Path("artifacts") / f"advanced-{uuid4().hex[:8]}").resolve()
    output.mkdir(parents=True)
    report = {}
    async with (
        stdio_client(
            StdioServerParameters(command=sys.executable, args=["-m", "kompas_mcp.server"])
        ) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        async def call(tool, **args):
            result = await session.call_tool(tool, args)
            if result.isError:
                raise RuntimeError(f"{tool}: {result.content}")
            value = json.loads(result.content[0].text)
            # JsonValue-returning generic tools are wrapped as result by FastMCP.
            return value.get("result", value) if isinstance(value, dict) else value

        await call("connect")

        async def plate(name):
            d = (await call("create_part", name=name))["document_id"]
            s = await call(
                "create_sketch",
                document_id=d,
                spec={
                    "curves": [{"kind": "polyline", "points": [[0, 0], [80, 0], [80, 50], [0, 50]]}]
                },
            )
            await call("extrude", document_id=d, spec={"sketch_id": s["sketch_id"], "depth": 8})
            return d

        async def persist(d, name, expected):
            info = await call("inspect_model", document_id=d)
            assert math.isclose(info["measurements"]["volume_mm3"], expected, rel_tol=1e-7), info
            path = str(output / f"{name}.m3d")
            await call("save_model", document_id=d, path=path)
            await call("api_invoke", handle=info["document"]["handle"], member="close")
            d = (await call("open_model", path=path))["document_id"]
            info = await call("inspect_model", document_id=d)
            assert math.isclose(info["measurements"]["volume_mm3"], expected, rel_tol=1e-7)
            await call("api_invoke", handle=info["document"]["handle"], member="close")
            report[name] = info

        for kind in ("fillet", "chamfer"):
            d = await plate(f"MCP {kind} acceptance")
            es = await call("list_entities", document_id=d, kind="o3d_edge")
            assert es["total"] == 12, es
            chosen = [
                e["entity_id"]
                for e in es["entities"]
                if math.isclose(e["geometry"]["length_mm"], 8)
            ]
            assert len(chosen) == 4
            f = await call(
                "treat_edges", document_id=d, spec={"kind": kind, "edges": chosen, "size": 2}
            )
            expected = 32000 - (4 * (4 - math.pi) * 8 if kind == "fillet" else 4 * 2 * 8)
            assert math.isclose(f["measurements"]["volume_mm3"], expected, rel_tol=1e-8)
            if kind == "fillet":
                changed = await call(
                    "update_feature",
                    document_id=d,
                    entity_id=f["feature_id"],
                    settings={"properties": {"radius": 3}},
                )
                expected = 32000 - 9 * (4 - math.pi) * 8
                assert math.isclose(changed["measurements"]["volume_mm3"], expected, rel_tol=1e-8)
                await call(
                    "set_entity_state", document_id=d, entity_id=f["feature_id"], excluded=True
                )
                suppressed = await call("inspect_model", document_id=d)
                assert math.isclose(suppressed["measurements"]["volume_mm3"], 32000, rel_tol=1e-8)
                await call(
                    "set_entity_state", document_id=d, entity_id=f["feature_id"], excluded=False
                )
            await persist(d, kind, expected)

        d = await plate("MCP shell acceptance")
        faces = await call("list_entities", document_id=d, kind="o3d_face")
        assert faces["total"] == 6
        top = [f for f in faces["entities"] if f["geometry"]["bounds_raw"][3] == 8]
        assert len(top) == 1
        await call(
            "create_feature",
            document_id=d,
            entity_type="o3d_shellOperation",
            name="2mm open shell",
            settings={
                "properties": {"thickness": 2, "thinType": True},
                "calls": [
                    {
                        "via": ["FaceArray"],
                        "member": "Add",
                        "arguments": [{"entity_id": top[0]["entity_id"]}],
                    }
                ],
            },
        )
        await persist(d, "shell", 32000 - 76 * 46 * 6)

        d = (await call("create_part", name="MCP loft acceptance"))["document_id"]
        ids = []
        for z, r in [(0, 10), (30, 5)]:
            s = await call(
                "create_sketch",
                document_id=d,
                spec={"offset": z, "curves": [{"kind": "circle", "radius": r}]},
            )
            ids.append(s["sketch_id"])
        await call(
            "create_feature",
            document_id=d,
            entity_type="o3d_bossLoft",
            name="Conical loft",
            settings={
                "calls": [{"member": "SetLoftParam", "arguments": [False, False, True]}]
                + [
                    {"via": ["Sketchs"], "member": "Add", "arguments": [{"entity_id": i}]}
                    for i in ids
                ]
            },
        )
        await persist(d, "loft", math.pi * 30 / 3 * (100 + 50 + 25))

        doc = await call("create_document", kind="part")
        container = await call(
            "api_cast", handle=doc["top_part"]["handle"], interface="IModelContainer"
        )
        result = await call(
            "api_batch",
            plan={
                "steps": [
                    {
                        "id": "fillets",
                        "target": {"handle": container["handle"]},
                        "member": "Fillets",
                        "action": "get",
                        "expect": "not_null",
                    },
                    {
                        "id": "count",
                        "target": {"ref": "fillets"},
                        "member": "Count",
                        "action": "get",
                    },
                ]
            },
        )
        assert result["completed"] and result["results"]["count"] == 0, result
        failed = await call(
            "api_batch",
            plan={
                "steps": [
                    {
                        "id": "read",
                        "target": {"handle": container["handle"]},
                        "member": "Fillets",
                        "action": "get",
                    },
                    {"id": "fail", "target": {"ref": "read"}, "member": "NoSuchSDKMethod"},
                    {"id": "never", "target": {"ref": "read"}, "member": "Add"},
                ]
            },
        )
        assert (
            not failed["completed"]
            and failed["failed_step"] == "fail"
            and "never" not in failed["results"]
        )
        report["batch"] = {"success": result, "failure": failed}
        await call("close_document", handle=doc["document"]["handle"], discard_changes=True)
        report["catalog"] = await call("api_catalog", limit=1)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Advanced MCP acceptance passed: {output}")


if __name__ == "__main__":
    asyncio.run(main())
