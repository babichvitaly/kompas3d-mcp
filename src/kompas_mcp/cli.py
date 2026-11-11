"""Project staging/result checks and a no-COM MCP capability inventory.

Offline commands never connect to CAD or change client configuration. run-recipe
executes only an explicitly supplied command and checks its fresh terminal file;
it never retries or terminates an uncertain native operation.
"""

import argparse
import asyncio
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    with Path(path).open(encoding="utf-8-sig") as stream:
        result = json.load(stream, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")  # noqa: TRY004 - malformed input protocol
    return result


def _emit(value, report=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if report is not None:
        with Path(report).open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")


async def capabilities():
    from .runtime_tools import health_snapshot
    from .server import mcp, worker

    tools = await mcp.list_tools()
    schemas = sorted([{
        "name": tool.name, "inputSchema": tool.inputSchema,
        "outputSchema": getattr(tool, "outputSchema", None),
    } for tool in tools], key=lambda item: item["name"])
    return health_snapshot(worker, schemas)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "verify-result":
        from .job_results import main as verify_main

        return verify_main(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version",
                        version=importlib.metadata.version("kompas3d-mcp"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities", help="List actual schemas/fingerprints without CAD/COM")
    sub.add_parser("verify-result", help="Verify a saved terminal result (use --help)")
    recipe = sub.add_parser("run-recipe", help="Execute a command once; verify its fresh terminal file")
    recipe.add_argument("--terminal-result", required=True)
    recipe.add_argument("--require-artifact-verification", action="store_true")
    recipe.add_argument("recipe", nargs=argparse.REMAINDER)
    for name in ("package-preflight", "package-stage"):
        command = sub.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--destination", required=True)
        command.add_argument("--report", help="New JSON file; never overwrite")
    args = parser.parse_args(argv)
    try:
        if args.command == "capabilities":
            _emit(asyncio.run(capabilities()))
            return 0
        if args.command == "run-recipe":
            from .job_results import verify_result_file

            terminal = Path(args.terminal_result).resolve()
            command = args.recipe[1:] if args.recipe[:1] == ["--"] else args.recipe
            if (not Path(args.terminal_result).is_absolute() or terminal.exists() or not command
                    or not terminal.parent.is_dir()):
                raise ValueError("Use a new absolute terminal-result path and an explicit command")
            # Reserve the canonical result path before starting any producer.
            # Retain this evidence after success/failure; a path is never reused.
            job_id = uuid4().hex
            lease = terminal.with_name(terminal.name + ".recipe-lease.json")
            with lease.open("x", encoding="utf-8") as stream:
                json.dump({"job_id": job_id, "terminal_result": str(terminal),
                           "created_unix_ns": time.time_ns(), "automatic_retry": False}, stream)
            if terminal.exists():
                raise ValueError("Terminal result appeared before launch; reconcile it")
            started = time.monotonic()
            launched = subprocess.Popen(command)  # no shell; do not use run()'s exception-time kill
            try:
                launcher_returncode = launched.wait()
            except BaseException:
                _emit({"phase": "reconciliation_required", "launcher_job_id": job_id,
                       "child_pid": launched.pid, "retry_allowed": False,
                       "recovery": "Child was not terminated; reconcile its terminal result"})
                raise
            try:
                result = verify_result_file(terminal, launcher_returncode,
                                            args.require_artifact_verification)
            except (OSError, ValueError, TypeError) as exc:
                result = {"execution_status": "failed" if launcher_returncode else "unreported",
                          "exit_code": 1 if launcher_returncode else 2,
                          "reason": str(exc), "retry_allowed": False,
                          "phase": "reconciliation_required",
                          "recipe_started": True, "child_pid": launched.pid,
                          "terminal_result_path": str(terminal),
                          "terminal_result_argument": args.terminal_result,
                          "recovery": "Recipe already ran. Inspect argv/path transport and the "
                                      "existing receipt; verify it separately. Do not rerun mutation."}
            result["launcher_returncode"] = launcher_returncode
            result["launcher_job_id"] = job_id
            result["launcher_elapsed_seconds"] = time.monotonic() - started
            _emit(result)
            return result["exit_code"]
        # Fail report preflight before materializing any copies.
        if args.report:
            target = Path(args.report)
            if target.exists() or not target.parent.is_dir():
                raise ValueError("Report must be a new file in an existing directory")
        from .project_package import materialize_package, preflight_package

        plan = read_json(args.plan)
        operation = preflight_package if args.command == "package-preflight" else materialize_package
        report = operation(plan, args.destination)
        _emit(report, args.report)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        _emit({"phase": "failed", "error": f"{type(exc).__name__}: {exc}",
               "portable": False, "recovery": "Inspect owned output before retrying"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
