"""Explicit STEP import on the owning STA worker; no adoption by filename alone."""

from pathlib import Path
from uuid import uuid4

from .backend import output_path, require
from .documents import KINDS, _info, save_evidence, verify_save


def document_reference(doc):
    value = doc.Reference
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise RuntimeError("Invalid native document Reference")
    return str(value)


def document_state(doc):
    return (doc.PathName, doc.DocumentType, bool(doc.Changed), bool(doc.ReadOnly))


def inventory(collection):
    rows = [collection.Item(i) for i in range(collection.Count)]
    result = {document_reference(doc): document_state(doc) for doc in rows}
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
    call_id = uuid4().hex  # one invocation token, created before Documents.Open
    before = inventory(collection)
    # An import can reuse an existing converted native document. Block known
    # collisions before Open, then verify identities afterwards as well.
    source_native = {source.with_suffix(ext) for ext in (".m3d", ".a3d")}
    if any(path and Path(path).resolve() in source_native | {source, target}
           for path, _, _, _ in before.values()):
        raise ValueError("Import path already open; no existing document may be adopted")
    doc = require(collection.Open(str(source), visible, False), "import STEP")
    after = inventory(collection)
    scope = document_reference(doc)
    if (scope in before or set(after) - set(before) != {scope}
            or any(after.get(key) != value for key, value in before.items())):
        raise RuntimeError("Uncertain import document set; ownership not granted; reconcile session")
    if after.get(scope) != document_state(doc):
        raise RuntimeError("Returned import document differs from the fresh inventory result")
    imported_state = document_state(doc)
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
    if doc.DocumentType != imported_state[1] or doc.ReadOnly:
        raise RuntimeError("Imported document kind/read-only state changed during SaveAs")
    saved_inventory = inventory(collection)
    if (document_reference(doc) != scope or set(saved_inventory) - set(before) != {scope}
            or any(saved_inventory.get(key) != value for key, value in before.items())
            or saved_inventory.get(scope) != document_state(doc)):
        raise RuntimeError("Uncertain document set after SaveAs; ownership not granted")
    k.owned_documents.add(scope)
    return {**_info(k, doc), "import_call_id": call_id, "created_reference": scope,
            "inventory_before": before, "inventory_after_open": after,
            "inventory_after_save": saved_inventory,
            "changed_after_import": imported_state[2],
            "imported_document_kind": native_kind,
            "ownership_basis": "single fresh result of this call plus verified owned SaveAs",
            "input_sha256": source_before[2], "import_source": str(source), "converted_path": str(actual),
            "saved_path": str(target), "save_evidence": evidence,
            "geometry_verified": False, "reopen_verified": False}
