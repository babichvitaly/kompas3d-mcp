"""Checked native drawing inventories, source rebinding and export on the STA.

No operation implicitly saves, recreates views or changes a model. Export reports
native converter source-close/reopen effects explicitly and refreshes its owned
copy handle. A failed mutation leaves its partial native result inspectable and
writes a report when requested. Successful Rebuild alone is not geometry proof.
"""

import hashlib
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

from . import documents
from .backend import require
from .documents import _cast, _document
from .instrumentation import timed_phase
from .job_results import phase
from .project_copy import native_document, verify_external_isolation

GEOMETRY = {
    "lines": ("LineSegments", "LineSegment", ("X1", "Y1", "X2", "Y2", "Style")),
    "circles": ("Circles", "Circle", ("Xc", "Yc", "Radius", "Style")),
    "arcs": ("Arcs", "Arc", ("Xc", "Yc", "Radius", "X1", "Y1", "X2", "Y2", "Direction", "Style")),
}
DIM_PROPS = ("X1", "Y1", "X2", "Y2", "X3", "Y3", "Orientation")
VIEW_PROPS = ("Number", "Name", "ViewType", "X", "Y", "Scale", "Angle", "ObjectCount", "Valid")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode("utf-8")).hexdigest()


@timed_phase("source.sha256")
def _file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _props(obj, names):
    return {name: getattr(obj, name) for name in names}


def _text_value(obj):
    """Read SDK IText/ITextLine.Str, never stringify a COM proxy representation."""
    value = obj.Str
    if not isinstance(value, str):
        raise TypeError("Native IText/ITextLine.Str did not return a BSTR string")
    return value


def _inside(path, root, extensions, exists=True):
    source = Path(path).expanduser()
    if not source.is_absolute():
        raise ValueError("An absolute copy path is required")
    source = source.resolve()
    if not source.is_relative_to(root) or source.suffix.lower() not in extensions:
        raise ValueError("Path must have the requested extension inside copy_root")
    if exists and not source.is_file():
        raise ValueError("The requested copy file does not exist")
    return source


def _copy(k, handle, copy_root, writable=True):
    folder = Path(copy_root).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError("copy_root must be an existing absolute directory")
    folder = folder.resolve()
    doc = _document(k, handle)
    if doc.DocumentType != k.constants["ksDocumentDrawing"]:
        raise ValueError("A native drawing is required")
    if writable and doc.ReadOnly:
        raise ValueError("A writable drawing copy is required")
    if str(doc.Reference) not in k.owned_documents:
        raise ValueError("Open the isolated drawing copy with this server first")
    path = _inside(doc.PathName, folder, {".cdw"})
    return doc, folder, path


@timed_phase("source.boundary")
def _dependency_snapshot(k, doc, root, sources=()):
    """Read the recursive SDK closure of the CDW and every old/new model root.

    Reuse only clean open linked documents; temporary opens are read-only and
    closed by the existing single-STA lifecycle helper. No model rebuild/save.
    Current drawing dirty state is covered by its native content fingerprint;
    every other open dependency must represent the checked bytes on disk.
    """
    files = {Path(doc.PathName).resolve()}

    def add_links(owner):
        for row in verify_external_isolation(k, owner, root):
            path = Path(row["path"]).resolve()
            if not path.is_file() or not path.is_relative_to(root):
                raise ValueError(f"Missing or outside-copy dependency: {path}")
            files.add(path)

    add_links(doc)
    for source in sorted({Path(path).resolve() for path in sources}):
        if not source.is_file() or not source.is_relative_to(root):
            raise ValueError(f"Missing or outside-copy source: {source}")
        files.add(source)
        with native_document(k, source, read_only=True) as linked:
            add_links(linked)
    by_name = {str(path).casefold() for path in files}
    collection = k.app.ksGetApplication7().Documents
    for index in range(collection.Count):
        opened = collection.Item(index)
        if (opened.PathName and Path(opened.PathName).resolve() != Path(doc.PathName).resolve()
                and str(Path(opened.PathName).resolve()).casefold() in by_name and opened.Changed):
            raise ValueError(f"Unsaved linked document changes; disk geometry is stale: {opened.PathName}")
    return {str(path): _file_hash(path) for path in sorted(files)}


def _stamp(sheet, limit):
    """SDK GetNextColumnId enumerates nonempty cells, rather than guessed IDs."""
    stamp = sheet.Stamp
    result = {}
    cell = 0
    while True:
        cell = int(stamp.GetNextColumnId(cell))
        if cell <= 0:
            break
        if str(cell) in result or len(result) >= limit:
            raise RuntimeError("Stamp enumeration repeated an ID or exceeded the inventory limit")
        result[str(cell)] = _text_value(stamp.Text(cell))
    return result


