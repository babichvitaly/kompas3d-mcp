"""Native API7 document lifecycle and assembly access, run on the COM worker."""

import hashlib
from pathlib import Path
from typing import Literal

from .backend import output_path, require
from .instrumentation import timed_phase
from .job_results import phase

DocumentKind = Literal["part", "assembly", "drawing", "fragment", "specification", "text"]
KINDS = {
    "part": ("ksDocumentPart", ".m3d"),
    "assembly": ("ksDocumentAssembly", ".a3d"),
    "drawing": ("ksDocumentDrawing", ".cdw"),
    "fragment": ("ksDocumentFragment", ".frw"),
    "specification": ("ksDocumentSpecification", ".spw"),
    "text": ("ksDocumentTextual", ".kdw"),
}


def _cast(k, obj, interface):
    import pythoncom

    wrapper = getattr(k.modules["kAPI7"], interface)
    return wrapper(obj._oleobj_.QueryInterface(wrapper.CLSID, pythoncom.IID_IDispatch))


def _document(k, handle):
    doc = _cast(k, k.get_handle(handle), "IKompasDocument")
    # Accessing identity also rejects disconnected COM objects before mutation.
    _ = doc.DocumentType
    return doc


def _summary(k, doc):
    """Read only document metadata; no TopPart, views or geometry expansion."""
    scope = str(doc.Reference)
    document_type = doc.DocumentType
    kind = next((name for name, (constant, _) in KINDS.items()
                 if k.constants[constant] == document_type), "unknown")
    result = {
        "document": k.pack(doc, scope), "kind": kind, "name": doc.Name,
        "path": doc.PathName, "changed": bool(doc.Changed),
        "read_only": bool(doc.ReadOnly), "visible": bool(doc.Visible),
        "active": bool(doc.Active), "owned_by_server": scope in k.owned_documents,
    }
    document_id = next((key for key, value in k.document_scopes.items() if value == scope), None)
    if document_id:
        result["document_id"] = document_id
    return result


def _info(k, doc):
    result = _summary(k, doc)
    scope, kind = str(doc.Reference), result["kind"]
    if kind in {"part", "assembly"}:
        model = _cast(k, doc, "IKompasDocument3D")
        top_part = model.TopPart
        result.update(model=k.pack(model, scope), top_part=k.pack(top_part, scope))
        native = require(k.app.ksGetDocumentByReference(doc.Reference), "get API5 document")
        document_id = k.register_document(native)
        result["document_id"] = document_id
        k.model_features[document_id] = _cast(k, top_part, "IFeature7")
        k.document_scopes[document_id] = scope
    elif kind in {"drawing", "fragment"}:
        drawing = _cast(k, doc, "IKompasDocument2D")
        result.update(
            drawing=k.pack(drawing, scope), views=k.pack(drawing.ViewsAndLayersManager.Views, scope)
        )
    return result


def _reconcile(k, docs):
    live = {str(doc.Reference) for doc in docs}
    # Legacy API5 entry points also have a scope, even before an API7 list.
    for document_id, native in list(k.documents.items()):
        if document_id not in k.document_scopes:
            try:
                k.document_scopes[document_id] = str(native.reference)
            except Exception:  # noqa: BLE001 - disconnected legacy COM alias
                k.documents.pop(document_id, None)
                k.model_features.pop(document_id, None)
                k.entities = {key: value for key, value in k.entities.items()
                              if value[0] != document_id}
    known = set(k.handle_scopes.values()) | set(k.document_scopes.values()) | k.owned_documents
    for scope in known - live - {None}:
        k.forget_document_scope(scope)


@timed_phase("native.documents.inventory")
def list_documents(k, details: bool = True):
    """Legacy detailed mode remains default; details=False is the inexpensive list."""
    k.connect()
    collection = k.app.ksGetApplication7().Documents
    docs = [collection.Item(i) for i in range(collection.Count)]
    _reconcile(k, docs)
    describe = _info if details else _summary
    return {"documents": [describe(k, doc) for doc in docs]}


