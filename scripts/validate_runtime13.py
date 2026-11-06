"""Opt-in native runtime acceptance; keep every pre-existing document untouched.

Creates only empty synthetic parts, times metadata/detail reads and schema caches,
then closes only those exact synthetic handles. No user model is adopted/saved/
closed, and no unsaved document is discarded. Requires a new output directory.
"""

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kompas_mcp.runtime_tools import _code_fingerprint


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")


def canonical_schema(tools):
    rows = sorted([{"name": tool.name, "inputSchema": tool.inputSchema,
                    "outputSchema": getattr(tool, "outputSchema", None)} for tool in tools],
                  key=lambda row: row["name"])
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def unchanged_baseline(before, after):
    """Active focus may move; native identity, file and unsaved state must survive."""
    by_handle = {row["document"]["handle"]: row for row in after}
    for old in before:
        handle = old["document"]["handle"]
        if handle not in by_handle:
            raise RuntimeError(f"A baseline document disappeared: {old['name']}")
        current = by_handle[handle]
        for key in ("kind", "name", "path", "changed", "read_only", "visible", "owned_by_server"):
            if old[key] != current[key]:
                raise RuntimeError(f"Baseline document state changed: {old['name']}, {key}")
    return True


def timing_result(values):
    return {"samples_seconds": values, "min_seconds": min(values),
            "median_seconds": statistics.median(values), "max_seconds": max(values)}