@timed_phase("native.drawing.inventory")
def _inventory(k, doc, geometry, max_objects):
    drawing = _cast(k, doc, "IKompasDocument2D")
    views = drawing.ViewsAndLayersManager.Views
    result = {"path": doc.PathName, "read_only": bool(doc.ReadOnly),
              "changed": bool(doc.Changed), "views": [], "sheets": [],
              "geometry_scope": "line segments, circles and circular arcs; not all 2D types"}
    objects = {}
    consumed = 0

    def budget(count):
        nonlocal consumed
        consumed += count
        if consumed > max_objects:
            raise ValueError("Drawing inventory exceeds max_objects; no partial acceptance")

    budget(int(views.Count))
    for i in range(views.Count):
        view = views.View(i)
        row = {"reference": view.Reference, **_props(view, VIEW_PROPS)}
        refs = {"view": view, "dimensions": []}
        # ViewType is the documented discriminator; a failed cast of an expected
        # associative view must not silently turn it into an ordinary view.
        if view.ViewType in {k.constants[name] for name in (
            "vt_Arbitrary", "vt_Standart", "vt_Projected", "vt_Arrow", "vt_Remote", "vt_Section"
        )}:
            assoc = _cast(k, view, "IAssociationView")
            row["association"] = _props(assoc, ("SourceFileName", "UseOcclusion", "Valid"))
            refs["association"] = assoc
        symbols = _cast(k, view, "ISymbols2DContainer")
        row["dimensions"] = []
        budget(int(symbols.LineDimensions.Count))
        for j in range(symbols.LineDimensions.Count):
            dim = _cast(k, symbols.LineDimensions.Item(j), "ILineDimension")
            text = _cast(k, dim, "IDimensionText")
            row["dimensions"].append({"reference": dim.Reference, "Valid": bool(dim.Valid),
                                      **_props(dim, DIM_PROPS),
                                      "text": {**_props(text, ("AutoNominalValue", "NominalValue",
                                                              "Accuracy")),
                                               # SDK IDimensionText.NominalText is an
                                               # ITextLine interface, not a BSTR.
                                               "NominalText": _text_value(_cast(
                                                   k, text.NominalText, "ITextLine"))}})
            refs["dimensions"].append(dim)
        row["leaders"] = []
        budget(int(symbols.Leaders.Count))
        for j in range(symbols.Leaders.Count):
            leader = symbols.Leaders.Item(j)
            row["leaders"].append({"reference": leader.Reference, "Valid": bool(leader.Valid)})
        container = _cast(k, view, "IDrawingContainer")
        row["texts"] = []
        budget(int(container.DrawingTexts.Count))
        for j in range(container.DrawingTexts.Count):
            text = _cast(k, container.DrawingTexts.Item(j), "IDrawingText")
            row["texts"].append({"reference": text.Reference,
                                 **_props(text, ("X", "Y", "Angle", "Height", "Width", "Valid")),
                                 "text": _text_value(_cast(k, text, "IText"))})
        if geometry:
            row["geometry"] = {}
            for key, (collection, getter, properties) in GEOMETRY.items():
                items = getattr(container, collection)
                budget(int(items.Count))
                row["geometry"][key] = [_props(getattr(items, getter)(j), properties)
                                         for j in range(items.Count)]
            row["geometry_digest"] = _digest(row["geometry"])
        result["views"].append(row)
        if row["Number"] in objects:
            raise ValueError("Ambiguous native view number")
        objects[row["Number"]] = refs
    sheets = drawing.LayoutSheets
    budget(int(sheets.Count))
    for i in range(sheets.Count):
        sheet = sheets.Item(i)
        result["sheets"].append({**_props(sheet, ("LayoutLibraryFileName", "LayoutStyleNumber",
                                               "SheetType")), "stamp": _stamp(sheet, max_objects)})
    result["inventoried_objects"] = consumed
    # Exclude dirty state: a focus/display operation can change it without geometry.
    result["fingerprint"] = _digest({key: value for key, value in result.items()
                                     if key not in {"changed", "read_only"}})
    return result, objects


def _report(path, result, root=None):
    if not path:
        return
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise ValueError("report_path must be absolute")
    target = target.resolve()
    if root is not None and not target.is_relative_to(root):
        raise ValueError("Report must be inside copy_root")
    if target.suffix.lower() != ".json":
        raise ValueError("report_path must end in .json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")


def inspect_drawing(k, handle, include_geometry=True, report_path=None, max_objects=50000):
    """Read native content without activating, rebuilding or saving the drawing."""
    if not 1 <= max_objects <= 200000:
        raise ValueError("max_objects must be 1..200000")
    if report_path and Path(report_path).exists():
        raise FileExistsError("Use a new inspection report path")
    doc = _document(k, handle)
    if doc.DocumentType != k.constants["ksDocumentDrawing"]:
        raise ValueError("Expected a drawing")
    result, _ = _inventory(k, doc, include_geometry, max_objects)
    _report(report_path, result)
    return result


def _near(a, b, tolerance=1e-8):
    return (isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool)
            and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance)


def _same(a, b, path="", tolerance=1e-8):
    if _near(a, b, tolerance):
        return
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        for key in a:
            _same(a[key], b[key], f"{path}.{key}", tolerance)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _same(x, y, f"{path}[{i}]", tolerance)
    elif a != b:
        raise RuntimeError(f"Unexpected drawing change at {path}: {a!r} -> {b!r}")