def document_details(k, handle: str):
    return _info(k, _document(k, handle))


def create_document(k, kind: DocumentKind, visible: bool = True):
    if kind not in KINDS:
        raise ValueError(f"Expected document kind in {list(KINDS)}")
    k.connect()
    doc = require(
        k.app.ksGetApplication7().Documents.Add(k.constants[KINDS[kind][0]], visible),
        f"create {kind}",
    )
    k.owned_documents.add(str(doc.Reference))
    return _info(k, doc)


@timed_phase("native.document.open")
def open_document(
    k, path: str, read_only: bool = False, visible: bool = True, reuse_existing: bool = True
):
    source = Path(path).expanduser()
    if not source.is_absolute() or not source.is_file():
        raise ValueError("Expected absolute path to an existing document")
    if source.suffix.lower() not in {extension for _, extension in KINDS.values()}:
        raise ValueError("Expected a native KOMPAS document")
    k.connect()
    collection = k.app.ksGetApplication7().Documents
    if reuse_existing:
        for i in range(collection.Count):
            existing = collection.Item(i)
            if existing.PathName and Path(existing.PathName).resolve() == source.resolve():
                if read_only and not existing.ReadOnly:
                    raise ValueError(
                        "read_only_mismatch: existing document is writable; "
                        "use a separate copy for a read-only audit"
                    )
                return {**_info(k, existing), "reused": True}
    before = {str(collection.Item(i).Reference) for i in range(collection.Count)}
    doc = require(
        collection.Open(str(source.resolve()), visible, read_only),
        "open native document",
    )
    reused = str(doc.Reference) in before
    if not reused:
        k.owned_documents.add(str(doc.Reference))
    result = {**_info(k, doc), "reused": reused}
    if read_only and not result["read_only"]:
        raise RuntimeError("read_only_mismatch: KOMPAS opened a writable document; inspect it")
    return result


def save_evidence(target):
    if not target.is_file():
        return None
    stat = target.stat()
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return (stat.st_size, stat.st_mtime_ns, digest.hexdigest())


def verify_save(target, before, actual_path, changed=False):
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("save_unconfirmed: SaveAs did not produce a nonempty file")
    if not actual_path or Path(actual_path).resolve() != target.resolve() or changed:
        raise RuntimeError("save_unconfirmed: native path/Changed postcondition failed")
    after = save_evidence(target)
    if before is not None and before == after:
        raise RuntimeError("save_unconfirmed: existing output has no write evidence; inspect it")
    return {"write_evidence": "created" if before is None else "updated",
            "sha256": after[2], "changed": bool(changed)}


@timed_phase("native.document.save")
def save_document(k, handle: str, path: str, overwrite: bool = False):
    doc = _document(k, handle)
    if doc.ReadOnly:
        raise ValueError("Document is read-only")
    extensions = {extension for constant, extension in KINDS.values()
                  if k.constants[constant] == doc.DocumentType}
    target = output_path(path, extensions, overwrite)
    before = save_evidence(target)
    with phase("native.document.SaveAs", counts={"native_calls": 1}):
        doc.SaveAs(str(target))  # API7 SaveAs is void; do not infer success from return value.
    evidence = verify_save(target, before, doc.PathName, bool(doc.Changed))
    return {"path": str(target), "bytes": target.stat().st_size,
            "document": {"handle": handle}, **evidence}


@timed_phase("native.document.close")
def close_document(k, handle: str, discard_changes: bool = False):
    doc = _document(k, handle)
    scope = str(doc.Reference)
    # Reconcile API5 IDs before releasing the native document. Never infer ownership.
    for document_id, native in list(k.documents.items()):
        if document_id not in k.document_scopes:
            k.document_scopes[document_id] = str(native.reference)
    if doc.Changed and not discard_changes:
        raise ValueError("Document has unsaved changes; save it or explicitly discard_changes")
    require(doc.Close(k.constants["kdDoNotSaveChanges"]), "close document")
    released = k.forget_document_scope(scope)
    return {"closed": True, "released_handles": released}


