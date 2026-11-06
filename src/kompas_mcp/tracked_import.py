"""Explicit STEP import on the owning STA worker; no adoption by filename alone."""

from pathlib import Path

from .backend import output_path, require
from .documents import KINDS, _info, save_evidence, verify_save


def inventory(collection):
    rows = [collection.Item(i) for i in range(collection.Count)]
    result = {str(doc.Reference): (doc.PathName, doc.DocumentType) for doc in rows}
    if len(result) != len(rows):
        raise RuntimeError("Duplicate document identity in native inventory")
    return result


def import_step(k, source, owned_root, target, visible=True):
    """Open one new STEP document, validate actual native kind/path, then SaveAs.

    Caller must exclusively own the CAD session. Ownership is granted only after
    verified SaveAs. On any failure leave documents untouched for reconciliation;
    do not retry, close unknown documents, or infer ownership from the target path.
    No geometry/reopen acceptance is claimed by this lifecycle operation.
    """
    source, root, target = [Path(p).expanduser() for p in (source, owned_root, target)]
    if not all(p.is_absolute() for p in (source, root, target)):
        raise ValueError("Use absolute source, owned root and target paths")
    source, root, target = [p.resolve() for p in (source, root, target)]
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("Expected an existing STEP source")
    if not root.is_dir() or target == root or not target.is_relative_to(root):
        raise ValueError("Target must be inside the explicit owned root")
    target = output_path(str(target), {".m3d", ".a3d"}, overwrite=False)
    source_before = save_evidence(source)
    k.connect()
    collection = k.app.ksGetApplication7().Documents
    before = inventory(collection)
    # An import can reuse an existing converted native document. Block known
    # collisions before Open, then verify identities afterwards as well.
    source_native = {source.with_suffix(ext) for ext in (".m3d", ".a3d")}
    if any(path and Path(path).resolve() in source_native | {source, target}
           for path, _ in before.values()):
        raise ValueError("Import path already open; no existing document may be adopted")
    doc = require(collection.Open(str(source), visible, False), "import STEP")
    after = inventory(collection)
    scope = str(doc.Reference)
    if (scope in before or set(after) - set(before) != {scope}
            or any(after.get(key) != value for key, value in before.items())):
        raise RuntimeError("Uncertain import document set; ownership not granted; reconcile session")
    native_kind = next((kind for kind in ("part", "assembly")
                        if doc.DocumentType == k.constants[KINDS[kind][0]]), None)
    if not native_kind or doc.ReadOnly:
        raise RuntimeError("Import must produce a writable native part or assembly")
    extension = KINDS[native_kind][1]
    actual = Path(doc.PathName).resolve() if doc.PathName else None
    if actual != source.with_suffix(extension) or target.suffix.lower() != extension:
        raise RuntimeError("Unexpected converted native path/kind or target extension")
    if save_evidence(source) != source_before:
        raise RuntimeError("STEP source changed during import; ownership not granted")
    # Recheck freshness immediately before SaveAs; never overwrite an existing file.
    output_path(str(target), {extension}, overwrite=False)
    doc.SaveAs(str(target))
    evidence = verify_save(target, None, doc.PathName, bool(doc.Changed))
    if save_evidence(source) != source_before:
        raise RuntimeError("STEP source changed during save; ownership not granted")
    saved_inventory = inventory(collection)
    if (str(doc.Reference) != scope or set(saved_inventory) - set(before) != {scope}
            or any(saved_inventory.get(key) != value for key, value in before.items())
            or saved_inventory.get(scope) != (doc.PathName, doc.DocumentType)):
        raise RuntimeError("Uncertain document set after SaveAs; ownership not granted")
    k.owned_documents.add(scope)
    return {**_info(k, doc), "import_source": str(source), "converted_path": str(actual),
            "saved_path": str(target), "save_evidence": evidence,
            "geometry_verified": False, "reopen_verified": False}