def _geometry_check(row, check, before):
    allowed = {"view_number", "line_count", "line_bounds", "geometry_digest",
               "different_from_before", "tolerance", "angle", "min_length", "min_angle_count"}
    if set(check) - allowed:
        raise ValueError("Unknown geometry check key")
    tolerance = check.get("tolerance", 1e-6)
    if not isinstance(tolerance, (int, float)) or not 0 < tolerance <= 0.1:
        raise ValueError("Geometry tolerance must be positive and <= 0.1 mm/degrees")
    if "line_count" in check and (not isinstance(check["line_count"], int)
                                  or isinstance(check["line_count"], bool)
                                  or check["line_count"] < 0):
        raise ValueError("line_count must be a nonnegative integer")
    if "line_bounds" in check and (not isinstance(check["line_bounds"], list)
                                   or len(check["line_bounds"]) != 4
                                   or not all(isinstance(value, (int, float))
                                              and not isinstance(value, bool) and math.isfinite(value)
                                              for value in check["line_bounds"])):
        raise ValueError("line_bounds must contain four finite numbers")
    if "angle" in check and (not all(isinstance(check.get(key, 0), (int, float))
                                      and math.isfinite(check.get(key, 0))
                                      for key in ("angle", "min_length"))
                             or check.get("min_length", 0) < 0
                             or not isinstance(check.get("min_angle_count", 1), int)
                             or check.get("min_angle_count", 1) < 1):
        raise ValueError("Expected finite angle, nonnegative length and positive edge count")
    lines = row["geometry"]["lines"]
    if "line_count" in check and len(lines) != check["line_count"]:
        raise RuntimeError("Projected line count differs from the explicit expectation")
    if "line_bounds" in check:
        if not lines or len(check["line_bounds"]) != 4:
            raise ValueError("line_bounds needs four values and nonempty line geometry")
        bounds = [min(p[q] for p in lines for q in ("X1", "X2")),
                  min(p[q] for p in lines for q in ("Y1", "Y2")),
                  max(p[q] for p in lines for q in ("X1", "X2")),
                  max(p[q] for p in lines for q in ("Y1", "Y2"))]
        _same(check["line_bounds"], bounds, "projected line bounds", tolerance)
    if "geometry_digest" in check and check["geometry_digest"] != row["geometry_digest"]:
        raise RuntimeError("Projected geometry digest differs from expectation")
    if check.get("different_from_before") and row["geometry_digest"] == before["geometry_digest"]:
        raise RuntimeError("Projection did not change although geometry change was required")
    if "angle" in check:
        if not all(math.isfinite(check.get(key, 0)) for key in ("angle", "min_length")):
            raise ValueError("Angle geometry check values must be finite")
        count = 0
        for line in lines:
            dx, dy = line["X2"]-line["X1"], line["Y2"]-line["Y1"]
            delta = (math.degrees(math.atan2(dy, dx))-check["angle"]) % 180
            if (math.hypot(dx, dy) >= check.get("min_length", 0)
                    and min(delta, 180-delta) <= tolerance):
                count += 1
        if count < check.get("min_angle_count", 1):
            raise RuntimeError("Expected inclined projected edges are absent")
    if not any(key in check for key in ("line_bounds", "geometry_digest", "angle")):
        raise ValueError("Each view needs geometric evidence: line_bounds, geometry_digest or angle")


def _plans(before, replacements, dimension_changes, view_changes, geometry_checks, root):
    views = {row["Number"]: row for row in before["views"]}
    selected = {}
    if not 1 <= len(replacements) <= 100:
        raise ValueError("Supply 1..100 explicit associative view replacements")
    for item in replacements:
        if set(item) != {"view_number", "expected_source", "source"}:
            raise ValueError("A replacement needs view_number, expected_source and source")
        number = item["view_number"]
        if (not isinstance(number, int) or isinstance(number, bool) or number in selected
                or number not in views or "association" not in views[number]):
            raise ValueError("Select distinct existing associative views")
        expected = _inside(item["expected_source"], root, {".m3d", ".a3d"})
        actual = Path(views[number]["association"]["SourceFileName"]).resolve()
        if actual != expected:
            raise ValueError("Stale associative source expectation")
        selected[number] = str(_inside(item["source"], root, {".m3d", ".a3d"}))
    dims = {}
    for item in dimension_changes:
        if set(item) != {"view_number", "index", "expected", "endpoints", "expected_after"}:
            raise ValueError("Dimension changes need view_number, index, expected, endpoints, expected_after")
        number, index = item["view_number"], item["index"]
        if number not in views or not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("Invalid dimension view/index")
        if not 0 <= index < len(views[number]["dimensions"]) or (number, index) in dims:
            raise ValueError("Select distinct existing dimensions")
        row = views[number]["dimensions"][index]
        _same(row, item["expected"], "expected dimension")
        if (not item["endpoints"] or set(item["endpoints"]) - {"X1", "Y1", "X2", "Y2"}
                or set(item["expected_after"]) != {*DIM_PROPS, "NominalValue"}):
            raise ValueError("Explicit endpoints and complete expected_after coordinates/nominal required")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   for v in [*item["endpoints"].values(), *item["expected_after"].values()]):
            raise ValueError("Dimension values must be finite numbers")
        if any(item["expected_after"][key] != value for key, value in item["endpoints"].items()):
            raise ValueError("Expected dimension endpoints must match the requested writes")
        dims[number, index] = item
    shifts = {}
    for item in view_changes:
        if set(item) != {"view_number", "expected_x", "expected_y"}:
            raise ValueError("view_changes only acknowledges expected_x and expected_y native shifts")
        number = item["view_number"]
        if number not in selected or number in shifts:
            raise ValueError("View shift must select a distinct rebound view")
        if not all(math.isfinite(item[key]) for key in ("expected_x", "expected_y")):
            raise ValueError("Expected view positions must be finite")
        shifts[number] = item
    checks = {}
    for check in geometry_checks:
        number = check.get("view_number")
        if number not in selected or number in checks:
            raise ValueError("Geometry checks must select distinct rebound views")
        # Check schema and geometric target before entering a mutation, but the
        # old projection is allowed not to meet the requested new target yet.
        try:
            _geometry_check(views[number], check, views[number])
        except RuntimeError:
            pass
        checks[number] = check
    if checks.keys() != selected.keys():
        raise ValueError("Every rebound view needs an explicit geometry check")
    return selected, dims, shifts, checks