async def validate(output, count=18):
    if not output.is_absolute() or output.exists() or not 15 <= count <= 20:
        raise ValueError("Use a new absolute output directory and count 15..20")
    output.mkdir(parents=True, exist_ok=False)
    parts = output / "synthetic-parts"
    parts.mkdir()
    report_path = output / "runtime13-native-acceptance.json"
    report = {"schema": 1, "status": "running", "synthetic_count": count,
              "scope": "Native runtime/document lifecycle only; no geometry certificate",
              "baseline_protection": "Never save/close/discard pre-existing documents",
              "calls": [], "cleanup": []}
    dump(report_path, report)
    source = Path(__file__).resolve().parents[1] / "src"
    server = StdioServerParameters(command=sys.executable,
                                  args=["-X", "utf8", "-m", "kompas_mcp.server"],
                                  env={"PYTHONPATH": str(source), "PYTHONUTF8": "1",
                                       "PYTHONIOENCODING": "utf-8"})
    baseline, synthetic, keep, closed = [], [], [], set()
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(tool_name, allow_error=False, **arguments):
            start = time.perf_counter()
            result = await session.call_tool(tool_name, arguments,
                                            read_timeout_seconds=timedelta(seconds=300))
            elapsed = time.perf_counter() - start
            report["calls"].append({"tool": tool_name, "seconds": elapsed,
                                     "is_error": bool(result.isError)})
            if result.isError:
                if allow_error:
                    return {"is_error": True,
                            "messages": [item.text for item in result.content
                                         if getattr(item, "type", "") == "text"]}
                raise RuntimeError(f"{tool_name}: {result.content}")
            value = result.structuredContent
            if value is None:
                value = json.loads(result.content[0].text)
            return value["result"] if isinstance(value, dict) and "result" in value else value

        async def summary():
            return (await call("list_documents", details=False))["documents"]

        async def ensure_clean_own(handle, index):
            rows = await summary()
            row = next((item for item in rows if item["document"]["handle"] == handle), None)
            if row is None or not row["owned_by_server"]:
                raise RuntimeError("A synthetic document is missing or no longer owned")
            if row["changed"]:
                saved = parts / f"empty-part-{index:02d}.m3d"
                # No discard: preserve even an unexpectedly dirty synthetic part.
                await call("save_document", handle=handle, path=str(saved), overwrite=False)
                report.setdefault("saved_synthetic_documents", []).append(str(saved))
                row = next(item for item in await summary()
                           if item["document"]["handle"] == handle)
            if row["changed"]:
                raise RuntimeError("Synthetic document is dirty after explicit save")
            return row

        try:
            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            required = {"runtime_health", "job_status", "cancel_job", "list_documents",
                        "document_details", "close_documents", "create_document", "api_describe"}
            if not required <= names:
                raise RuntimeError(f"Wrong server; missing runtime tools: {required - names}")
            health = await call("runtime_health")
            if (health["loaded_code_fingerprint"] != _code_fingerprint()
                    or health["disk_code_fingerprint"] != _code_fingerprint()
                    or health["reconnect_required"]
                    or health["schema_fingerprint"] != canonical_schema(tools)
                    or health["tool_count"] != len(tools)):
                raise RuntimeError("Loaded source/schema fingerprint differs from this checkout")
            report["health_before_com"] = health
            report["registered_tools"] = sorted(names)
            baseline = await summary()
            keep = [row["document"]["handle"] for row in baseline]
            report["baseline"] = baseline
            dump(report_path, report)
            print(f"Baseline: {len(baseline)} native documents, all protected", flush=True)

            for index in range(count):
                # Verify each new part's actual Changed state immediately, before
                # any later creation; never assume a blank native document is clean.
                item = await call("create_document", kind="part", visible=False)
                handle = item["document"]["handle"]
                if handle in keep or not item["owned_by_server"]:
                    raise RuntimeError("New synthetic identity/ownership is unsafe")
                synthetic.append(handle)
                row = await ensure_clean_own(handle, index)
                report.setdefault("synthetic", []).append(row)
                unchanged_baseline(baseline, await summary())
                dump(report_path, report)
            print(f"Created {count} clean synthetic empty parts", flush=True)

            timings = {}
            for details in (False, True):
                values = []
                for _ in range(5):
                    begin = time.perf_counter()
                    listed = await call("list_documents", details=details)
                    values.append(time.perf_counter()-begin)
                    if len(listed["documents"]) != len(baseline)+count:
                        raise RuntimeError("Benchmark changed the native document count")
                    unchanged_baseline(baseline, listed["documents"])
                    if not details and any("top_part" in row or "views" in row
                                           for row in listed["documents"]):
                        raise RuntimeError("Summary unexpectedly expands TopPart/views")
                timings["details" if details else "summary"] = timing_result(values)
            report["timings"] = timings
            report["summary_speedup_median"] = (
                timings["details"]["median_seconds"] / timings["summary"]["median_seconds"])

            # Run a read concurrently with out-of-STA diagnostics. On a fast PC
            # it may finish before the observation; report that honestly.
            reading = asyncio.create_task(call("list_documents", details=True))
            await asyncio.sleep(0)
            begin = time.perf_counter()
            report["job_status_during_read"] = await call("job_status", limit=100)
            report["job_status_roundtrip_seconds"] = time.perf_counter()-begin
            await reading
            report["observed_busy_sta"] = report["job_status_during_read"]["pending"] > 0
            cache_before = (await call("runtime_health"))["schema_cache"]
            described = []
            for _ in range(5):
                begin = time.perf_counter()
                schema = await call("api_describe", handle=synthetic[0])
                described.append(time.perf_counter()-begin)
                if schema["interface"] != "IKompasDocument":
                    raise RuntimeError("Document handle has an unexpected SDK schema")
            cache_after = (await call("runtime_health"))["schema_cache"]
            if cache_after["hits"] - cache_before["hits"] < 4:
                raise RuntimeError("Repeated pure SDK schema requests did not hit the cache")
            report["schema_cache"] = {"before": cache_before, "after": cache_after,
                                       "timings": timing_result(described)}
            dump(report_path, report)

            plan = await call("close_documents", keep=keep, candidates=synthetic, dry_run=True)
            if (not plan["dry_run"] or plan["closed_count"]
                    or len(plan["documents"]) != count
                    or any(row["state"] != "candidate" for row in plan["documents"])):
                raise RuntimeError("Unexpected batch-close plan; nothing should have closed")
            report["close_plan"] = plan
            preclose = await summary()
            unchanged_baseline(baseline, preclose)
            if len(preclose) != len(baseline)+count:
                raise RuntimeError("Dry run changed the native document count")
            for index, handle in enumerate(synthetic):
                await ensure_clean_own(handle, index)
            applied = await call("close_documents", keep=keep, candidates=synthetic, dry_run=False)
            report["close_apply"] = applied
            closed.update(row["handle"] for row in applied["documents"] if row["state"] == "closed")
            if (applied["closed_count"] != count or applied["discarded_changes"]
                    or any(row["state"] != "closed" for row in applied["documents"])):
                raise RuntimeError("Batch close was incomplete; inspect per-document states")
            after = await summary()
            unchanged_baseline(baseline, after)
            if len(after) != len(baseline):
                raise RuntimeError("Final native document count differs from baseline")
            stale = []
            for handle in synthetic:
                rejected = await call("document_details", handle=handle, allow_error=True)
                if not rejected.get("is_error") or not any("stale_handle" in message
                                                          for message in rejected["messages"]):
                    raise RuntimeError("Closed native handle was not rejected as stale")
                stale.append(handle)
            report["stale_handles_rejected"] = stale
            report["baseline_after"] = after
            report["health_after"] = await call("runtime_health")
            report.update(status="passed", baseline_preserved=True,
                          all_synthetic_closed=True, no_discard_used=True)
            print("PASS: baseline preserved; synthetic batch closed; stale handles rejected", flush=True)
        except Exception as exc:
            report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            # Exceptional cleanup is still restricted to exact synthetic handles.
            # Save their own unexpected edits first; never touch baseline files.
            if synthetic:
                try:
                    current = await summary()
                    live = {row["document"]["handle"] for row in current}
                    remaining = [handle for handle in synthetic if handle not in closed and handle in live]
                    for index, handle in enumerate(remaining):
                        await ensure_clean_own(handle, count+index)
                    if remaining:
                        cleanup = await call("close_documents", keep=keep, candidates=remaining,
                                             dry_run=False)
                        report["cleanup"].append(cleanup)
                    final = await summary()
                    unchanged_baseline(baseline, final)
                    report["baseline_preserved_finally"] = True
                except Exception as cleanup_error:  # noqa: BLE001 - preserve native cleanup evidence
                    report.update(status="failed", cleanup_error=str(cleanup_error))
            dump(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-native", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=18)
    args = parser.parse_args()
    if not args.run_native:
        parser.error("Native acceptance requires explicit --run-native")
    result = asyncio.run(validate(args.output, args.count))
    print(json.dumps({"status": result["status"], "report": str(args.output /
          "runtime13-native-acceptance.json")}, ensure_ascii=False), flush=True)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
