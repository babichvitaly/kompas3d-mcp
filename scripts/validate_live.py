"""Explicit live acceptance run: creates test parts, saves artifacts, closes only its parts."""

import asyncio
import base64
import json
import math
import sys
from pathlib import Path
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    output = Path("artifacts") / f"acceptance-{uuid4().hex[:8]}"
    output.mkdir(parents=True)
    output = output.resolve()
    async with (
        stdio_client(
            StdioServerParameters(command=sys.executable, args=["-m", "kompas_mcp.server"])
        ) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        async def call(tool_name, **args):
            result = await session.call_tool(tool_name, args)
            if result.isError:
                raise RuntimeError(f"{tool_name}: {result.content}")
            return json.loads(result.content[0].text)

        await call("connect")
        report = {}
        for reverse in (False, True):
            d = (await call("create_part", name=f"MCP acceptance plate reverse={reverse}"))[
                "document_id"
            ]
            s = await call(
                "create_sketch",
                document_id=d,
                spec={
                    "curves": [{"kind": "polyline", "points": [[0, 0], [80, 0], [80, 50], [0, 50]]}]
                },
            )
            await call(
                "extrude",
                document_id=d,
                spec={"sketch_id": s["sketch_id"], "depth": 8, "reverse": reverse},
            )
            s = await call(
                "create_sketch",
                document_id=d,
                spec={"curves": [{"kind": "circle", "center": [20, 25], "radius": 5}]},
            )
            await call(
                "extrude",
                document_id=d,
                spec={
                    "sketch_id": s["sketch_id"],
                    "depth": 8,
                    "operation": "cut",
                    "reverse": reverse,
                },
            )
            info = await call("inspect_model", document_id=d)
            expected = 80 * 50 * 8 - math.pi * 25 * 8
            assert math.isclose(info["measurements"]["volume_mm3"], expected, rel_tol=1e-8)
            assert info["measurements"]["body_count"] == 1
            bounds = info["bounds_raw"][1:]
            assert bounds == ([0, 0, -8, 80, 50, 0] if reverse else [0, 0, 0, 80, 50, 8])
            name = "plate-reverse" if reverse else "plate"
            await call("save_model", document_id=d, path=str(output / f"{name}.m3d"))
            if not reverse:
                for ext in ("step", "stl", "igs"):
                    await call("export_model", document_id=d, path=str(output / f"{name}.{ext}"))
                for prop in ("hideAllPlanes", "hideAllSketches"):
                    await call(
                        "api_invoke",
                        handle=info["document"]["handle"],
                        member=prop,
                        action="set",
                        value=True,
                    )
                result = await session.call_tool("model_preview", {"document_id": d})
                assert not result.isError
                (output / "plate.png").write_bytes(base64.b64decode(result.content[0].data))
            report[name] = info
            await call("api_invoke", handle=info["document"]["handle"], member="close")
            reopened = (await call("open_model", path=str(output / f"{name}.m3d")))["document_id"]
            again = await call("inspect_model", document_id=reopened)
            assert math.isclose(again["measurements"]["volume_mm3"], expected, rel_tol=1e-8)
            await call("api_invoke", handle=again["document"]["handle"], member="close")

        d = (await call("create_part", name="MCP acceptance shaft"))["document_id"]
        s = await call(
            "create_sketch",
            document_id=d,
            spec={
                "curves": [
                    {"kind": "polyline", "points": [[0, 0], [10, 0], [10, 30], [0, 30]]},
                    {
                        "kind": "polyline",
                        "points": [[0, -5], [0, 35]],
                        "closed": False,
                        "construction": True,
                    },
                ]
            },
        )
        await call("revolve", document_id=d, spec={"sketch_id": s["sketch_id"]})
        info = await call("inspect_model", document_id=d)
        assert math.isclose(info["measurements"]["volume_mm3"], math.pi * 100 * 30, rel_tol=1e-8)
        await call("save_model", document_id=d, path=str(output / "shaft.m3d"))
        await call("api_invoke", handle=info["document"]["handle"], member="close")
        report["shaft"] = info
        docs = await call("sdk_search", query="kscutextrusiondefinition_directiontype")
        assert docs["topics"]
        assert (await call("sdk_read", topic=docs["topics"][0]))["text"]
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Live MCP acceptance passed. Artifacts: {output}")


if __name__ == "__main__":
    asyncio.run(main())