def _preserve(before, after, selected, dims, shifts, checks):
    if len(before["views"]) != len(after["views"]):
        raise RuntimeError("A drawing view was created or removed")
    _same(before["sheets"], after["sheets"], "sheets/stamp")
    new = {row["Number"]: row for row in after["views"]}
    for old in before["views"]:
        number = old["Number"]
        if number not in new:
            raise RuntimeError("Native view identity/number disappeared")
        row = new[number]
        for key in ("reference", "Number", "Name", "ViewType", "Scale", "Angle"):
            _same(old[key], row[key], f"view {number}.{key}")
        for key in ("X", "Y"):
            expected = shifts.get(number, {}).get("expected_"+key.lower(), old[key])
            _same(expected, row[key], f"view {number}.{key}")
        for key in ("texts", "leaders"):
            _same(old[key], row[key], f"view {number}.{key}")
        if len(old["dimensions"]) != len(row["dimensions"]):
            raise RuntimeError("A native dimension was created or removed")
        for index, (a, b) in enumerate(zip(old["dimensions"], row["dimensions"], strict=True)):
            if (number, index) not in dims:
                _same(a, b, f"view {number}.dimension {index}")
            else:
                expected = json.loads(json.dumps(a))
                for key, value in dims[number, index]["expected_after"].items():
                    if key == "NominalValue":
                        expected["text"][key] = value
                    else:
                        expected[key] = value
                # NominalText follows native formatting; all formatting settings
                # and AutoNominalValue remain protected.
                expected["text"]["NominalText"] = b["text"]["NominalText"]
                _same(expected, b, f"view {number}.dimension {index}")
            if not b["Valid"]:
                raise RuntimeError("An invalid dimension remains after rebuild")
        if number in selected:
            if (not row["Valid"] or row["ObjectCount"] <= 0
                    or row["association"]["UseOcclusion"]
                    or not row["association"]["Valid"]
                    or Path(row["association"]["SourceFileName"]).resolve()
                    != Path(selected[number]).resolve()):
                raise RuntimeError("Rebound view is invalid, empty, draft or uses the wrong source")
            _geometry_check(row, checks[number], old)
        else:
            expected = {**old, "dimensions": row["dimensions"]}
            _same(expected, row, f"unselected view {number}")


def _auto_scale_caption(text, scale):
    """Recognize only the measured native scale-only view designation grammar.

    Every byte must belong to four parameter tokens. Ordinary user text, extra
    parameter kinds, displayed custom names/angles and mismatched scale fail
    recognition. This parser is necessary but not sufficient for deletion: the
    native IViewDesignation.DrawingText identity is verified separately.
    """
    token = re.compile(r"\^\(#(?P<size>0|5)~(?P<label>[^~\r\n]*?)\)"
                       r"(?P<meta>(?:[A-Za-z]+=[^;~]*;)+)~")
    cursor, parameters, view_name = 0, {}, None
    for match in token.finditer(text):
        if match.start() != cursor:
            return None
        cursor = match.end()
        fields = [item.split("=", 1) for item in match["meta"].split(";") if item]
        meta = dict(fields)
        if len(meta) != len(fields) or set(meta) != {"brackets", "param", "type", "viewName"}:
            return None
        param = meta["param"]
        if (meta["type"] != "view" or not re.fullmatch(r"[1-9][0-9]*", meta["viewName"])
                or param not in {"1", "2", "3", "5"} or param in parameters):
            return None
        if view_name is None:
            view_name = meta["viewName"]
        if meta["viewName"] != view_name:
            return None
        if param == "1":
            ratio = re.fullmatch(r"\(([0-9]+(?:[.,][0-9]+)?):([0-9]+(?:[.,][0-9]+)?)\)",
                                 match["label"])
            if ratio is None or match["size"] != "5" or meta["brackets"] != "1":
                return None
            numerator, denominator = (float(value.replace(",", ".")) for value in ratio.groups())
            if numerator <= 0 or denominator <= 0 or not _near(numerator/denominator, scale):
                return None
        elif match["label"] or match["size"] != "0" or meta["brackets"] != "0":
            return None
        parameters[param] = meta
    if cursor != len(text) or set(parameters) != {"1", "2", "3", "5"}:
        return None
    return {"native_view_name": view_name, "scale": scale, "parameter_kinds": sorted(parameters)}


