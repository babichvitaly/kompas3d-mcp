"""Bulk native sketch inspection on isolated copies, on the existing STA worker."""

import math
from contextlib import contextmanager
from uuid import uuid4

from .audit import array, write_json
from .backend import require
from .collisions import verify_copy_tree
from .documents import _cast, _document, _info


@contextmanager
def editing(k, entity):
    definition = entity.GetDefinition()
    drawing5 = require(definition.BeginEdit(), "begin sketch edit")
    try:
        drawing7 = _cast(k, k.app.TransferInterface(
            drawing5, k.constants["ksAPI7Dual"], 0
        ), "IKompasDocument2D")
        yield drawing7.ViewsAndLayersManager.Views.ActiveView
    finally:
        require(definition.EndEdit(), "end sketch edit")


def selected_sketches(k, doc_id, names):
    collection = k.document(doc_id).GetPart(-1).EntityCollection(k.constants["o3d_sketch"])
    entities = [collection.GetByIndex(i) for i in range(collection.GetCount())]
    if names is None:
        return entities
    if not names or len(names) != len(set(names)):
        raise ValueError("Supply distinct sketch names")
    result = []
    for name in names:
        matches = [e for e in entities if e.name == name]
        if len(matches) != 1:
            raise ValueError(f"Sketch name is missing or ambiguous: {name}")
        result.append(matches[0])
    return result


def geometry(k, view, max_primitives=5000):
    container = _cast(k, view, "IDrawingContainer")
    result = {}
    total = 0
    for family, interface, fields in (
        ("LineSegments", "ILineSegment", ("X1", "Y1", "X2", "Y2", "Length", "Style")),
        ("Circles", "ICircle", ("Xc", "Yc", "Radius", "Style")),
        ("Arcs", "IArc", ("Xc", "Yc", "Radius", "Angle1", "Angle2", "Direction",
                           "X1", "Y1", "X2", "Y2", "Style")),
    ):
        collection = getattr(container, family)
        total += collection.Count
        if total > max_primitives:
            raise ValueError("Sketch primitive limit exceeded; no mutation performed")
        rows = []
        for i in range(collection.Count):
            obj = _cast(k, collection.Item(i), interface)
            extra = _cast(k, obj, "IDrawingObject1")
            rows.append({
                "index": i, "reference": obj.Reference,
                **{name: getattr(obj, name) for name in fields},
                "constraints": [{"type": c.ConstraintType, "valid": bool(c.Valid)}
                                for c in array(extra.Constraints)],
            })
        result[family] = rows
    return result


def inspect_sketches(k, handle, copy_root, names=None, report_path=None):
    from pathlib import Path

    doc = _document(k, handle)
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    verify_copy_tree(k, doc, root, copy_root)
    if root.Parts.Count:
        raise ValueError("Inspect a part's own sketches, not an assembly")
    target = None
    if report_path:
        target = Path(report_path)
        if not target.is_absolute() or target.exists() or not target.parent.is_dir():
            raise ValueError("Use a new absolute report path in an existing directory")
    info = _info(k, doc)
    changed = bool(doc.Changed)
    rows = []
    snapshot_dir = Path(copy_root).resolve() / "sketch-inventory" / uuid4().hex
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    for entity in selected_sketches(k, info["document_id"], names):
        native = _cast(k, k.app.TransferInterface(entity, k.constants["ksAPI7Dual"], 0),
                       "ISketch")
        state_before = int(native.ConstraintsState)
        # Even BeginEditEx(True)/EndEdit changes 1 -> 2 in this SDK's cached
        # sketch state. Inspect an exported fragment without entering the source.
        fragment_path = snapshot_dir / f"sketch-{len(rows) + 1}.frw"
        require(native.WriteToFragment(str(fragment_path)), "export sketch inventory fragment")
        fragment = require(k.app.ksGetApplication7().Documents.Open(
            str(fragment_path), False, True), "open sketch inventory fragment")
        try:
            drawing = _cast(k, fragment, "IKompasDocument2D")
            view = drawing.ViewsAndLayersManager.Views.ActiveView
            rows.append({"name": entity.name, "geometry": geometry(k, view),
                         "constraints_state_before": state_before,
                         "reference_scope": "exported fragment", "snapshot": str(fragment_path)})
        finally:
            require(fragment.Close(k.constants["kdDoNotSaveChanges"]),
                    "close sketch inventory fragment")
        rows[-1]["constraints_state_after"] = int(native.ConstraintsState)
        if rows[-1]["constraints_state_after"] != state_before:
            raise RuntimeError("Sketch inspection changed source constraint state; do not save")
    result = {"document": doc.PathName, "sketches": rows,
              "changed_before": changed, "changed_after": bool(doc.Changed)}
    if result["changed_after"] != changed:
        raise RuntimeError("Sketch inspection changed source dirty state; do not save")
    if target:
        write_json(target, result)
    return result


