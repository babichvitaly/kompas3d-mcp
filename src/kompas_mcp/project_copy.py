"""Copy a complete, checked dependency DAG without saving original documents.

All native work runs in the caller's existing STA. Cyclic document links and
model-library pseudo paths deliberately fail preflight rather than producing an
incompletely isolated project. No production paths or data are built into code.
"""

import hashlib
import math
import shutil
from contextlib import contextmanager
from pathlib import Path

from .audit import IDENTITY, matrix, multiply, write_json
from .backend import require
from .documents import KINDS, _cast, _document

NATIVE = {extension for _, extension in KINDS.values()}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical(path, owner=None):
    """Resolve native relative links against their owning file, never the cwd."""
    if not isinstance(path, (str, Path)) or not str(path) or "|" in str(path):
        raise ValueError("Empty or model-library pseudo paths cannot be isolated")
    value = Path(path)
    if not value.is_absolute():
        if owner is None:
            raise ValueError("An absolute source path is required")
        value = Path(owner).parent / value
    return value.resolve()


def path_key(path):
    return str(canonical(path)).casefold()


@contextmanager
def native_document(k, path, read_only=True):
    """Reuse clean source documents; close only a document this context opened."""
    path = canonical(path)
    collection = k.app.ksGetApplication7().Documents
    existing = [collection.Item(i) for i in range(collection.Count)]
    found = next((d for d in existing if d.PathName and path_key(d.PathName) == path_key(path)), None)
    if found is not None:
        if not read_only:
            raise ValueError(f"Destination already open; reconcile it before retrying: {path}")
        if found.Changed:
            raise ValueError(f"Unsaved source changes; disk copy would be stale: {path}")
        yield found
        return
    doc = require(collection.Open(str(path), False, read_only), "open dependency document")
    try:
        if bool(doc.ReadOnly) != read_only:
            raise RuntimeError("Native read-only state does not match the requested mode")
        yield doc
    finally:
        scope = str(doc.Reference)
        require(doc.Close(k.constants["kdDoNotSaveChanges"]), "close owned dependency document")
        k.release_scope(scope)
        k.owned_documents.discard(scope)


def external_links(k, doc, recursive=False):
    """SDK file/type arrays; immediate by default, all link types retained."""
    result = _cast(k, doc, "IKompasDocument1").GetExternalFilesNamesEx(recursive)
    if not isinstance(result, (tuple, list)) or len(result) != 3 or not result[0]:
        raise RuntimeError("GetExternalFilesNamesEx did not return a checked file/type list")
    names, types = result[1], result[2]
    names = [] if names is None else list(names)
    types = [] if types is None else list(types)
    if len(names) != len(types):
        raise RuntimeError("External file and type arrays have different lengths")
    return [{"native_path": str(name), "type": int(kind),
             "path": str(canonical(name, doc.PathName))}
            for name, kind in zip(names, types, strict=True)]


def verify_external_isolation(k, doc, copy_root):
    """Check non-component dependencies too, without opening or rebuilding them.

    Recursive=True is read-only here. It is never used for ReplaceExternalFilesNames.
    This allows unsaved edits in a copied sketch while protecting linked geometry,
    variable sources, resources and other files outside the declared copy root.
    """
    folder = Path(copy_root).resolve()
    links = external_links(k, doc, recursive=True)
    for link in links:
        path = Path(link["path"])
        if not path.is_file() or not path.is_relative_to(folder):
            raise ValueError(f"Missing or outside-copy external dependency: {path}")
    return links


def occurrence_snapshot(k, doc, max_nodes=50000):
    """Fresh path identities, including excluded components and embedded children."""
    if doc.DocumentType not in {k.constants["ksDocumentPart"], k.constants["ksDocumentAssembly"]}:
        return []
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    pending = [(root, [], IDENTITY, doc.PathName)]
    rows = []
    while pending:
        part, path, parent, owner = pending.pop()
        if len(rows) >= max_nodes or len(path) > 64:
            raise ValueError("Occurrence traversal limit; isolation is unproved")
        local = matrix(part.Placement.GetMatrix3D()) if path else list(IDENTITY)
        world = multiply(local, parent)
        source = str(part.FileName or "")
        source_path = str(canonical(source, owner)) if source else ""
        rows.append({"path": path, "source": source_path,
                     "local_to_parent": local, "local_to_root": world,
                     "fixed": bool(part.Fixed), "hidden": bool(part.Hidden)})
        for i in reversed(range(part.Parts.Count)):
            pending.append((part.Parts.Part(i), [*path, i], world, source_path or owner))
    return rows


def dependencies(k, doc):
    rows = external_links(k, doc)
    keys = {path_key(row["path"]) for row in rows}
    own = path_key(doc.PathName)
    # This also catches external insertions below an embedded subassembly.
    for row in occurrence_snapshot(k, doc):
        if row["path"] and row["source"] and path_key(row["source"]) not in keys | {own}:
            rows.append({"path": row["source"], "native_path": row["source"],
                         "type": None, "discovered_by": "occurrence_tree"})
            keys.add(path_key(row["source"]))
    return [row for row in rows if path_key(row["path"]) != own]