def close_documents(k, keep: list[str], candidates: list[str] | None = None, dry_run: bool = True):
    """Close only explicit or server-owned unchanged candidates; no implicit discard.

    Handles come from a fresh summary list. Identity, path and Changed are checked
    again immediately before each close. Partial closure is returned, never retried.
    """
    listed = list_documents(k, details=False)["documents"]
    by_handle = {row["document"]["handle"]: row for row in listed}
    if len(keep) != len(set(keep)) or (candidates and len(candidates) != len(set(candidates))):
        raise ValueError("Keep and candidate handles must be unique")
    if any(handle not in by_handle for handle in keep + (candidates or [])):
        raise ValueError("stale_handle: refresh the document list before closing")
    selected = candidates if candidates is not None else [
        key for key, row in by_handle.items() if row["owned_by_server"]]
    if set(keep) & set(selected) and candidates is not None:
        raise ValueError("Keep and explicit candidates overlap")
    keep_scopes = {str(_document(k, handle).Reference) for handle in keep}
    plan = []
    for handle in selected:
        row = by_handle[handle]
        doc = _document(k, handle)
        scope = str(doc.Reference)
        state = "kept" if scope in keep_scopes else (
            "skipped_changed" if doc.Changed else "candidate")
        plan.append({"handle": handle, "scope": scope, "path": row["path"],
                     "name": row["name"], "state": state})
    if not dry_run:
        for row in plan:
            if row["state"] != "candidate":
                continue
            try:
                doc = _document(k, row["handle"])
                if str(doc.Reference) != row["scope"] or doc.PathName != row["path"]:
                    row["state"] = "skipped_identity_changed"
                elif doc.Changed:
                    row["state"] = "skipped_changed"
                else:
                    # close_document repeats Changed immediately adjacent to Close.
                    close_document(k, row["handle"])
                    row["state"] = "closed"
            except Exception as exc:  # noqa: BLE001 - preserve partial batch result
                row.update(state="failed", error=str(exc))
    return {"dry_run": dry_run, "documents": plan,
            "closed_count": sum(row["state"] == "closed" for row in plan),
            "discarded_changes": False}


def insert_component(k, assembly_handle: str, path: str, linked: bool = True):
    doc = _document(k, assembly_handle)
    if doc.DocumentType != k.constants["ksDocumentAssembly"]:
        raise ValueError("Target document must be an assembly")
    if doc.ReadOnly:
        raise ValueError("Assembly is read-only")
    source = Path(path).expanduser()
    if (
        not source.is_absolute()
        or not source.is_file()
        or source.suffix.lower() not in {".m3d", ".a3d"}
    ):
        raise ValueError("Expected an absolute path to a native part or assembly")
    model = _cast(k, doc, "IKompasDocument3D")
    component = require(
        model.TopPart.Parts.AddFromFile(str(source.resolve()), linked, True),
        "insert assembly component",
    )
    return {
        "component": k.pack(component),
        "name": component.Name,
        "source": str(source.resolve()),
        "linked": linked,
        "placement": k.pack(component.Placement),
    }


