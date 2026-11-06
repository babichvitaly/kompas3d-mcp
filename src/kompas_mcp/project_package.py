"""Offline, hash-pinned staging of a multi-root CAD project.

This module never imports COM or rewrites native references. A successful copy is
``files_staged_not_rebound``, never a portable-project certificate. Native link
inspection/rebinding remains a separate operation in :mod:`project_copy`.
"""

import hashlib
import json
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from uuid import uuid4

METADATA_DIRECTORY = ".cad-package"
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}"
    for prefix in ("COM", "LPT")
    for number in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3")
}


class PackageMaterializationError(RuntimeError):
    """Staging failed after ownership was acquired; inspect the preserved report."""

    def __init__(self, report):
        self.report = report
        super().__init__(report["error"])


def _utc():
    return datetime.now(UTC).isoformat()


def _path_key(path):
    return unicodedata.normalize("NFC", str(path)).casefold()


def _identity(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


def _no_symlinks(path):
    """Reject links in every existing ancestor, including the source itself."""
    for value in (path, *path.parents):
        if value.is_symlink() or (hasattr(value, "is_junction") and value.is_junction()):
            raise ValueError(f"Symlink path is not supported for package staging: {value}")


def _source_path(value):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("source must be a nonempty absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("source must be a host-native absolute path")
    _no_symlinks(path)
    if not path.is_file():
        raise ValueError(f"Missing or non-regular source file: {path}")
    path = path.resolve(strict=True)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Source is not a regular file: {path}")
    return path


def _relative_destination(value):
    if not isinstance(value, str) or not value:
        raise ValueError("destination_relative must be a nonempty relative path")
    win = PureWindowsPath(value)
    if win.drive or win.root or Path(value).is_absolute():
        raise ValueError("Absolute destination_relative paths are forbidden")
    parts = value.replace("\\", "/").split("/")
    for part in parts:
        if (
            part in {"", ".", ".."}
            or part.endswith((" ", "."))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            or part.split(".", 1)[0].rstrip(" ").upper() in WINDOWS_RESERVED
        ):
            raise ValueError(f"Unsafe or Windows-incompatible destination path: {value}")
    if _path_key(parts[0]) == METADATA_DIRECTORY:
        raise ValueError("The package metadata directory is reserved")
    return "/".join(parts)


def _target_path(value):
    target = Path(value)
    if not target.is_absolute():
        raise ValueError("destination must be a new host-native absolute directory")
    _no_symlinks(target)
    if target.exists():
        raise ValueError("destination already exists; use a new owned directory")
    if not target.parent.is_dir():
        raise ValueError("destination parent must already exist")
    return target.parent.resolve(strict=True) / target.name


def _read_source(path, expected_identity=None, output=None):
    """Hash stable path/handle channels; copy the same bytes when requested.

    Windows can expose a different ctime through fstat and stat after a flushed
    write. Compare each metadata channel with itself, linking them only through
    the shared device/inode identity; SHA checks remain independent of metadata.
    """
    _no_symlinks(path)
    path_before = path.stat()
    if expected_identity is not None and _identity(path_before) != expected_identity:
        raise ValueError(f"Source identity changed after preflight: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Source is no longer a regular file: {path}")
        if not os.path.samestat(path_before, before):
            raise ValueError(f"Source path/handle identity mismatch: {path}")
        digest = hashlib.sha256()
        size = 0
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
            if output is not None:
                output.write(block)
        after = os.fstat(stream.fileno())
    _no_symlinks(path)
    current = path.stat()
    if (
        _identity(before) != _identity(after)
        or _identity(path_before) != _identity(current)
        or not os.path.samestat(after, current)
    ):
        raise ValueError(f"Source changed while reading: {path}")
    return digest.hexdigest(), size, _identity(current)


def _resources(plan):
    rows = plan.get("runtime_resources", [])
    if not isinstance(rows, list):
        # Plan-validation errors use one public ValueError contract.
        raise ValueError(  # noqa: TRY004
            "runtime_resources must be a list of explicit name/policy declarations"
        )
    names, result = set(), []
    for row in rows:
        if not isinstance(row, Mapping) or not all(
            isinstance(row.get(key), str) and row[key].strip() for key in ("name", "policy")
        ):
            raise ValueError("Each runtime resource requires explicit name and policy")
        name = row["name"]
        if _path_key(name) in names:
            raise ValueError("Duplicate runtime resource declaration")
        names.add(_path_key(name))
        result.append({"name": name, "policy": row["policy"], "native_verified": False})
    return result


def _graph_report(plan, files, resources):
    """Report cycles from supplied links; never infer native closure from filenames."""
    raw = plan.get("dependency_graph")
    if raw is None:
        return {
            "status": "not_scanned",
            "roots": [],
            "cycles": [],
            "missing_engineering_dependencies": None,
            "native_closure_verified": False,
        }
    if not isinstance(raw, Mapping):
        raise ValueError(  # noqa: TRY004 - malformed input plan, not a Python API type overload
            "dependency_graph must map absolute source paths to link lists"
        )
    sources = {_path_key(row["source"]): row["source"] for row in files}
    resource_ids = {_path_key(f"resource:{row['name']}") for row in resources}
    graph, missing, edges = {}, set(), 0
    for source, links in raw.items():
        key = _path_key(source)
        if key not in sources or not isinstance(links, list):
            raise ValueError("Graph nodes must be planned sources with explicit link lists")
        if key in graph:
            raise ValueError("Case-folding duplicate dependency graph node")
        graph[key] = []
        for child in links:
            if not isinstance(child, str):
                raise ValueError(  # noqa: TRY004 - preserve the plan-validation contract
                    "Graph links must be source paths or declared resource:name IDs"
                )
            child_key = _path_key(child)
            edges += 1
            if edges > 500000:
                raise ValueError("Dependency graph edge limit exceeded")
            if child_key in resource_ids:
                continue
            if child_key not in sources:
                missing.add(child)
            else:
                graph[key].append(child_key)
    if missing:
        raise ValueError(f"Missing engineering dependencies from package plan: {sorted(missing)}")
    roots = plan.get("roots", [])
    if not isinstance(roots, list) or not all(
        isinstance(root, str) and _path_key(root) in sources for root in roots
    ):
        raise ValueError("roots must be a list of planned absolute source paths")
    # Iterative DFS handles deep source trees without Python recursion limits.
    done, active, order, cycles = set(), {}, [], []
    for root, root_children in graph.items():
        if root in done:
            continue
        trail, stack = [root], [(root, iter(root_children))]
        active[root] = 0
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                trail.pop()
                active.pop(node, None)
                done.add(node)
                order.append(sources[node])
            elif child in active:
                if len(cycles) >= 1000:
                    raise ValueError("Dependency graph cycle reporting limit exceeded")
                cycles.append([sources[value] for value in trail[active[child]:]] + [sources[child]])
            elif child not in done:
                active[child] = len(trail)
                trail.append(child)
                stack.append((child, iter(graph.get(child, []))))
    complete = set(graph) == set(sources)
    return {
        "status": "supplied_complete_graph" if complete else "supplied_partial_graph",
        "roots": roots,
        "cycles": cycles,
        "bottom_up_order": None if cycles else order,
        "missing_engineering_dependencies": 0,
        "native_closure_verified": False,
        "native_scan_claim_from_caller": bool(
            plan.get("all_root_external_links_freshly_native_scanned", False)
        ),
    }


def preflight_package(plan, destination, *, max_files=50000):
    """Validate every source/hash/destination before any write, without CAD/COM.

    The plan accepts ``copy_mapping`` entries containing ``source``,
    ``source_sha256`` and ``destination_relative``; optional ``source_bytes`` is
    checked too. Runtime resources remain explicit, unverified exceptions.
    """
    if not isinstance(plan, Mapping):
        raise ValueError("plan must be an object")  # noqa: TRY004 - plan-validation contract
    if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 50000:
        raise ValueError("max_files must be 1..50000")
    target = _target_path(destination)
    mapping = plan.get("copy_mapping")
    if not isinstance(mapping, list) or not 1 <= len(mapping) <= max_files:
        raise ValueError("copy_mapping must be a nonempty bounded list")
    files, sources, destinations, destination_parents = [], set(), set(), set()
    for row in mapping:
        if not isinstance(row, Mapping):
            raise ValueError(  # noqa: TRY004 - plan-validation contract
                "Each copy_mapping entry must be an object"
            )
        source = _source_path(row.get("source"))
        source_key = _path_key(source)
        relative = _relative_destination(row.get("destination_relative"))
        destination_key = _path_key(relative)
        if source_key in sources:
            raise ValueError("Duplicate or case-folding conflicting source path")
        if destination_key in destinations:
            raise ValueError("Duplicate or Windows case-folding conflicting destination path")
        # A file cannot also be another file's parent directory.
        parts = destination_key.split("/")
        parents = {"/".join(parts[:index]) for index in range(1, len(parts))}
        if destination_key in destination_parents or parents & destinations:
            raise ValueError("Conflicting file/directory destination paths")
        expected = row.get("source_sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise ValueError("Every source requires a complete SHA256")
        digest, size, identity = _read_source(source)
        if digest != expected.lower():
            raise ValueError(f"Source SHA256 mismatch: {source}")
        expected_size = row.get("source_bytes")
        if expected_size is not None and (
            isinstance(expected_size, bool) or not isinstance(expected_size, int) or size != expected_size
        ):
            raise ValueError(f"Source byte count mismatch: {source}")
        sources.add(source_key)
        destinations.add(destination_key)
        destination_parents.update(parents)
        files.append({
            "source": str(source),
            "source_sha256": digest,
            "source_bytes": size,
            "source_identity": identity,
            "destination_relative": relative,
        })
    resources = _resources(plan)
    graph = _graph_report(plan, files, resources)
    return {
        "schema": "cad-project-package-staging/0.1",
        "phase": "preflight_pass_not_rebound",
        "destination": str(target),
        "files": files,
        "file_count": len(files),
        "source_bytes": sum(row["source_bytes"] for row in files),
        "runtime_resources": resources,
        "dependency_graph": graph,
        "references_rewritten": False,
        "portable": False,
        "CAD_COM_access": False,
    }


def _write_manifest(target, report):
    folder = target / METADATA_DIRECTORY
    temporary = folder / f"manifest-{uuid4().hex}.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(folder / "manifest.json")


def _copy_file(row, target):
    relative = Path(row["destination_relative"])
    output = target / relative
    parent = target
    for part in relative.parts[:-1]:
        parent /= part
        parent.mkdir(exist_ok=True)
        _no_symlinks(parent)
    with output.open("xb") as stream:
        digest, size, _ = _read_source(
            Path(row["source"]), row["source_identity"], output=stream
        )
        stream.flush()
        os.fsync(stream.fileno())
    if digest != row["source_sha256"] or size != row["source_bytes"]:
        raise ValueError(f"Source changed after preflight: {row['source']}")
    actual, actual_size, _ = _read_source(output)
    if actual != digest or actual_size != size:
        raise ValueError(f"Copied file SHA256 mismatch: {output}")


def materialize_package(plan, destination, *, max_files=50000):
    """Stage pinned bytes into a newly owned folder, preserving any failed copy.

    Preflight failures write nothing. A failure after ``mkdir`` leaves the owned
    directory and a failed manifest, then raises ``PackageMaterializationError``.
    No file is overwritten and failed destination names are never reused.
    """
    report = preflight_package(plan, destination, max_files=max_files)
    target = Path(report["destination"])
    owner_id = uuid4().hex
    target.mkdir()  # exclusive; another creator wins safely with FileExistsError
    report.update(owner_id=owner_id, started_utc=_utc(), phase="files_staging", copied=[])
    try:
        (target / METADATA_DIRECTORY).mkdir()
        with (target / METADATA_DIRECTORY / "owner.json").open("x", encoding="utf-8") as stream:
            json.dump({"owner_id": owner_id, "created_utc": report["started_utc"]}, stream)
        _write_manifest(target, report)
        for row in report["files"]:
            # Record even the current partial copy before any file bytes are written.
            record = {"destination_relative": row["destination_relative"], "state": "copying"}
            report["copied"].append(record)
            _write_manifest(target, report)
            _copy_file(row, target)
            record["state"] = "copied_sha_verified"
        # Re-read all original paths after staging to catch changes to earlier files.
        for row in report["files"]:
            digest, _, _ = _read_source(Path(row["source"]), row["source_identity"])
            if digest != row["source_sha256"]:
                raise ValueError(f"Source changed during package staging: {row['source']}")
            output = target / row["destination_relative"]
            copied, copied_size, _ = _read_source(output)
            if copied != row["source_sha256"] or copied_size != row["source_bytes"]:
                raise ValueError(f"Copied file changed during package staging: {output}")
        report.update(
            phase="files_staged_not_rebound",
            completed_utc=_utc(),
            all_source_SHA_rechecked=True,
            all_copied_SHA_verified=True,
        )
        _write_manifest(target, report)
        return report
    except BaseException as error:
        report.update(
            phase="files_staging_failed",
            completed_utc=_utc(),
            error=f"{type(error).__name__}: {error}",
            inspect_before_retry=True,
        )
        try:
            _write_manifest(target, report)
        except Exception as manifest_error:  # noqa: BLE001 - retain both primary and manifest failures
            report["manifest_write_error"] = f"{type(manifest_error).__name__}: {manifest_error}"
        if not isinstance(error, Exception):
            raise
        raise PackageMaterializationError(report) from error