def bottom_up(graph):
    """Each canonical source exactly once; fail on a cycle before any copying."""
    visited, active, order = set(), set(), []

    def visit(node):
        if node in active:
            raise ValueError("Cyclic external document links require an explicit cycle-aware workflow")
        if node in visited:
            return
        active.add(node)
        for child in graph[node]:
            visit(child)
        active.remove(node)
        visited.add(node)
        order.append(node)

    for node in graph:
        visit(node)
    return order


def assert_occurrences(expected, actual, mapping=None, tolerance=1e-8):
    if len(expected) != len(actual):
        raise RuntimeError("Occurrence count changed")
    mapping = mapping or {}
    for a, b in zip(expected, actual, strict=True):
        if a["path"] != b["path"] or a["fixed"] != b["fixed"] or a["hidden"] != b["hidden"]:
            raise RuntimeError("Occurrence identity/fixed/hidden state changed")
        target = mapping.get(path_key(a["source"]), a["source"]) if a["source"] else ""
        if bool(target) != bool(b["source"]) or (target and path_key(target) != path_key(b["source"])):
            raise RuntimeError(f"Unexpected source at occurrence {a['path']}")
        for name in ("local_to_parent", "local_to_root"):
            if len(b[name]) != 16 or any(not math.isfinite(y) or abs(x - y) > tolerance
                                       for x, y in zip(a[name], b[name], strict=True)):
                raise RuntimeError(f"Placement changed at occurrence {a['path']}")


def scan_closure(k, root_path, max_files=5000):
    graph, files = {}, {}

    def visit(path):
        path = canonical(path)
        key = path_key(path)
        if key in files:
            return
        if len(files) >= max_files or not path.is_file():
            raise ValueError(f"Missing dependency or file limit exceeded: {path}")
        row = {"source": str(path), "sha256": digest(path), "bytes": path.stat().st_size,
               "native": path.suffix.lower() in NATIVE, "links": [], "occurrences": []}
        files[key], graph[key] = row, []
        if row["native"]:
            with native_document(k, path, True) as doc:
                row["links"] = dependencies(k, doc)
                row["occurrences"] = occurrence_snapshot(k, doc)
                if doc.Changed:
                    raise RuntimeError("Read-only dependency inspection changed document state")
            for link in row["links"]:
                graph[key].append(path_key(link["path"]))
                visit(link["path"])

    visit(root_path)
    return files, bottom_up(graph)


def replacement_plan(source_links, current_links, copied_path, mapping, target):
    """Resolve relative native links using their original owner, never a new cwd.

    A native reopen may report either a literal relative link or its expansion
    against the copied document folder. Both are matched to the preflight record.
    An already-inside path is accepted only when it is the exact planned, existing
    destination. Unexpected or ambiguous links are a failed plan, not a skip.
    """
    plans = [link for link in source_links if link.get("discovered_by") != "occurrence_tree"]
    changes, used = {}, set()
    for current in current_links:
        key = path_key(current["path"])
        matches = {}
        for source in plans:
            original = path_key(source["path"])
            if original not in mapping:
                raise RuntimeError("Preflight link has no copied target")
            aliases = {original, path_key(canonical(source["native_path"], copied_path)),
                       path_key(mapping[original])}
            if key in aliases:
                matches[original] = mapping[original]
        if len(matches) != 1:
            raise RuntimeError("Unplanned or ambiguous native link after opening the copied document")
        original, replacement = next(iter(matches.items()))
        wanted = Path(replacement).resolve()
        if not wanted.is_file() or not wanted.is_relative_to(target):
            raise RuntimeError("Copied dependency target is absent or outside destination")
        used.add(original)
        if key != path_key(wanted):
            changes[current["native_path"]] = str(wanted)
    if used != {path_key(link["path"]) for link in plans}:
        raise RuntimeError("A preflight-owned native link disappeared while opening the copy")
    return changes