@timed_phase("native.views.create")
def create_standard_views(
    k,
    drawing_handle: str,
    model_path: str,
    projections: list[str],
    x: float = 100,
    y: float = 150,
    scale: float = 1,
    gap_x: float = 30,
    gap_y: float = 30,
    orientation: str = "",
    draft_projection: bool = False,
):
    """Add and verify associative model views using exact projection by default.

    orientation is a native named model orientation. draft_projection selects
    the SDK's draft projection mode (IAssociationView.UseOcclusion).
    """
    import math

    import pythoncom
    from win32com.client import VARIANT

    projection_constants = {
        "front": "ksPtFront",
        "rear": "ksPtRear",
        "top": "ksPtUp",
        "bottom": "ksPtDown",
        "left": "ksPtLeft",
        "right": "ksPtRight",
        "isometric": "ksPtIsoXYZ",
    }
    if not projections or any(p not in projection_constants for p in projections):
        raise ValueError(f"Choose projections from {list(projection_constants)}")
    if len(set(projections)) != len(projections):
        raise ValueError("Projection names must be unique")
    if not all(math.isfinite(v) for v in (x, y, scale, gap_x, gap_y)) or scale <= 0:
        raise ValueError("Coordinates and gaps must be finite; scale must be positive")
    doc = _document(k, drawing_handle)
    if doc.DocumentType != k.constants["ksDocumentDrawing"] or doc.ReadOnly:
        raise ValueError("Expected a writable drawing document")
    source = Path(model_path).expanduser()
    if (
        not source.is_absolute()
        or not source.is_file()
        or source.suffix.lower() not in {".m3d", ".a3d"}
    ):
        raise ValueError("Expected absolute path to an existing native model")
    drawing = _cast(k, doc, "IKompasDocument2D")
    views = drawing.ViewsAndLayersManager.Views
    before = views.Count
    before_references = {views.View(i).Reference for i in range(before)}

    def new_views():
        # View numbers/indices can be reused or reordered. Only native identity
        # distinguishes new views from the user's existing drawing contents.
        current = [views.View(i) for i in range(views.Count)]
        return [view for view in current if view.Reference not in before_references]

    kinds = VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_I4,
        [k.constants[projection_constants[p]] for p in projections],
    )
    try:
        require(
            views.AddStandartViews(
                str(source.resolve()), orientation, kinds, x, y, scale, gap_x, gap_y
            ),
            "create associative views",
        )
        created = new_views()
        if len(created) != len(projections):
            raise RuntimeError(
                f"Expected {len(projections)} new views, found {len(created)}"
            )
        associations = [_cast(k, view, "IAssociationView") for view in created]
        for view in associations:
            # AddStandartViews inherits application defaults. Draft projection
            # reported success but no drawing objects on the tested installation.
            view.UseOcclusion = draft_projection
            with phase("native.view.update", counts={"native_calls": 1}):
                require(view.Update(), f"update view {view.Number}")
            with phase("native.view.rebuild", counts={"native_calls": 1}):
                require(view.Rebuild(), f"rebuild view {view.Number}")
        metadata = [
            {
                "number": view.Number,
                **k.pack(view),
                "object_count": view.ObjectCount,
                "draft_projection": bool(view.UseOcclusion),
                "valid": bool(view.Valid),
            }
            for view in associations
        ]
        if any(
            not view["valid"]
            or view["object_count"] <= 0
            or view["draft_projection"] != draft_projection
            for view in metadata
        ):
            raise RuntimeError("New views are invalid, empty, or use the wrong projection mode")
    except Exception as exc:
        try:
            partial = [
                {"number": view.Number, "object_count": view.ObjectCount}
                for view in new_views()
            ]
        except Exception as diagnostic_error:  # noqa: BLE001 - preserve the original COM error
            partial = f"unavailable ({diagnostic_error})"
        raise RuntimeError(
            f"Associative view creation failed: {exc}. Created views: {partial}. "
            "Any partially created views remain in the drawing; inspect them before retrying."
        ) from exc
    return {
        "views": k.pack(views),
        "count_before": before,
        "count_after": views.Count,
        "created_count": len(metadata),
        "created_views": metadata,
        "model_path": str(source.resolve()),
    }


def _finite(*values):
    import math

    if not all(math.isfinite(v) for v in values):
        raise ValueError("All coordinates and dimensions must be finite")