def assert_same_geometry(before, after, tolerance=1e-6):
    """Compare every primitive, not just a mass or bounding box."""
    for family in ("LineSegments", "Circles", "Arcs"):
        if len(before[family]) != len(after[family]):
            raise ValueError(f"Geometry changed: {family} count")
        for a, b in zip(before[family], after[family], strict=True):
            for key, value in a.items():
                if key in {"reference", "constraints", "index"}:
                    continue
                actual = b[key]
                if isinstance(value, bool):
                    equal = value == actual
                elif isinstance(value, (int, float)):
                    delta = abs(value - actual)
                    if key in {"Angle1", "Angle2"}:
                        delta = abs((value - actual + 180) % 360 - 180)
                    equal = math.isfinite(actual) and delta <= tolerance
                else:
                    equal = value == actual
                if not equal:
                    raise ValueError(f"Geometry changed: {family}[{a['index']}].{key}: "
                                     f"{value} -> {actual}")


def coordinate_plan(source, tolerance=1e-7):
    """Coordinate-driven layout: one datum, shared points/axes, editable dimensions.

    No primitive is frozen. Arc end points and diameters retain the original
    profile; inferred tangency/design equations are deliberately not invented.
    """
    groups = []
    for family in ("LineSegments", "Circles", "Arcs"):
        for row in source[family]:
            if row["constraints"]:
                raise ValueError("Existing constraints need an explicit incremental plan")
            points = ([(0, row["X1"], row["Y1"]), (1, row["X2"], row["Y2"])]
                      if family == "LineSegments" else
                      [(0, row["Xc"], row["Yc"])] if family == "Circles" else
                      [(1, row["X1"], row["Y1"]), (2, row["X2"], row["Y2"])])
            for index, x, y in points:
                if not all(math.isfinite(v) for v in (x, y)):
                    raise ValueError("Non-finite sketch coordinate")
                point = {"family": family, "index": row["index"], "point": index}
                match = next((g for g in groups if abs(g["x"] - x) <= tolerance
                              and abs(g["y"] - y) <= tolerance), None)
                if match is None:
                    groups.append({"x": x, "y": y, "members": [point]})
                else:
                    match["members"].append(point)
    if not groups:
        raise ValueError("No supported primitives")
    for i, group in enumerate(groups):
        group["axes"] = []
        if i == 0:
            continue
        for axis in ("x", "y"):
            shared = next((j for j, prior in enumerate(groups[:i])
                           if abs(prior[axis] - group[axis]) <= tolerance), None)
            group["axes"].append({"axis": axis, "align": shared,
                                  "offset": group[axis] - groups[0][axis]})
    return groups


def new_constraint(k, obj, kind, **properties):
    extra = _cast(k, obj, "IDrawingObject1")
    c = extra.NewConstraint()
    c.ConstraintType = k.constants[kind]
    for name, value in properties.items():
        setattr(c, name, value)
    require(c.Create(), f"create {kind}")
    valid = bool(c.Valid)
    if not valid and kind == "ksCAssociation":
        replacements = array(extra.Constraints)
        valid = len(replacements) >= 2 and all(item.Valid for item in replacements)
    require(valid, f"validate {kind}")