def _remove_new_auto_captions(k, before, after, objects, numbers, result, report_path, root):
    """Delete only new scale captions whose native owning-view identity agrees."""
    baseline = {text["reference"] for row in before["views"] for text in row["texts"]}
    removed = []
    for row in after["views"]:
        number = row["Number"]
        if number not in numbers:
            continue
        candidates = [(text, _auto_scale_caption(text["text"], row["Scale"]))
                      for text in row["texts"] if text["reference"] not in baseline]
        candidates = [(text, parsed) for text, parsed in candidates if parsed is not None]
        if not candidates:
            continue
        view = objects[number]["view"]
        designation = _cast(k, view, "IViewDesignation")
        native_caption = designation.DrawingText
        if native_caption is None:
            continue
        owning_reference = native_caption.Reference
        collection = _cast(k, view, "IDrawingContainer").DrawingTexts
        for text, parsed in candidates:
            if text["reference"] != owning_reference:
                continue
            matches = [collection.Item(index) for index in range(collection.Count)
                       if collection.Item(index).Reference == owning_reference]
            if len(matches) != 1:
                raise RuntimeError("Native scale caption identity is missing/ambiguous")
            candidate = _cast(k, matches[0], "IDrawingText")
            if (not candidate.Valid or candidate.Reference in baseline
                    or _text_value(_cast(k, candidate, "IText")) != text["text"]):
                raise RuntimeError("Native scale caption changed before checked deletion")
            evidence = {"view_number": number, "view_reference": row["reference"],
                        "caption": text, "parsed_markup": parsed,
                        "native_designation_reference": owning_reference,
                        "new_reference_verified": True}
            result.setdefault("caption_cleanup_planned", []).append(evidence)
            _report(report_path, result, root)
            require(candidate.Delete(), f"delete new generated scale caption in view {number}")
            removed.append(evidence)
            result["removed_new_auto_captions"] = removed
            _report(report_path, result, root)
    return removed


@timed_phase("native.drawing.rebind")
def rebind_drawing_views(k, handle, copy_root, replacements, expected_fingerprint,
                         dimension_changes=None, view_changes=None, geometry_checks=None,
                         dry_run=True, report_path=None, remove_new_auto_captions=None):
    """Explicit checked source replacement; no save/reopen, model writes or rollback."""
    doc, root, path = _copy(k, handle, copy_root)
    result = {"drawing": str(path), "dry_run": dry_run, "saved": False,
              "persistence_verified": False, "phase": "preflight"}
    if report_path:
        _inside(report_path, root, {".json"}, exists=False)
        if Path(report_path).exists():
            raise FileExistsError("Use a new report path")
    before, objects = _inventory(k, doc, True, 200000)
    if before["fingerprint"] != expected_fingerprint:
        raise ValueError("Stale drawing fingerprint; inspect again before planning")
    selected, dims, shifts, checks = _plans(before, replacements, dimension_changes or [],
                                           view_changes or [], geometry_checks or [], root)
    captions = [] if remove_new_auto_captions is None else remove_new_auto_captions
    if (not isinstance(captions, list)
            or any(not isinstance(number, int) or isinstance(number, bool) or number not in selected
                   for number in captions) or len(captions) != len(set(captions))):
        raise ValueError("remove_new_auto_captions must explicitly select distinct rebound view numbers")
    sources = ({Path(value) for value in selected.values()}
               | {Path(item["expected_source"]).resolve() for item in replacements})
    hashes = _dependency_snapshot(k, doc, root, sources)
    result.update(before=before, replacements=replacements, dimension_changes=dimension_changes or [],
                  expected_native_view_shifts=view_changes or [], geometry_checks=geometry_checks or [],
                  source_hashes=hashes, remove_new_auto_captions=captions)
    _report(report_path, result, root)
    if dry_run:
        return result
    try:
        result["phase"] = "rebinding"
        result["completed_steps"] = []
        _report(report_path, result, root)
        for number, source in selected.items():
            assoc = objects[number]["association"]
            assoc.SourceFileName = source
            assoc.UseOcclusion = False
            with phase("native.view.update", counts={"native_calls": 1}):
                require(assoc.Update(), f"update associative view {number}")
            result["completed_steps"].append({"view_number": number, "operation": "source_update"})
            _report(report_path, result, root)
        for number in selected:
            with phase("native.view.rebuild", counts={"native_calls": 1}):
                require(objects[number]["association"].Rebuild(), f"rebuild associative view {number}")
            result["completed_steps"].append({"view_number": number, "operation": "view_rebuild"})
            _report(report_path, result, root)
        for (number, index), item in dims.items():
            dim = objects[number]["dimensions"][index]
            for key, value in item["endpoints"].items():
                setattr(dim, key, value)
            require(dim.Update(), f"update existing dimension {number}/{index}")
            result["completed_steps"].append({"view_number": number, "dimension_index": index,
                                              "operation": "dimension_update"})
            _report(report_path, result, root)
        extra = _cast(k, _cast(k, doc, "IKompasDocument2D"), "IKompasDocument2D1")
        require(extra.RebuildDocument(), "rebuild drawing document")
        after, _ = _inventory(k, doc, True, 200000)
        if captions:
            result["after_before_caption_cleanup"] = after
            _report(report_path, result, root)
            _remove_new_auto_captions(k, before, after, objects, captions, result, report_path, root)
            after, _ = _inventory(k, doc, True, 200000)
        result["after"] = after
        _preserve(before, after, selected, dims, shifts, checks)
        if hashes != {source: _file_hash(source) for source in hashes}:
            raise RuntimeError("A source/dependency file changed during drawing rebinding")
        result.update(phase="accepted_in_memory", native_content_preserved=True,
                      source_files_unchanged=True,
                      geometry_diff={str(number): {"before": next(v for v in before["views"]
                                      if v["Number"] == number)["geometry_digest"],
                                      "after": next(v for v in after["views"]
                                      if v["Number"] == number)["geometry_digest"]}
                                     for number in selected})
    except Exception as exc:
        result.update(phase="failed_partial_mutation", error=str(exc),
                      recovery="Inspect or discard this owned copy; do not retry blindly")
        _report(report_path, result, root)
        raise RuntimeError(f"Drawing rebind failed; partial changes remain inspectable: {exc}") from exc
    _report(report_path, result, root)
    return result


