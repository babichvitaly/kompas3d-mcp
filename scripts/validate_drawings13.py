"""Opt-in real MCP/STA acceptance of synthetic drawing copies and native exports.

Run only in the same interactive user session as KOMPAS. Requires --run-native
and --output ABSOLUTE_NEW_DIRECTORY. No user document is adopted or changed.
The separate native oracle uses the new box's measured dimensions. Every old
source is hash protected. Module tests alone do not establish native acceptance.
"""

import argparse
import asyncio
import hashlib
import json
import math
import shutil
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kompas_mcp.runtime_tools import _code_fingerprint


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


def bounds(row):
    lines = row["geometry"]["lines"]
    assert len(lines) == 4, lines
    values = [min(line[key] for line in lines for key in ("X1", "X2")),
              min(line[key] for line in lines for key in ("Y1", "Y2")),
              max(line[key] for line in lines for key in ("X1", "X2")),
              max(line[key] for line in lines for key in ("Y1", "Y2"))]
    # Four distinct rectangle sides, rather than count/bounds alone.
    segments = {tuple(sorted(((round(line["X1"], 6), round(line["Y1"], 6)),
                              (round(line["X2"], 6), round(line["Y2"], 6))))) for line in lines}
    a, b, c, d = [round(value, 6) for value in values]
    expected = {tuple(sorted(pair)) for pair in [((a, b), (c, b)), ((c, b), (c, d)),
                                                 ((c, d), (a, d)), ((a, d), (a, b))]}
    assert segments == expected, (segments, expected)
    return values


def classify(inventory, thickness):
    result = {}
    expected = {"front": [80, 50], "top": [80, thickness], "left": [thickness, 50]}
    for row in inventory["views"]:
        if "association" not in row:
            continue
        box = bounds(row)
        size = [box[2]-box[0], box[3]-box[1]]
        matches = [role for role, values in expected.items()
                   if all(math.isclose(x, y, abs_tol=1e-6)
                          for x, y in zip(size, values, strict=True))]
        assert len(matches) == 1, size
        assert matches[0] not in result
        result[matches[0]] = row
    assert result.keys() == expected.keys()
    return result


def expected_dimension(oracle):
    """The native X3 is a text anchor affected by glyph width, not its centre."""
    system = next(row for row in oracle["views"] if row["Number"] == 0)
    assert len(system["dimensions"]) == 1
    dimension = system["dimensions"][0]
    assert dimension["text"]["AutoNominalValue"]
    assert dimension["text"]["NominalValue"] == 12.
    result = {key: dimension[key] for key in
              ("X1", "Y1", "X2", "Y2", "X3", "Y3", "Orientation")}
    result["NominalValue"] = dimension["text"]["NominalValue"]
    assert result["X1"] == 60. and result["X2"] == 72.
    return result


def expected_view_position(role, row):
    # A fresh AddStandartViews layout and regeneration do not position the
    # linked top view identically. This synthetic 8 -> 12-mm change preserves
    # its projected centre by moving Y by +2 sheet mm at scale 1, confirmed by
    # the retained native rejection report. The other placements stay fixed.
    # This is an explicit fixture expectation, not a general relaxation in the
    # production rebind tool and not a write to the native view position.
    return {"view_number": row["Number"], "expected_x": row["X"],
            "expected_y": row["Y"] + ((12.-8.)*row["Scale"]/2 if role == "top" else 0.)}


