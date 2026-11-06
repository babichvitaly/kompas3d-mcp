"""Pure planning/geometry contracts; actual solver cases need live CAD."""

import copy
from types import SimpleNamespace as NS

import pytest

from kompas_mcp import sketches
from kompas_mcp.sketches import assert_same_geometry, coordinate_plan


def rectangle():
    return {"LineSegments": [
        {"index": i, "reference": i + 10, "X1": a[0], "Y1": a[1],
         "X2": b[0], "Y2": b[1], "Style": 1, "constraints": []}
        for i, (a, b) in enumerate(zip(
            [(0., 0.), (100., 0.), (100., 50.), (0., 50.)],
            [(100., 0.), (100., 50.), (0., 50.), (0., 0.)], strict=True))],
        "Circles": [], "Arcs": []}


def test_rectangle_plan_has_shared_corners_one_datum_and_two_driving_offsets():
    groups = coordinate_plan(rectangle())
    assert len(groups) == 4
    assert all(len(group["members"]) == 2 for group in groups)
    assert groups[0]["axes"] == []
    offsets = [axis["offset"] for g in groups for axis in g["axes"]
               if axis["align"] is None]
    assert offsets == [100., 50.]


def test_hole_grid_retains_center_alignment_and_distinct_diameters():
    source = {"LineSegments": [], "Arcs": [], "Circles": [
        {"index": i, "Xc": x, "Yc": y, "Radius": radius, "constraints": []}
        for i, (x, y, radius) in enumerate([(5., -2., 3.2), (45., -2., 3.2),
                                           (5., 18., 4.), (45., 18., 4.)])]}
    groups = coordinate_plan(source)
    offsets = [(axis["axis"], axis["offset"]) for g in groups for axis in g["axes"]
               if axis["align"] is None]
    assert offsets == [("x", 40.), ("y", 20.)]
    assert len(groups) == 4


def test_existing_constraints_rejected_instead_of_overconstraining():
    source = rectangle()
    source["LineSegments"][0]["constraints"] = [{"type": 3, "valid": True}]
    with pytest.raises(ValueError, match="incremental"):
        coordinate_plan(source)


def test_geometry_comparison_ignores_native_reference_and_constraint_changes_only():
    before = rectangle()
    after = copy.deepcopy(before)
    after["LineSegments"][0]["reference"] = 999
    after["LineSegments"][0]["constraints"] = [{"type": 3, "valid": True}]
    assert_same_geometry(before, after)
    after["LineSegments"][2]["Y2"] += .001
    with pytest.raises(ValueError, match="Y2"):
        assert_same_geometry(before, after)


def test_arc_direction_and_radius_changes_detected_with_same_endpoints():
    before = {"LineSegments": [], "Circles": [], "Arcs": [
        {"index": 0, "Xc": 5., "Yc": 5., "Radius": 5., "Angle1": 270.,
         "Angle2": 180., "Direction": True, "X1": 5., "Y1": 0., "X2": 0.,
         "Y2": 5., "constraints": []}]}
    after = copy.deepcopy(before)
    after["Arcs"][0]["Angle1"] -= 360
    assert_same_geometry(before, after)
    after["Arcs"][0]["Direction"] = False
    with pytest.raises(ValueError, match="Direction"):
        assert_same_geometry(before, after)
    after["Arcs"][0]["Direction"] = True
    after["Arcs"][0]["Radius"] += .01
    with pytest.raises(ValueError, match="Radius"):
        assert_same_geometry(before, after)


@pytest.mark.parametrize("dirty", [False, True])
def test_fragment_inventory_never_enters_source_and_closes_owned_fragment(monkeypatch, tmp_path, dirty):
    closed = []
    root = NS(Parts=NS(Count=0))
    doc = NS(PathName=str(tmp_path / "copy.m3d"), Changed=False, TopPart=root)

    def write_fragment(path):
        from pathlib import Path
        Path(path).write_bytes(b"synthetic fragment")
        return True

    native = NS(ConstraintsState=1, WriteToFragment=write_fragment)
    fragment = NS(ViewsAndLayersManager=NS(Views=NS(ActiveView=object())),
                  Close=lambda flag: closed.append(flag) or True)
    app7 = NS(Documents=NS(Open=lambda path, visible, readonly: fragment))
    k = NS(app=NS(TransferInterface=lambda *args: native, ksGetApplication7=lambda: app7),
           constants={"ksAPI7Dual": 1, "kdDoNotSaveChanges": 2})
    monkeypatch.setattr(sketches, "_document", lambda *args: doc)
    monkeypatch.setattr(sketches, "_cast", lambda k, obj, interface: obj)
    monkeypatch.setattr(sketches, "_info", lambda *args: {"document_id": "doc"})
    monkeypatch.setattr(sketches, "verify_copy_tree", lambda *args: tmp_path)
    monkeypatch.setattr(sketches, "selected_sketches", lambda *args: [NS(name="profile")])

    def read_geometry(*args):
        doc.Changed = dirty
        return rectangle()

    monkeypatch.setattr(sketches, "geometry", read_geometry)
    if dirty:
        with pytest.raises(RuntimeError, match="dirty state"):
            sketches.inspect_sketches(k, "handle", str(tmp_path))
    else:
        result = sketches.inspect_sketches(k, "handle", str(tmp_path))
        assert result["sketches"][0]["constraints_state_before"] == 1
        assert result["sketches"][0]["constraints_state_after"] == 1
        assert result["sketches"][0]["reference_scope"] == "exported fragment"
    assert closed == [2]