def create_isolated_copy(k, handle, destination, dry_run=True, max_files=5000):
    """Native dependency closure, copied once, rebound bottom-up and reopened.

    Cycles/pseudo paths/missing links/unsaved originals are rejected preflight.
    Assets are byte copied as leaves. Every native external-link type is retained
    and redirected; no recursive replacement is used, so originals are never saved.
    A failed result leaves a manifest and inspectable partial copies, never a pass.
    """
    doc = _document(k, handle)
    if not doc.PathName or doc.Changed:
        raise ValueError("Save source changes explicitly before making a disk-based isolated copy")
    target = Path(destination)
    if not target.is_absolute() or target.exists() or not 1 <= max_files <= 50000:
        raise ValueError("destination must be a new absolute directory; max_files 1..50000")
    target = target.resolve()
    files, order = scan_closure(k, doc.PathName, max_files)
    source_root = path_key(doc.PathName)
    mapping = {}
    for i, (key, row) in enumerate(files.items()):
        category = "root" if key == source_root else f"files/{i:05d}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"
        mapping[key] = str(target / category / Path(row["source"]).name)
    records = {key: {**row, "copy": mapping[key]} for key, row in files.items()}
    report = {"schema": 1, "operation": "create_isolated_copy", "status": "planned",
              "dry_run": dry_run, "destination": str(target), "root": mapping[source_root],
              "source_count": len(files), "bottom_up_order": [files[key]["source"] for key in order],
              "files": list(records.values()),
              "originals_unchanged": None, "persistence_verified": False,
              "outside_links": None, "completed_files": [],
              "limits": "Dependency DAG only; library pseudo paths/cycles rejected; no manufacturing certification"}
    if dry_run:
        return report
    target.mkdir(parents=True, exist_ok=False)
    manifest = target / "isolated-copy-manifest.json"
    phase = "copy_bytes"
    try:
        write_json(manifest, report)
        for key, row in files.items():
            if digest(row["source"]) != row["sha256"]:
                raise RuntimeError("Source changed after preflight; do not retry without reconciliation")
            out = Path(mapping[key])
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["source"], out)
            records[key]["byte_copy_sha256"] = digest(out)
            if records[key]["byte_copy_sha256"] != row["sha256"]:
                raise RuntimeError("Byte-copy hash mismatch")
        for key in order:
            row = files[key]
            if not row["native"]:
                report["completed_files"].append(mapping[key])
                continue
            phase = f"rebind:{mapping[key]}"
            with native_document(k, mapping[key], False) as copied:
                extra = _cast(k, copied, "IKompasDocument1")
                # Only links owned by this document belong in a non-recursive
                # replacement. The full occurrence snapshot also contains its
                # external child's links; those were rebound in the child file
                # already. Replacing such a transitive path here returns False
                # by SDK contract and must never trigger recursive=True.
                changes = replacement_plan(row["links"], external_links(k, copied),
                                           copied.PathName, mapping, target)
                for old, new in changes.items():
                    require(extra.ReplaceExternalFilesNames(False, old, new), "replace copy-only file link")
                # Sources hidden below embedded children are not always returned
                # as external links: use explicit occurrence FileName only there.
                if copied.DocumentType in {k.constants["ksDocumentPart"], k.constants["ksDocumentAssembly"]}:
                    root = _cast(k, copied, "IKompasDocument3D").TopPart
                    originals_by_path = {tuple(r["path"]): r for r in row["occurrences"]}
                    pending = [(root, [])]
                    while pending:
                        part, parent_path = pending.pop()
                        for i in range(part.Parts.Count):
                            child = part.Parts.Part(i)
                            occurrence_path = [*parent_path, i]
                            source = str(child.FileName or "")
                            source_path = canonical(source, copied.PathName) if source else None
                            original = originals_by_path.get(tuple(occurrence_path))
                            if original is None:
                                raise RuntimeError("Unplanned occurrence appeared during rebind")
                            owned = not source_path or path_key(source_path) == path_key(copied.PathName)
                            if not owned:
                                old = path_key(original["source"]) if original["source"] else ""
                                if old not in mapping:
                                    raise RuntimeError("Unplanned occurrence source")
                                wanted = Path(mapping[old])
                                if not wanted.is_file() or not wanted.resolve().is_relative_to(target):
                                    raise RuntimeError("Occurrence target is absent or outside copy")
                                if path_key(source_path) != path_key(wanted):
                                    child.FileName = str(wanted)
                                    require(child.Update(), "update rebound copy occurrence")
                            else:
                                # Traverse only embedded children owned by this file.
                                # External children are processed separately bottom-up;
                                # never mutate their native objects through a parent.
                                pending.append((child, occurrence_path))
                copied.SaveAs(mapping[key])
                if copied.Changed or not Path(mapping[key]).is_file():
                    raise RuntimeError("Native save did not leave a clean copied document")
            phase = f"reopen:{mapping[key]}"
            with native_document(k, mapping[key], True) as reopened:
                links = dependencies(k, reopened)
                outside = [link for link in links if not Path(link["path"]).resolve().is_relative_to(target)]
                if outside:
                    raise RuntimeError(f"Outside-copy links remain: {outside}")
                assert_occurrences(row["occurrences"], occurrence_snapshot(k, reopened), mapping)
                records[key]["reopened_links"] = links
                records[key]["copy_sha256"] = digest(mapping[key])
            report["completed_files"].append(mapping[key])
            write_json(manifest, report)
        report.update(status="passed", persistence_verified=True, outside_links=[],
                      placements_verified=True)
    except Exception as exc:  # noqa: BLE001 - preserve an inspectable partial copy
        report.update(status="failed", failed_phase=phase, error=str(exc), partial_output=True,
                      acceptance="Do not promote this copy; inspect manifest before retrying")
    finally:
        report["originals_unchanged"] = all(Path(row["source"]).is_file() and
                                              digest(row["source"]) == row["sha256"]
                                              for row in files.values())
        if not report["originals_unchanged"]:
            report.update(status="failed", source_integrity_error=True)
        write_json(manifest, report)
    return report