@contextmanager
def _messages_no(k):
    """Only conversion uses scoped No, never blanket Yes or persistent policy."""
    app = k.app.ksGetApplication7()
    previous = app.HideMessage
    try:
        app.HideMessage = k.constants["ksHideMessageNo"]
        yield app
    finally:
        app.HideMessage = previous


def _pdf_converter():
    root = os.getenv("KOMPAS_SDK_PATH")
    bins = ([Path(root).parent / "Bin"] if root else
            sorted(Path("C:/Program Files/ASCON").glob("KOMPAS*/Bin"), reverse=True))
    for folder in bins:
        manifest, library = folder / "Pdf2d.xml", folder / "Pdf2d.dll"
        if manifest.is_file() and library.is_file():
            commands = [item for item in ET.parse(manifest).getroot().findall("appCommand")
                        if "PDF" in item.get("title", "").upper()]
            if len(commands) == 1:
                return library.resolve(), int(commands[0].attrib["id"]), manifest.resolve()
    raise RuntimeError("Installed Pdf2d converter/unique manifest command unavailable")


def _dxf_dimensions(pairs):
    """Count ENTITIES dimensions and explicitly instantiated block dimensions.

    Unused definitions in BLOCKS do not constitute any drawing instances. INSERT
    is followed recursively, including bounded row/column arrays. Missing or cyclic
    blocks fail closed instead of inventing geometry or counting phantom symbols.
    """
    records = []
    for code, value in pairs:
        try:
            int(code)
        except ValueError as exc:
            raise RuntimeError("DXF contains a nonnumeric group code") from exc
        if code == "0":
            records.append({"type": value, "fields": []})
        elif records:
            records[-1]["fields"].append((code, value))
        else:
            raise RuntimeError("DXF does not begin with an entity/section group")
    section, block = None, None
    entities, definitions, seen_sections = [], {}, set()
    for record in records:
        kind = record["type"]
        if kind == "SECTION":
            fields = record["fields"]
            # HEADER can contain additional group-2 strings before the next
            # group-0 record. Only the first field is the section identifier.
            if section is not None or not fields or fields[0][0] != "2":
                raise RuntimeError("DXF has malformed/nested sections")
            section = fields[0][1]
            if section in seen_sections:
                raise RuntimeError("DXF has duplicate sections")
            seen_sections.add(section)
        elif kind == "ENDSEC":
            if section is None or block is not None:
                raise RuntimeError("DXF has an unmatched section/block boundary")
            section = None
        elif section == "BLOCKS":
            if kind == "BLOCK":
                names = [value.casefold() for code, value in record["fields"] if code == "2"]
                if block is not None or len(names) != 1 or names[0] in definitions:
                    raise RuntimeError("DXF has malformed/duplicate block definitions")
                block = names[0]
                definitions[block] = []
            elif kind == "ENDBLK":
                if block is None:
                    raise RuntimeError("DXF has an unmatched ENDBLK")
                block = None
            elif block is not None:
                definitions[block].append(record)
        elif section == "ENTITIES":
            entities.append(record)
    if section is not None or block is not None or "ENTITIES" not in seen_sections:
        raise RuntimeError("DXF is missing a complete ENTITIES section")
    visited = 0

    def count(items, stack=()):
        nonlocal visited
        dimensions = 0
        for item in items:
            visited += 1
            if visited > 1000000:
                raise RuntimeError("DXF instance traversal exceeds the validation limit")
            if item["type"] == "DIMENSION":
                dimensions += 1
            elif item["type"] == "INSERT":
                names = [value.casefold() for code, value in item["fields"] if code == "2"]
                if len(names) != 1 or names[0] not in definitions:
                    raise RuntimeError("DXF INSERT refers to an unresolved block")
                name = names[0]
                if name in stack or len(stack) >= 64:
                    raise RuntimeError("DXF INSERT has a cyclic or excessively deep block reference")
                counts = []
                for group in ("70", "71"):
                    values = [value for code, value in item["fields"] if code == group]
                    if len(values) > 1:
                        raise RuntimeError("DXF INSERT has duplicate array counts")
                    try:
                        value = int(values[0]) if values else 1
                    except ValueError as exc:
                        raise RuntimeError("DXF INSERT array counts are invalid") from exc
                    if not 1 <= value <= 1000000:
                        raise RuntimeError("DXF INSERT array counts exceed the validation limit")
                    counts.append(value)
                instances = counts[0]*counts[1]
                if instances > 1000000:
                    raise RuntimeError("DXF INSERT instance count exceeds the validation limit")
                dimensions += instances*count(definitions[name], (*stack, name))
        return dimensions

    direct = sum(item["type"] == "DIMENSION" for item in entities)
    total = count(entities)
    return {"dimensions": total, "direct_dimensions": direct,
            "dimensions_in_instantiated_blocks": total-direct,
            "block_definitions": len(definitions), "validated_entity_records": visited}