async def isolate_layout_resources(call, invoke, info, resource_dir):
    """Copy the native LYT resource and explicitly rebind the synthetic sheets.

    SDK ILayoutSheet.LayoutLibraryFileName is writable and requires Update.
    Preserve the exact style number, sheet type and every ISheetFormat setting;
    copied resource bytes must match the installed source. This prepares a fully
    isolated fixture instead of bypassing the production dependency guard.
    """
    drawing = await call("api_cast", handle=info["document"]["handle"],
                         interface="IKompasDocument2D")
    sheets = await invoke(drawing, "LayoutSheets", action="get")
    resources = []
    format_properties = ("Format", "FormatHeight", "FormatMultiplicity", "FormatWidth",
                         "VerticalOrientation")
    for index in range(await invoke(sheets, "Count", action="get")):
        sheet = await invoke(sheets, "Item", index)
        source = Path(await invoke(sheet, "LayoutLibraryFileName", action="get"))
        assert source.is_absolute() and source.is_file(), "Missing native layout resource"
        source = source.resolve()
        digest = sha(source)
        resource_dir.mkdir(parents=True, exist_ok=True)
        target = resource_dir / (digest[:16]+"-"+source.name)
        if target.exists():
            assert sha(target) == digest, "Existing resource copy has different bytes"
        else:
            shutil.copy2(source, target)
        assert sha(source) == sha(target) == digest
        style = await invoke(sheet, "LayoutStyleNumber", action="get")
        sheet_type = await invoke(sheet, "SheetType", action="get")
        native_format = await invoke(sheet, "Format", action="get")
        before = {key: await invoke(native_format, key, action="get") for key in format_properties}
        await invoke(sheet, "LayoutLibraryFileName", action="set", value=str(target))
        assert await invoke(sheet, "Update"), "Native sheet resource update failed"
        native_format = await invoke(sheet, "Format", action="get")
        after = {key: await invoke(native_format, key, action="get") for key in format_properties}
        assert before == after, "Sheet format changed while isolating its style library"
        assert await invoke(sheet, "LayoutStyleNumber", action="get") == style
        assert await invoke(sheet, "SheetType", action="get") == sheet_type
        assert Path(await invoke(sheet, "LayoutLibraryFileName", action="get")).samefile(target)
        resources.append({"source": str(source), "copy": str(target), "sha256": digest,
                          "sheet_index": index, "style_number": style, "sheet_type": sheet_type,
                          "format_before": before, "format_after": after})
    return resources


async def close_owned_document(call, info, path=None, discard_changes=False):
    """Fresh identity plus observed absence, without blindly retrying False."""
    original_handle = info["document"]["handle"]

    def matches(listed):
        if path is None:
            return [row for row in listed if row["document"]["handle"] == original_handle]
        return [row for row in listed if row["path"]
                and Path(row["path"]).resolve() == Path(path).resolve()]

    before = matches((await call("list_documents", details=False))["documents"])
    receipt = {"path": str(path) if path else None, "original_handle": original_handle,
               "native_close_attempted": False, "absent_before_call": not before}
    if not before:
        receipt["absence_confirmed"] = True
        return receipt
    if len(before) != 1:
        raise RuntimeError("Owned synthetic close is ambiguous: multiple documents use one path")
    if before[0]["changed"] and not discard_changes:
        raise RuntimeError("Owned synthetic document has unsaved changes before checked close")
    handle = before[0]["document"]["handle"]
    receipt.update(native_close_attempted=True, actual_handle=handle)
    try:
        receipt["native_result"] = await call("close_document", handle=handle,
                                              discard_changes=discard_changes)
    except Exception as exc:  # noqa: BLE001 - reconcile native state before interpreting failure
        receipt["native_error"] = str(exc)
    after = matches((await call("list_documents", details=False))["documents"])
    receipt["absence_confirmed"] = not after
    if after:
        raise RuntimeError("Owned synthetic close remains unconfirmed; no automatic retry: "
                           +receipt.get("native_error", "document is still live"))
    return receipt


