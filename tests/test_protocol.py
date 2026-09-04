import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


def test_stdio_schema_and_blueprint_image(tmp_path):
    source = tmp_path / "drawing.png"
    Image.new("RGB", (400, 200), "white").save(source)

    async def check():
        async with (
            stdio_client(
                StdioServerParameters(command=sys.executable, args=["-m", "kompas_mcp.server"])
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
            } <= tools.keys()
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
