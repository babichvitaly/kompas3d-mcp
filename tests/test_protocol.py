import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


def test_stdio_schema_and_blueprint_image(tmp_path):
    source = tmp_path / "drawing.png"
    Image.new("RGB", (400, 200), "white").save(source)

    async def check():
        async with (
            stdio_client(
                StdioServerParameters(command=sys.executable, args=["-m", "kompas_mcp.server"],
                                      env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
            ) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert {
                "create_sketch",
                "revolve",
                "sdk_read",
                "api_invoke",
                "api_batch",
                "api_cast",
                "create_feature",
                "draw_linear_dimension",
                "set_variable",
                "audit_model",
                "read_audit_report",
                "check_collisions",
                "inspect_sketches",
                "constrain_sketch",
                "rebind_component_sources",
                "place_components",
                "runtime_health", "job_status", "cancel_job", "document_details",
                "close_documents", "inspect_drawing", "rebind_drawing_views",
                "export_drawing", "create_isolated_copy", "create_collision_fixture",
                "set_sketch_frame",
                "inspect_body_components",
            } <= tools.keys()
            assert tools["constrain_sketch"].inputSchema["properties"]["dry_run"]["default"] is True
            assert tools["rebind_component_sources"].inputSchema["properties"]["dry_run"]["default"] is True
            assert tools["place_components"].inputSchema["properties"]["dry_run"]["default"] is True
            result = await session.call_tool(
                "blueprint_view", {"path": str(source), "crop": [0, 0, 0.5, 1]}
            )
            assert not result.isError
            assert result.content[0].type == "image"
            result = await session.call_tool(
                "blueprint_view", {"path": str(source), "crop": [0.8, 0, 0.2, 1]}
            )
            assert result.isError
            result = await session.call_tool(
                "create_sketch",
                {"document_id": "unused", "spec": {"curves": [{"kind": "circle", "radius": -1}]}},
            )
            assert result.isError  # validation must not start KOMPAS
            result = await session.call_tool(
                "api_batch",
                {
                    "plan": {
                        "steps": [{"id": "bad", "target": {"ref": "future"}, "member": "Create"}]
                    }
                },
            )
            assert result.isError  # malformed batches must not perform their first mutation
            assert len((await session.list_prompts()).prompts) == 2

    asyncio.run(check())