async def validate(output):
    output.mkdir(parents=True, exist_ok=False)
    src = Path(__file__).resolve().parents[1] / "src"
    report = {"schema": 1, "status": "running", "scope": "synthetic native drawing acceptance"}
    report_path = output / "drawings13-native-acceptance.json"
    owned = set()
    owned_paths, close_attempted = {}, set()
    server = StdioServerParameters(command=sys.executable,
                                  args=["-X", "utf8", "-m", "kompas_mcp.server"],
                                  env={"PYTHONPATH": str(src)})
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(name, **arguments):
            value = await session.call_tool(name, arguments,
                                            read_timeout_seconds=timedelta(seconds=300))
            if value.isError:
                raise RuntimeError(f"{name}: {value.content}")
            result = value.structuredContent
            if result is None:
                result = json.loads(value.content[0].text)
            return result["result"] if isinstance(result, dict) and "result" in result else result

        async def invoke(obj, member, *args, action="call", value=None):
            arguments = {"handle": obj["handle"], "member": member, "action": action}
            if action == "set":
                arguments["value"] = value
            elif action == "call":
                arguments["arguments"] = list(args)
            return await call("api_invoke", **arguments)

        async def open_owned(path):
            app = (await call("connect"))["application7"]
            previous = await invoke(app, "HideMessage", action="get")
            try:
                await invoke(app, "HideMessage", action="set", value={"constant": "ksHideMessageNo"})
                info = await call("open_document", path=str(path), visible=False)
            finally:
                await invoke(app, "HideMessage", action="set", value=previous)
            assert not info.get("reused"), "Synthetic destination unexpectedly open"
            owned.add(info["document"]["handle"])
            owned_paths[info["document"]["handle"]] = path
            return info

        async def save(info, path):
            result = await call("save_document", handle=info["document"]["handle"],
                                path=str(path), overwrite=path.exists())
            owned_paths[info["document"]["handle"]] = path
            return result

        async def close(info, discard_changes=False):
            handle = info["document"]["handle"]
            close_attempted.add(handle)
            receipt = await close_owned_document(call, info, owned_paths.get(handle), discard_changes)
            report.setdefault("close_receipts", []).append(receipt)
            owned.remove(handle)

        async def box(path, thickness):
            part = await call("create_document", kind="part", visible=False)
            owned.add(part["document"]["handle"])
            sketch = await call("create_sketch", document_id=part["document_id"], spec={
                "plane": "XY", "name": "Rectangle", "curves": [{"kind": "polyline",
                "points": [[0, 0], [80, 0], [80, 50], [0, 50]], "closed": True}]})
            await call("extrude", document_id=part["document_id"], spec={
                "sketch_id": sketch["sketch_id"], "depth": thickness, "name": "Box"})
            state = await call("inspect_model", document_id=part["document_id"])
            assert state["measurements"]["body_count"] == 1
            assert math.isclose(state["measurements"]["volume_mm3"], 80*50*thickness, abs_tol=1e-5)
            await save(part, path)
            await close(part)
            return state

        async def drawing(path, model):
            info = await call("create_document", kind="drawing", visible=False)
            owned.add(info["document"]["handle"])
            resources = await isolate_layout_resources(call, invoke, info, output / "resources")
            report.setdefault("layout_resources", []).extend(resources)
            dump(report_path, report)
            made = await call("create_standard_views", drawing_handle=info["document"]["handle"],
                              model_path=str(model), projections=["front", "top", "left"],
                              x=60, y=180, scale=1., gap_x=30., gap_y=30.)
            assert made["created_count"] == 3
            await save(info, path)
            return info

        try:
            report["runtime"] = await call("runtime_health")
            health = report["runtime"]
            assert health["runtime_revision"] == "13" and not health["reconnect_required"]
            assert health["loaded_code_fingerprint"] == _code_fingerprint(), "Wrong MCP source loaded"
            required = {"inspect_drawing", "rebind_drawing_views", "export_drawing"}
            assert required <= set(health["tool_names"]), "Wrong MCP schema loaded"
            dump(report_path, report)
            print("SYNTHETIC BOX SOURCES", flush=True)
            old_model, new_model = output / "old-box.m3d", output / "new-box.m3d"
            report["old_model"] = await box(old_model, 8.)
            report["new_model"] = await box(new_model, 12.)
            protected = {str(path): sha(path) for path in (old_model, new_model)}
            old_drawing = output / "original.cdw"
            info = await drawing(old_drawing, old_model)
            await call("draw_text", drawing_handle=info["document"]["handle"],
                       text="Synthetic editable note; preserve this", x=30., y=80.)
            await call("draw_linear_dimension", drawing_handle=info["document"]["handle"],
                       x1=60., y1=110., x2=68., y2=110., text_x=64., text_y=100.,
                       orientation="horizontal")
            await save(info, old_drawing)
            await close(info)
            protected[str(old_drawing)] = sha(old_drawing)
            working = output / "working-copy.cdw"
            shutil.copy2(old_drawing, working)
            info = await open_owned(working)
            before = await call("inspect_drawing", handle=info["document"]["handle"])
            roles = classify(before, 8.)
            report["before"] = before
            oracle_path = output / "new-source-oracle.cdw"
            oracle = await drawing(oracle_path, new_model)
            await call("draw_linear_dimension", drawing_handle=oracle["document"]["handle"],
                       x1=60., y1=110., x2=72., y2=110., text_x=66., text_y=100.,
                       orientation="horizontal")
            # Settle native text layout independently, including the width of
            # the two-digit nominal, before planning the working copy update.
            await save(oracle, oracle_path)
            await close(oracle)
            oracle = await open_owned(oracle_path)
            target = await call("inspect_drawing", handle=oracle["document"]["handle"])
            targets = classify(target, 12.)
            report["oracle"] = target
            await close(oracle)
            replacements, checks, shifts = [], [], []
            for role, row in roles.items():
                number = row["Number"]
                replacements.append({"view_number": number, "expected_source": str(old_model),
                                     "source": str(new_model)})
                checks.append({"view_number": number, "line_bounds": bounds(targets[role]),
                               "line_count": 4, "different_from_before": role != "front"})
                shifts.append(expected_view_position(role, row))
            system = next(row for row in before["views"] if row["Number"] == 0)
            dimension = system["dimensions"][0]
            after_dim = expected_dimension(target)
            changes = [{"view_number": 0, "index": 0, "expected": dimension,
                        "endpoints": {"X2": 72.}, "expected_after": after_dim}]
            arguments = {"handle": info["document"]["handle"], "copy_root": str(output),
                         "replacements": replacements, "expected_fingerprint": before["fingerprint"],
                         "dimension_changes": changes, "view_changes": shifts,
                         "geometry_checks": checks,
                         "remove_new_auto_captions": [row["Number"] for row in roles.values()]}
            report["dry_run"] = await call("rebind_drawing_views", **arguments)
            unchanged = await call("inspect_drawing", handle=info["document"]["handle"])
            assert unchanged["fingerprint"] == before["fingerprint"]
            print("REBIND THREE EXISTING VIEWS AND ONE COORDINATE DIMENSION", flush=True)
            report["rebind"] = await call("rebind_drawing_views", **arguments, dry_run=False,
                                          report_path=str(output / "native-rebind.json"))
            dump(report_path, report)
            applied = report["rebind"]["after"]
            assert report["rebind"]["native_content_preserved"]
            await save(info, working)
            await close(info)
            info = await open_owned(working)
            reopened = await call("inspect_drawing", handle=info["document"]["handle"])
            report["reopened"] = reopened
            classify(reopened, 12.)
            assert applied["sheets"] == reopened["sheets"]
            for row in reopened["views"]:
                previous = next(item for item in applied["views"] if item["Number"] == row["Number"])
                assert previous["geometry_digest"] == row["geometry_digest"]
                assert [text["text"] for text in previous["texts"]] == [text["text"] for text in row["texts"]]
                assert [dim["text"]["NominalValue"] for dim in previous["dimensions"]] == [
                    dim["text"]["NominalValue"] for dim in row["dimensions"]]
                if "association" in row:
                    assert Path(row["association"]["SourceFileName"]).samefile(new_model)
            report["reopen_passed"] = True
            print("NATIVE PDF/DXF EXPORT AND STRUCTURAL PARSING", flush=True)
            report["exports"] = await call("export_drawing", handle=info["document"]["handle"],
                                            copy_root=str(output),
                                            paths=[str(output / "working.pdf"), str(output / "working.dxf")],
                                            report_path=str(output / "native-export.json"))
            assert report["exports"]["phase"] == "exported_structurally_valid"
            previous_handle = info["document"]["handle"]
            info = report["exports"]["document_after_export"]
            owned.discard(previous_handle)
            owned.add(info["document"]["handle"])
            owned_paths[info["document"]["handle"]] = working
            assert protected == {path: sha(path) for path in protected}
            assert all(sha(resource["source"]) == sha(resource["copy"]) == resource["sha256"]
                       for resource in report["layout_resources"])
            report.update(status="accepted", protected_originals_unchanged=True,
                          visual_review_required=True)
            dump(report_path, report)
            await close(info)
            print(json.dumps({"status": report["status"], "report": str(report_path)}, ensure_ascii=False), flush=True)
        except Exception as exc:
            report.update(status="failed", error=str(exc))
            dump(report_path, report)
            raise
        finally:
            # Only handles explicitly created/opened by this synthetic run. A
            # failed run may have partial changes; these are all unique copies.
            for handle in list(owned-close_attempted):
                try:
                    await close({"document": {"handle": handle}}, discard_changes=True)
                except Exception as exc:  # noqa: BLE001 - retain cleanup errors without masking failure
                    report.setdefault("cleanup_errors", []).append(str(exc))
            if owned:
                report["left_for_inspection"] = [str(owned_paths.get(handle, handle)) for handle in owned]
            dump(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.run_native or not args.output.is_absolute() or args.output.exists():
        parser.error("Supply --run-native and a new absolute --output directory")
    asyncio.run(validate(args.output.resolve()))


if __name__ == "__main__":
    main()
