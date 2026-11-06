"""Opt-in installed-package smoke: MCP schemas and result contracts, never CAD.

Use a new output directory. This script does not connect to an application,
open a document, edit client configuration or certify model geometry.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


async def protocol_smoke():
    params = StdioServerParameters(command=sys.executable, args=["-m", "kompas_mcp.server"],
                                   env={**os.environ, "PYTHONUTF8": "1"})
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await asyncio.wait_for(session.initialize(), 20)
        tools = await session.list_tools()
        result = await session.call_tool("runtime_health", {})
        if result.isError:
            raise RuntimeError("runtime_health returned an MCP error")
        health = result.structuredContent
        if not isinstance(health, dict):
            health = json.loads(next(item.text for item in result.content if item.type == "text"))
        if health["worker"]["sta_initialized"] or health["worker"]["pending"]:
            raise RuntimeError("Schema smoke unexpectedly initialized/used CAD STA")
        names = {tool.name for tool in tools.tools}
        if names != set(health["tool_names"]) or health["tool_count"] != len(names):
            raise RuntimeError("Transport schemas and health fingerprints disagree")
        expected = {"inspect_drawing_view_state", "compare_drawing_view_state",
                    "find_visible_view_anchor", "runtime_health", "job_status"}
        if not expected <= names:
            raise RuntimeError("Expected runtime-14 tools are absent")
        return health


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    health = asyncio.run(protocol_smoke())
    write_json(output / "mcp-health.json", health)
    outcomes = []
    for phase, expected in (("failed_left_open", 1), ("complete_closed", 0), ("timed_out", 2)):
        source = output / f"{phase}.json"
        write_json(source, {"phase": phase})
        result = subprocess.run([sys.executable, "-m", "kompas_mcp.cli", "verify-result",
                                 str(source), "--launcher-returncode", "0"],
                                capture_output=True, text=True, check=False, timeout=15)
        if result.returncode != expected:
            raise RuntimeError(f"Result contract mismatch: {phase}, {result.returncode}")
        outcomes.append({"phase": phase, "exit_code": result.returncode,
                         "assessment": json.loads(result.stdout)})
    receipt = {"phase": "complete_closed", "scope": "installed wheel CLI/MCP; no CAD calls",
               "python": sys.version.split()[0], "version": health["package_version"],
               "tool_count": health["tool_count"], "schema_fingerprint": health["schema_fingerprint"],
               "code_fingerprint": health["loaded_code_fingerprint"],
               "STA_initialized": False, "CAD_geometry_verified": False, "cases": outcomes}
    write_json(output / "smoke-result.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "cases"}))


if __name__ == "__main__":
    main()