@timed_phase("export.validate")
def validate_export(path, minimum_dimensions=0):
    """Parse output, not just file length. Layout approval still requires rendering."""
    source = Path(path)
    if not source.is_file() or source.stat().st_size == 0:
        raise RuntimeError("Native converter did not produce a nonempty output")
    result = {"path": str(source), "bytes": source.stat().st_size, "sha256": _file_hash(source)}
    if source.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(source) as document:
            if not document.is_pdf or not document.page_count:
                raise RuntimeError("PDF cannot be parsed or has no pages")
            result["pages"] = []
            for page in document:
                drawing_count = len(page.get_drawings())
                text = page.get_text()
                if not drawing_count and not text.strip() and not page.get_images():
                    raise RuntimeError("PDF contains an empty page")
                result["pages"].append({"width_pt": page.rect.width, "height_pt": page.rect.height,
                                        "drawing_paths": drawing_count, "text": text})
    elif source.suffix.lower() == ".dxf":
        data = source.read_bytes()
        if data.startswith(b"AutoCAD Binary DXF"):
            raise RuntimeError("Binary DXF validation is unsupported; inspect the retained export")
        lines = data.decode("utf-8-sig", errors="replace").splitlines()
        if len(lines) % 2:
            raise RuntimeError("Malformed ASCII DXF group pairs")
        pairs = [(lines[i].strip(), lines[i+1].strip()) for i in range(0, len(lines), 2)]
        if not pairs or pairs[-1] != ("0", "EOF"):
            raise RuntimeError("DXF has no final EOF group")
        result.update(_dxf_dimensions(pairs))
        if result["dimensions"] < minimum_dimensions:
            raise RuntimeError("DXF lost native DIMENSION entities")
        result["group_pairs"] = len(pairs)
    else:
        raise ValueError("Expected PDF or DXF")
    result["structural_validation_passed"] = True
    result["visual_layout_verified"] = False
    return result


def _pump_messages():
    # Pdf2d can close its input through deferred messages. Reconcile while still
    # on this STA, before returning a document handle to the MCP caller.
    import pythoncom

    pythoncom.PumpWaitingMessages()


def _persistent_content(value):
    """Compare native saved contents across a genuine close/reopen boundary."""
    if isinstance(value, dict):
        return {key: _persistent_content(item) for key, item in value.items()
                if key not in {"reference", "fingerprint", "changed", "read_only"}}
    if isinstance(value, list):
        return [_persistent_content(item) for item in value]
    return value


def _export_identity(doc):
    return {"reference": doc.Reference, "path": doc.PathName, "read_only": bool(doc.ReadOnly),
            "visible": bool(doc.Visible), "active": bool(doc.Active)}


