"""Runtime diagnostics outside STA, plus explicitly scoped document conveniences."""

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

from . import bridge, documents


def _code_fingerprint():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


LOADED_CODE_FINGERPRINT = _code_fingerprint()


def health_snapshot(worker, schemas):
    """No CAD/COM calls, including when a native operation is blocked."""
    canonical = json.dumps(schemas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    current_code = _code_fingerprint()
    try:
        version = importlib.metadata.version("kompas3d-mcp")
    except importlib.metadata.PackageNotFoundError:
        version = "uninstalled-source"
    return {
        "server": "kompas3d-mcp", "package_version": version, "runtime_revision": "13",
        "loaded_source_directory": str(Path(__file__).resolve().parent),
        "python": sys.version.split()[0],
        "loaded_code_fingerprint": LOADED_CODE_FINGERPRINT,
        "disk_code_fingerprint": current_code,
        "reconnect_required": current_code != LOADED_CODE_FINGERPRINT,
        "tool_count": len(schemas),
        "schema_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "tool_names": [tool["name"] for tool in schemas],
        "worker": worker.status(),
        "schema_cache": bridge._describe_type.cache_info()._asdict(),
        "diagnostic_scope": "Python runtime and registered schemas only; no live CAD health claim.",
        "timing_scope": "Worker duration includes Python, COM execution and message pumping.",
    }


def register_runtime(mcp, worker):
    @mcp.tool()
    async def runtime_health() -> dict:
        """Version, loaded/disk code fingerprints and actual tool schemas without waiting for COM.

        An idle/healthy Python transport does not prove that KOMPAS is responsive.
        Reconnect if code changed or the expected tool set differs from the client.
        """
        tools = await mcp.list_tools()
        schemas = sorted([{
            "name": tool.name, "inputSchema": tool.inputSchema,
            "outputSchema": getattr(tool, "outputSchema", None),
        } for tool in tools], key=lambda row: row["name"])
        return health_snapshot(worker, schemas)

    @mcp.tool()
    def job_status(job_id: str | None = None, limit: int = 30) -> dict:
        """Read queue/running/completed job IDs, names and timings without entering the occupied STA.

        History is bounded. Job completion is wrapper completion, not a geometry certificate.
        """
        return worker.status(job_id, limit)

    @mcp.tool()
    def cancel_job(job_id: str) -> dict:
        """Cancel a queued job if it has not started. Never interrupt a running COM call.

        A running operation keeps its queue slot and may mutate CAD after the client
        stops waiting. Reconcile its final status and document state before retrying.
        """
        return worker.cancel(job_id)


def register_documents(mcp, worker):
    @mcp.tool()
    async def document_details(handle: str) -> dict:
        """Expand one document with typed model/TopPart or drawing/views handles on the same STA."""
        return await worker.call(lambda k: documents.document_details(k, handle),
                                 name="document_details")

    @mcp.tool()
    async def close_documents(
        keep: list[str], candidates: list[str] | None = None, dry_run: bool = True,
    ) -> dict:
        """Plan/close unchanged documents by explicit handles; default is a dry run.

        With omitted candidates only server-owned documents are considered. Existing
        adopted documents never become owned. Explicit candidates may include adopted
        unchanged documents. Keep handles are always protected. Rechecks Changed and
        identity per close, never saves/discards changes or quits KOMPAS. A batch may
        partially close; inspect returned states before another attempt.
        """
        return await worker.call(lambda k: documents.close_documents(k, keep, candidates, dry_run),
                                 name="close_documents")


def register(mcp, worker):
    register_runtime(mcp, worker)
    register_documents(mcp, worker)