def constrain_sketch(k, handle, copy_root, name, expected_geometry, prefix="Layout",
                     dry_run=True):
    """One explicit, unconstrained, line/circle/arc sketch on a saved copy.

    Does not save. On failure the caller must close its owned copy with discard,
    rather than continuing with the partially constrained in-memory document.
    """
    import re

    import pythoncom
    from win32com.client import VARIANT

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", prefix):
        raise ValueError("Use a short ASCII variable prefix")
    doc = _document(k, handle)
    if doc.ReadOnly:
        raise ValueError("A writable part copy is required")
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    verify_copy_tree(k, doc, root, copy_root)
    if root.Parts.Count:
        raise ValueError("Only standalone part sketches are supported")
    info = _info(k, doc)
    entity = selected_sketches(k, info["document_id"], [name])[0]
    result = {"document": doc.PathName, "name": name, "dry_run": dry_run}
    with editing(k, entity) as view:
        container = _cast(k, view, "IDrawingContainer")
        unsupported = {family: getattr(container, family).Count for family in (
            "ArcSlots", "Beziers", "ConicCurves", "DrawingContours", "EllipseArcs",
            "Ellipses", "Equidistants", "InsertionObjects", "Lines", "MacroObjects",
            "Multilines", "Nurbses", "NurbsesByPoints", "PolyLines2D", "Rectangles",
            "RegularPolygons", "StraightSlots",
        ) if getattr(container, family).Count}
        if unsupported:
            raise ValueError(f"Unsupported sketch curves; no constraints added: {unsupported}")
        before = geometry(k, view)
        assert_same_geometry(expected_geometry, before)
        groups = coordinate_plan(before)
        result["plan"] = groups
        if dry_run:
            return result
        container = _cast(k, view, "IDrawingContainer")
        objects = {family: [_cast(k, getattr(container, family).Item(i), interface)
                            for i in range(len(before[family]))]
                   for family, interface in (("LineSegments", "ILineSegment"),
                                             ("Circles", "ICircle"), ("Arcs", "IArc"))}

        def obj(point):
            return objects[point["family"]][point["index"]]

        def pair_constraint(a, b, kind):
            new_constraint(k, obj(a), kind, Index=a["point"], Partner=obj(b),
                           PartnerIndex=b["point"])

        for group in groups:
            for point in group["members"][1:]:
                pair_constraint(point, group["members"][0], "ksCMergePoints")
        anchor = groups[0]["members"][0]
        new_constraint(k, obj(anchor), "ksCFixedPoint", Index=anchor["point"])
        symbols = _cast(k, view, "ISymbols2DContainer")
        variables = []

        def driving(dim, variable, value):
            try:
                new_constraint(k, dim, "ksCFixedDim")
            except Exception as exc:
                raise ValueError(f"Driving dimension {variable}={value}: {exc}") from exc
            new_constraint(k, dim, "ksCDimWithVariable", Variable=variable,
                           Expression=format(value, ".15g"), Value=value)
            variables.append({"name": variable, "value": value})

        for i, group in enumerate(groups[1:], 1):
            point = group["members"][0]
            for axis in group["axes"]:
                if axis["align"] is not None:
                    other = groups[axis["align"]]["members"][0]
                    same_line = (point["family"] == other["family"] == "LineSegments"
                                 and point["index"] == other["index"])
                    kind = ("ksCVertical" if axis["axis"] == "x" else "ksCHorizontal")
                    if same_line:
                        new_constraint(k, obj(point), kind)
                    else:
                        pair_constraint(point, other, "ksCVAlignPoints" if axis["axis"] == "x"
                                        else "ksCHAlignPoints")
                    continue
                dim = symbols.LineDimensions.Add()
                dim.X1, dim.Y1 = groups[0]["x"], groups[0]["y"]
                dim.X2, dim.Y2 = group["x"], group["y"]
                dim.X3, dim.Y3 = group["x"] + 10, group["y"] + 10
                dim.Orientation = k.constants["ksLinDHorizontal" if axis["axis"] == "x"
                                              else "ksLinDVertical"]
                _cast(k, dim, "IDimensionText").AutoNominalValue = True
                require(dim.Update(), "create coordinate dimension")
                if anchor["family"] == point["family"] and anchor["index"] == point["index"]:
                    partner = obj(point)
                else:
                    partner = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                                      [obj(anchor), obj(point)])
                try:
                    new_constraint(k, dim, "ksCAssociation", Partner=partner)
                except Exception as exc:
                    raise ValueError(f"Coordinate dimension {i}/{axis['axis']}: {exc}") from exc
                driving(dim, f"{prefix}_{axis['axis'].upper()}{i}", abs(axis["offset"]))
        for family in ("Circles", "Arcs"):
            for row, curve in zip(before[family], objects[family], strict=True):
                if family == "Arcs" and abs((row["Angle2"]-row["Angle1"]) % 360-180) < 1e-7:
                    if abs(row["X1"]-row["X2"]) < 1e-7:
                        kind = "ksCVAlignPoints"
                    elif abs(row["Y1"]-row["Y2"]) < 1e-7:
                        kind = "ksCHAlignPoints"
                    else:
                        raise ValueError("An oblique semicircle needs an explicit center/chord plan")
                    # Its center lies on the diameter chord; the driven endpoint
                    # separation determines radius. Avoid a singular minimum-radius
                    # dimension on a fully positioned semicircular cap.
                    endpoint = next(g for g in groups if abs(g["x"]-row["X1"]) < 1e-7
                                    and abs(g["y"]-row["Y1"]) < 1e-7)
                    partner_point = next((p for p in endpoint["members"]
                                          if p["family"] != "Arcs" or p["index"] != row["index"]), None)
                    if partner_point is None:
                        raise ValueError("A semicircle needs a distinct incident primitive for its chord relation")
                    new_constraint(k, curve, kind, Index=0, Partner=obj(partner_point),
                                   PartnerIndex=partner_point["point"])
                    continue
                dim = symbols.DiametralDimensions.Add()
                dim.BaseObject = curve
                dim.Angle = 30
                _cast(k, dim, "IDimensionText").AutoNominalValue = True
                require(dim.Update(), "create diameter dimension")
                try:
                    linked = array(_cast(k, dim, "IDrawingObject1").Constraints)
                    if not any(c.ConstraintType == k.constants["ksCAssociation"]
                               and c.Valid for c in linked):
                        new_constraint(k, dim, "ksCAssociation", Partner=curve)
                except Exception as exc:
                    raise ValueError(f"Diameter {family}[{row['index']}]: {exc}") from exc
                driving(dim, f"{prefix}_{'D' if family == 'Circles' else 'ArcD'}{row['index']}",
                        row["Radius"] * 2)
        after = geometry(k, view)
        assert_same_geometry(before, after)
        if any(not c["valid"] for rows in after.values() for row in rows
               for c in row["constraints"]):
            raise ValueError("Invalid native constraint after parameterization")
        result.update(variables=variables, geometry_before=before, geometry_after=after)
    require(k.document(info["document_id"]).RebuildDocument(), "rebuild constrained part")
    result["saved"] = False
    return result