def _drawing_view(k, drawing_handle, view_number):
    doc = _document(k, drawing_handle)
    if doc.ReadOnly or doc.DocumentType not in {
        k.constants["ksDocumentDrawing"],
        k.constants["ksDocumentFragment"],
    }:
        raise ValueError("Expected a writable drawing or fragment")
    drawing = _cast(k, doc, "IKompasDocument2D")
    return require(
        drawing.ViewsAndLayersManager.Views.ViewByNumber(view_number), "find drawing view"
    )


def draw_line(
    k,
    drawing_handle: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    style: int = 1,
    view_number: int = 0,
):
    """Draw a native segment in a numbered view's local millimetre coordinates."""
    _finite(x1, y1, x2, y2)
    if (x1, y1) == (x2, y2) or style < 1:
        raise ValueError("Line endpoints must differ and style must be positive")
    view = _drawing_view(k, drawing_handle, view_number)
    line = require(_cast(k, view, "IDrawingContainer").LineSegments.Add(), "add line")
    line.X1, line.Y1, line.X2, line.Y2, line.Style = x1, y1, x2, y2, style
    require(line.Update(), "update drawing line")
    return {"object": k.pack(line), "length_mm": line.Length, "view_number": view_number}


def draw_circle(
    k, drawing_handle: str, x: float, y: float, radius: float, style: int = 1, view_number: int = 0
):
    _finite(x, y, radius)
    if radius <= 0 or style < 1:
        raise ValueError("Radius and style must be positive")
    view = _drawing_view(k, drawing_handle, view_number)
    circle = require(_cast(k, view, "IDrawingContainer").Circles.Add(), "add circle")
    circle.Xc, circle.Yc, circle.Radius, circle.Style = x, y, radius, style
    require(circle.Update(), "update drawing circle")
    return {"object": k.pack(circle), "radius_mm": circle.Radius, "view_number": view_number}


def draw_linear_dimension(
    k,
    drawing_handle: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    text_x: float,
    text_y: float,
    orientation: Literal["horizontal", "vertical", "parallel"] = "parallel",
    view_number: int = 0,
):
    """Native measured dimension between coordinates; not a geometry constraint."""
    _finite(x1, y1, x2, y2, text_x, text_y)
    names = {
        "horizontal": "ksLinDHorizontal",
        "vertical": "ksLinDVertical",
        "parallel": "ksLinDParallel",
    }
    if orientation not in names or (x1, y1) == (x2, y2):
        raise ValueError("Expected distinct points and horizontal/vertical/parallel orientation")
    view = _drawing_view(k, drawing_handle, view_number)
    dim = require(_cast(k, view, "ISymbols2DContainer").LineDimensions.Add(), "add dimension")
    dim.X1, dim.Y1, dim.X2, dim.Y2 = x1, y1, x2, y2
    dim.X3, dim.Y3, dim.Orientation = text_x, text_y, k.constants[names[orientation]]
    text = _cast(k, dim, "IDimensionText")
    text.AutoNominalValue = True
    require(dim.Update(), "update linear dimension")
    return {
        "object": k.pack(dim),
        "dimension_text": k.pack(text),
        "nominal_value": text.NominalValue,
        "view_number": view_number,
    }


def draw_text(
    k, drawing_handle: str, text: str, x: float, y: float, angle: float = 0, view_number: int = 0
):
    """Draw native editable text using the document's default text style."""
    _finite(x, y, angle)
    if not text.strip():
        raise ValueError("Text cannot be blank")
    view = _drawing_view(k, drawing_handle, view_number)
    drawing_text = require(_cast(k, view, "IDrawingContainer").DrawingTexts.Add(), "add text")
    drawing_text.X, drawing_text.Y, drawing_text.Angle = x, y, angle
    content = _cast(k, drawing_text, "IText")
    content.Str = text
    require(drawing_text.Update(), "update drawing text")
    return {"object": k.pack(drawing_text), "text": content.Str, "view_number": view_number}
