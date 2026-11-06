"""Explicit source replacement in one isolated assembly, on the COM STA."""

import math
from pathlib import Path

from .backend import require
from .collisions import verify_copy_tree
from .documents import _cast, _document, _info


def rows(root):
    return [{"index": i, "source": root.Parts.Part(i).FileName,
             "matrix": list(root.Parts.Part(i).Placement.GetMatrix3D())}
            for i in range(root.Parts.Count)]


def same_placements(before, after):
    if len(before) != len(after):
        raise ValueError("Component count changed")
    for a, b in zip(before, after, strict=True):
        if a["index"] != b["index"] or len(a["matrix"]) != len(b["matrix"]):
            raise ValueError("Component identity changed")
        if any(not math.isfinite(y) or abs(x - y) > 1e-10
               for x, y in zip(a["matrix"], b["matrix"], strict=True)):
            raise ValueError(f"Component placement changed: {a['index']}")


def rebind_sources(k, handle, copy_root, replacements, dry_run=True):
    """No recursive writes, no save. Caller discards its owned copy on failure."""
    doc = _document(k, handle)
    if doc.ReadOnly:
        raise ValueError("A writable assembly copy is required")
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    folder = verify_copy_tree(k, doc, root, copy_root)
    if not root.Parts.Count:
        raise ValueError("An assembly with external components is required")
    if not replacements or len(replacements) > 1000:
        raise ValueError("Supply 1..1000 explicit source replacements")
    mapping = {}
    for source, target in replacements.items():
        a, b = Path(source), Path(target)
        for path in (a, b):
            if not path.is_absolute() or not path.is_file() or not path.resolve().is_relative_to(folder):
                raise ValueError("Every source and target must exist inside copy_root")
        a, b = a.resolve(), b.resolve()
        if a == b or a.suffix.lower() != b.suffix.lower() or a.suffix.lower() not in {".m3d", ".a3d"}:
            raise ValueError("Use distinct native sources of the same kind")
        if a in mapping:
            raise ValueError("Duplicate canonical source")
        mapping[a] = b
    before = rows(root)
    changes = [{"index": row["index"], "from": row["source"],
                "to": str(mapping[Path(row["source"]).resolve()])}
               for row in before if row["source"] and Path(row["source"]).resolve() in mapping]
    used = {Path(change["from"]).resolve() for change in changes}
    if used != set(mapping):
        raise ValueError("A requested source is absent from the immediate assembly; stale plan")
    result = {"document": doc.PathName, "dry_run": dry_run, "changes": changes,
              "before": before, "saved": False}
    if dry_run:
        return result
    for change in changes:
        part = root.Parts.Part(change["index"])
        part.FileName = change["to"]
        part.Update()
    require(k.document(_info(k, doc)["document_id"]).RebuildDocument(), "rebuild rebound assembly")
    after = rows(root)
    same_placements(before, after)
    expected = {c["index"]: c["to"] for c in changes}
    for a, b in zip(before, after, strict=True):
        if Path(b["source"]).resolve() != Path(expected.get(a["index"], a["source"])).resolve():
            raise ValueError(f"Unexpected source after rebuild: {a['index']}")
    verify_copy_tree(k, doc, root, copy_root)
    result.update(after=after, placements_unchanged=True)
    return result


def rigid_matrix(value):
    if len(value) != 16 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in value):
        raise ValueError("A finite 16-element matrix is required")
    if any(abs(value[i]) > 1e-9 for i in (3, 7, 11)) or abs(value[15] - 1) > 1e-9:
        raise ValueError("Expected an affine row-vector matrix")
    axes = [value[i:i+3] for i in (0, 4, 8)]
    for i, a in enumerate(axes):
        for j, b in enumerate(axes):
            if abs(sum(x*y for x, y in zip(a, b, strict=True)) - (1 if i == j else 0)) > 1e-8:
                raise ValueError("Only rigid placements, without scale or shear, are supported")
    a, b, c = axes
    determinant = a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if abs(determinant-1) > 1e-8:
        raise ValueError("Mirroring is not a rigid rotation")
    return list(value)


def place_components(k, handle, copy_root, placements, dry_run=True):
    """Explicit immediate occurrences; preserve fixed flags and all other poses."""
    import pythoncom
    from win32com.client import VARIANT

    doc = _document(k, handle)
    if doc.ReadOnly:
        raise ValueError("A writable assembly copy is required")
    root = _cast(k, doc, "IKompasDocument3D").TopPart
    verify_copy_tree(k, doc, root, copy_root)
    if not 1 <= len(placements) <= 1000:
        raise ValueError("Supply 1..1000 explicit placement changes")
    before = rows(root)
    selected = {}
    fixed_before = [bool(root.Parts.Part(i).Fixed) for i in range(root.Parts.Count)]
    for item in placements:
        if set(item) != {"index", "expected", "matrix"}:
            raise ValueError("Each placement needs index, expected and matrix")
        index = item["index"]
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(before) or index in selected:
            raise ValueError("Select distinct existing immediate component indices")
        expected = rigid_matrix(item["expected"])
        target = rigid_matrix(item["matrix"])
        if any(abs(a-b)>1e-8 for a, b in zip(expected, before[index]["matrix"], strict=True)):
            raise ValueError(f"Stale placement plan at component {index}")
        selected[index] = target
    result = {"document": doc.PathName, "dry_run": dry_run, "changes": placements,
              "before": before, "saved": False}
    if dry_run:
        return result
    doc.Active = True
    update_returns = []
    for index, target in selected.items():
        part = root.Parts.Part(index)
        fixed = bool(part.Fixed)
        try:
            if fixed:
                part.Fixed = False
                part.Update()
            native = k.api.ksPart(k.app.TransferInterface(part, k.constants["ksAPI5Auto"], 0))
            placement = native.GetPlacement()
            require(placement.InitByMatrix3D(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, target)),
                    f"initialize component placement {index}")
            # InitByMatrix3D already changes the owned placement. Passing that same
            # object back to SetPlacement is a self-assignment rejected by v25.
            # Preserve the update return: false is not represented as native success;
            # exact readback and independent save/reopen acceptance remain required.
            update_returns.append({"index": index, "native_update_return": bool(native.UpdatePlacement())})
        finally:
            if fixed:
                part.Fixed = True
                part.Update()
    require(k.document(_info(k, doc)["document_id"]).RebuildDocument(), "rebuild placed assembly")
    after = rows(root)
    expected_rows = [{**row, "matrix": selected.get(row["index"], row["matrix"])} for row in before]
    same_placements(expected_rows, after)
    if [r["source"] for r in before] != [r["source"] for r in after]:
        raise ValueError("Component source changed during placement")
    if fixed_before != [bool(root.Parts.Part(i).Fixed) for i in range(root.Parts.Count)]:
        raise ValueError("Component fixed state changed during placement")
    result.update(after=after, unselected_placements_unchanged=True,
                  native_updates=update_returns, persistence_verified=False)
    return result
