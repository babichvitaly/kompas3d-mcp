"""Opt-in real stdio/STA acceptance using synthetic native files only.

Run with the intended copy's src in PYTHONPATH. Nothing connects to COM on
import. --run-native --output ABSOLUTE_NEW_FOLDER is required; no user document
is attached, saved or closed. Report every native result before assertions.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kompas_mcp.audit import IDENTITY
from kompas_mcp.sketch_frame import compare_frame


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_report(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def validate(output):
    output.mkdir(parents=True, exist_ok=False)
    source = output / "sources"
    source.mkdir()
    report = {"schema": 1, "mode": "synthetic real stdio/STA acceptance", "status": "running"}
    report_path = output / "geometry13-native-acceptance.json"
    owned = set()
    async with stdio_client(StdioServerParameters(
            command=sys.executable, args=["-X", "utf8", "-m", "kompas_mcp.server"],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {tool.name for tool in (await session.list_tools()).tools}
        required = {"create_isolated_copy", "create_collision_fixture", "set_sketch_frame"}
        if not required <= names:
            raise RuntimeError(f"Wrong MCP source/runtime; missing geometry13 tools: {required - names}")
        report["registered_tools"] = sorted(names)

        async def call(tool_name, **arguments):
            result = await session.call_tool(tool_name, arguments, read_timeout_seconds=timedelta(seconds=300))
            if result.isError:
                raise RuntimeError(f"{tool_name}: {result.content}")
            value = result.structuredContent
            if value is None:
                value = json.loads(result.content[0].text)
            if isinstance(value, dict) and "result" in value:
                value = value["result"]
            return value

        async def open_owned(path):
            info = await call("open_document", path=str(path), visible=False)
            if info.get("reused"):
                raise RuntimeError("Synthetic destination unexpectedly already open")
            owned.add(info["document"]["handle"])
            return info

        async def close_owned(info):
            handle = info["document"]["handle"]
            if handle in owned:
                await call("close_document", handle=handle, discard_changes=False)
                owned.remove(handle)

        async def save_owned(info, path):
            return await call("save_document", handle=info["document"]["handle"], path=str(path), overwrite=Path(path).exists())

        async def assembly(path, components, placements):
            info = await call("create_document", kind="assembly", visible=False)
            owned.add(info["document"]["handle"])
            await save_owned(info, path)
            for component in components:
                await call("insert_component", assembly_handle=info["document"]["handle"], path=str(component))
            changes = [{"index": i, "expected": list(IDENTITY), "matrix": value}
                       for i, value in enumerate(placements)]
            placed = await call("place_components", handle=info["document"]["handle"], copy_root=str(source), placements=changes, dry_run=False)
            await save_owned(info, path)
            await close_owned(info)
            return placed

        try:
            print("CREATE SYNTHETIC PART", flush=True)
            part_path = source / "plate.m3d"
            inner_path = source / "inner.a3d"
            root_path = source / "root.a3d"
            part = await call("create_document", kind="part", visible=False)
            owned.add(part["document"]["handle"])
            sketch = await call("create_sketch", document_id=part["document_id"], spec={
                "name": "FrameProbe", "plane": "XY", "curves": [{"kind": "polyline",
                "points": [[0, 0], [12, 0], [12, 8], [0, 8]], "closed": True}]})
            await call("extrude", document_id=part["document_id"], spec={
                "sketch_id": sketch["sketch_id"], "depth": 3, "name": "Plate"})
            report["source_part"] = await call("inspect_model", document_id=part["document_id"])
            await save_owned(part, part_path)
            await close_owned(part)
            a, b = list(IDENTITY), list(IDENTITY)
            b[12] = 5
            report["inner_placement"] = await assembly(inner_path, [part_path, part_path], [a, b])
            parent = [0., 1., 0., 0., -1., 0., 0., 0., 0., 0., 1., 0., 100., 200., 0., 1.]
            report["root_placement"] = await assembly(root_path, [inner_path], [parent])
            source_hashes = {str(p): sha(p) for p in (part_path, inner_path, root_path)}

            print("DEPENDENCY CLOSURE / DRY RUN / REOPEN", flush=True)
            root_info = await open_owned(root_path)
            isolated = output / "isolated"
            report["copy_plan"] = await call("create_isolated_copy", handle=root_info["document"]["handle"], destination=str(isolated))
            assert not isolated.exists(), "Dry run wrote a destination"
            report["copy"] = await call("create_isolated_copy", handle=root_info["document"]["handle"], destination=str(isolated), dry_run=False)
            save_report(report_path, report)
            assert report["copy"]["status"] == "passed", report["copy"]
            assert report["copy"]["source_count"] == 3
            assert report["copy"]["persistence_verified"] and report["copy"]["originals_unchanged"]
            await close_owned(root_info)
            copied_part = next(Path(row["copy"]) for row in report["copy"]["files"] if Path(row["source"]) == part_path)

            print("SKETCH FRAME / GETPOINT3D / SAVE-REOPEN", flush=True)
            part = await open_owned(copied_part)
            arguments = {"handle": part["document"]["handle"], "copy_root": str(isolated),
                         "name": "FrameProbe", "translation": [7., 13.], "angle": 35.}
            report["frame_plan"] = await call("set_sketch_frame", **arguments)
            report["frame"] = await call("set_sketch_frame", **arguments,
                                         expected_frame=report["frame_plan"]["before"], dry_run=False)
            save_report(report_path, report)
            assert report["frame"]["status"] == "passed", report["frame"]
            report["rotated_part"] = await call("inspect_model", document_id=part["document_id"])
            assert abs(report["rotated_part"]["measurements"]["volume_mm3"] - 288) < 1e-5
            await save_owned(part, copied_part)
            await close_owned(part)
            part = await open_owned(copied_part)
            arguments["handle"] = part["document"]["handle"]
            report["frame_reopened"] = await call("set_sketch_frame", **arguments)
            compare_frame(report["frame"]["target"], report["frame_reopened"]["before"])
            await close_owned(part)

            print("NESTED OCCURRENCES / SAVED TOP-LEVEL FIXTURE", flush=True)
            root_info = await open_owned(report["copy"]["root"])
            fixture_path = isolated / "fixture.a3d"
            args = {"handle": root_info["document"]["handle"], "copy_root": str(isolated),
                    "destination": str(fixture_path), "occurrence_paths": [[0, 0], [0, 1]]}
            report["fixture_plan"] = await call("create_collision_fixture", **args)
            assert not fixture_path.exists()
            report["fixture"] = await call("create_collision_fixture", **args, dry_run=False)
            save_report(report_path, report)
            assert report["fixture"]["status"] == "passed", report["fixture"]
            assert report["fixture"]["persistence_verified"]
            matrices = [row["local_to_root"] for row in report["fixture"]["occurrences"]]
            assert matrices[0][12:15] == [100, 200, 0] and matrices[1][12:15] == [100, 205, 0]
            await close_owned(root_info)
            fix = await open_owned(fixture_path)
            report["overlap_check"] = await call("check_collisions", handle=fix["document"]["handle"], copy_root=str(isolated), paths1=[[0]], paths2=[[1]])
            save_report(report_path, report)
            assert report["overlap_check"].get("collisions_count", 0) >= 1
            moved = list(matrices[1])
            moved[13] += 100
            await call("place_components", handle=fix["document"]["handle"], copy_root=str(isolated), placements=[
                {"index": 1, "expected": matrices[1], "matrix": moved}], dry_run=False)
            report["separated_check"] = await call("check_collisions", handle=fix["document"]["handle"], copy_root=str(isolated), paths1=[[0]], paths2=[[1]])
            assert report["separated_check"]["collisions_count"] == 0
            await save_owned(fix, fixture_path)
            await close_owned(fix)
            assert all(sha(p) == wanted for p, wanted in source_hashes.items())
            report.update(status="passed", source_hashes=source_hashes, originals_unchanged=True,
                          limits="Synthetic native acceptance only; no production model altered; "
                                 "collision endpoint attribution remains unproved")
            print("GEOMETRY13 NATIVE ACCEPTANCE PASSED", flush=True)
        except Exception as exc:
            report.update(status="failed", error=str(exc), remaining_owned_handles=sorted(owned))
            raise
        finally:
            # Never discard unsaved files on failure. Retain owned handles in the
            # report for an explicit reconciliation; no unknown document is closed.
            save_report(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.run_native:
        parser.error("--run-native is required; this script creates native synthetic documents")
    if not args.output.is_absolute() or args.output.exists():
        parser.error("--output must be a new absolute directory")
    asyncio.run(validate(args.output.resolve()))


if __name__ == "__main__":
    main()