def _restore_export_source(k, path, before_identity, expected_content):
    """Explicit compatibility for a native converter closing/replacing its input.

    Only the already-authorized owned copy is reopened. Stale scopes are released
    by the normal document reconciliation, then flags, clean state and complete
    inventoried native contents are verified. Never infer a close from False.
    """
    path = Path(path).resolve()
    live = documents.list_documents(k, details=False)["documents"]
    matches = [item for item in live if item["path"] and Path(item["path"]).resolve() == path]
    if len(matches) > 1:
        raise RuntimeError("Multiple live documents use the exported copy path; lifecycle is ambiguous")
    receipt = {"before": before_identity, "input_absent_after_native_call": not matches,
               "reopened_by_server": False, "native_identity_changed": None}
    if not matches:
        with _messages_no(k):
            info = documents.open_document(k, str(path),
                                           read_only=before_identity["read_only"],
                                           visible=before_identity["visible"])
        if info["reused"]:
            raise RuntimeError("Unexpected concurrent reuse while restoring exported source")
        receipt["reopened_by_server"] = True
    else:
        info = matches[0]
    doc = _document(k, info["document"]["handle"])
    if (Path(doc.PathName).resolve() != path or doc.Changed
            or bool(doc.ReadOnly) != before_identity["read_only"]
            or bool(doc.Visible) != before_identity["visible"]):
        raise RuntimeError("Exported source lifecycle flags/path/clean state were not restored")
    if before_identity["active"]:
        doc.Active = True
    actual, _ = _inventory(k, doc, True, 200000)
    _same(_persistent_content(expected_content), _persistent_content(actual),
          "drawing contents after native converter lifecycle")
    receipt["after"] = _export_identity(doc)
    receipt["native_identity_changed"] = doc.Reference != before_identity["reference"]
    receipt["content_verified"] = True
    # A converter-created replacement at this unique owned-copy path is part of
    # the same authorized operation. Ownership never transfers to other paths.
    k.owned_documents.add(str(doc.Reference))
    info = documents.document_details(k, info["document"]["handle"])
    return doc, info, receipt


@timed_phase("native.drawing.export")
def export_drawing(k, handle, copy_root, paths, report_path=None):
    """Export a saved owned drawing copy via native converters, never auto-save it."""
    doc, root, drawing_path = _copy(k, handle, copy_root, writable=False)
    if doc.Changed:
        raise ValueError("Save and reopen the drawing copy before exporting; no implicit save")
    if not 1 <= len(paths) <= 2:
        raise ValueError("Supply one or two new PDF/DXF output paths")
    outputs = [_inside(path, root, {".pdf", ".dxf"}, exists=False) for path in paths]
    if len({p.suffix.lower() for p in outputs}) != len(outputs):
        raise ValueError("Supply at most one output per format")
    for path in outputs:
        if path.exists():
            raise FileExistsError(f"Export already exists: {path}")
    if report_path:
        _inside(report_path, root, {".json"}, exists=False)
        if Path(report_path).exists():
            raise FileExistsError("Use a new report path")
    inventory, _ = _inventory(k, doc, True, 200000)
    expected_dimensions = sum(len(view["dimensions"]) for view in inventory["views"])
    before_hash = _file_hash(drawing_path)
    dependency_hashes = _dependency_snapshot(k, doc, root)
    result = {"drawing": str(drawing_path), "drawing_sha256": before_hash,
              "phase": "preflight", "exports": [], "saved": False,
              "source_hashes": dependency_hashes, "visual_layout_verified": False,
              "requested_outputs": [str(path) for path in outputs], "native_lifecycle": []}
    _report(report_path, result, root)
    identity = _export_identity(doc)
    try:
        for path in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            result["phase"] = "exporting_"+path.suffix[1:]
            _report(report_path, result, root)
            identity = _export_identity(doc)
            if path.suffix.lower() == ".dxf":
                native = require(k.app.ksGetDocumentByReference(doc.Reference), "get drawing API5")
                native = k.api.ksDocument2D(native)
                converted = bool(native.ksSaveToDXF(str(path)))
            else:
                library, command, manifest = _pdf_converter()
                with _messages_no(k) as app:
                    converter = require(app.Converter(str(library)), "load native PDF converter")
                    converted = converter.Convert(str(drawing_path), str(path), command, False)
                result["pdf_converter"] = {"library": str(library), "command": command,
                                           "manifest": str(manifest)}
            _pump_messages()
            doc, fresh, receipt = _restore_export_source(k, drawing_path, identity, inventory)
            receipt["format"] = path.suffix[1:]
            result["native_lifecycle"].append(receipt)
            result["document_after_export"] = fresh
            _report(report_path, result, root)
            if converted != 1:
                raise RuntimeError(f"Native {path.suffix[1:].upper()} converter returned {converted!r}")
            result["exports"].append(validate_export(path, expected_dimensions))
            _report(report_path, result, root)
        if dependency_hashes != {source: _file_hash(source) for source in dependency_hashes}:
            raise RuntimeError("Source drawing/dependency file changed during export")
        result.update(phase="exported_structurally_valid", source_file_unchanged=True)
    except Exception as exc:
        result.update(phase="failed_partial_export", error=str(exc),
                      recovery="Inspect retained output files before using new paths to retry")
        try:
            _pump_messages()
            _, fresh, receipt = _restore_export_source(k, drawing_path, identity, inventory)
            result["document_after_export"] = fresh
            result["lifecycle_recovery"] = receipt
        except Exception as recovery_error:  # noqa: BLE001 - retain original conversion failure
            result["lifecycle_recovery_error"] = str(recovery_error)
        _report(report_path, result, root)
        raise RuntimeError(f"Drawing export failed; outputs retained: {exc}") from exc
    _report(report_path, result, root)
    return result
