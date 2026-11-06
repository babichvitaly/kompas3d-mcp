"""Safety/planning tests. Native acceptance is scripts/validate_geometry13.py."""

import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from kompas_mcp import body_diagnostics as bodies
from kompas_mcp import collision_fixture as fixture
from kompas_mcp import project_copy as copy
from kompas_mcp import sketch_frame as frame
from kompas_mcp.audit import IDENTITY


def translation(x=0, y=0, z=0):
    value = list(IDENTITY)
    value[12:15] = [x, y, z]
    return value


def occurrence(path, source, position=None):
    return {"path": path, "source": str(source), "local_to_parent": position or list(IDENTITY),
            "local_to_root": position or list(IDENTITY), "fixed": True, "hidden": False}


@pytest.mark.parametrize("paths", [[], [[]], [[True]], [[-1]], [[0], [0]], [[1], [1, 0]],
                                  [[1, 0], [1]], [[0.5]]])
def test_fixture_refuses_ambiguous_or_overlapping_scopes(paths):
    with pytest.raises(ValueError):
        fixture.validate_paths(paths)


def test_fixture_accepts_different_instances_of_same_source():
    assert fixture.validate_paths([[0, 1], [1, 1]]) == [(0, 1), (1, 1)]


def test_native_noop_update_false_requires_readback_not_invented_success(monkeypatch):
    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(VT_ARRAY=8192, VT_R8=5))
    monkeypatch.setitem(sys.modules, "win32com.client", SimpleNamespace(VARIANT=lambda kind, value: value))
    current = list(IDENTITY)
    part = SimpleNamespace(Fixed=False, Placement=SimpleNamespace(GetMatrix3D=lambda: current),
                           Update=lambda: False)

    def initialize(value):
        current[:] = value
        return True

    native = SimpleNamespace(GetPlacement=lambda: SimpleNamespace(InitByMatrix3D=initialize),
                             UpdatePlacement=lambda: False)
    k = SimpleNamespace(api=SimpleNamespace(ksPart=lambda obj: native),
                        app=SimpleNamespace(TransferInterface=lambda *args: object()),
                        constants={"ksAPI5Auto": 5})
    result = fixture.set_native_matrix(k, part, translation(3, 4, 5))
    assert current[12:15] == [3, 4, 5] and part.Fixed
    assert result["unfix_update_return"] is None  # no redundant Fixed=False update
    assert result["fix_update_return"] is False
    assert result["native_update_return"] is False
    assert result["matrix_readback_verified"] and result["fixed_readback_verified"]


def test_world_matrix_composition_is_child_then_parent(monkeypatch):
    parent = [0., 1., 0., 0., -1., 0., 0., 0., 0., 0., 1., 0., 100., 200., 0., 1.]
    nodes = {(0,): SimpleNamespace(Placement=SimpleNamespace(GetMatrix3D=lambda: parent)),
             (0, 1): SimpleNamespace(Placement=SimpleNamespace(GetMatrix3D=lambda: translation(20)))}
    monkeypatch.setattr(fixture, "resolve_occurrence", lambda k, root, path: nodes[tuple(path)])
    monkeypatch.setattr(fixture, "_cast", lambda *args: SimpleNamespace(Excluded=False, IsRollBacked=False))
    _, result = fixture.occurrence_world(None, None, [0, 1])
    assert result[12:15] == pytest.approx([100, 220, 0])
    assert result[:12] == parent[:12]


def test_copy_graph_shared_source_once_and_bottom_up():
    assert copy.bottom_up({"root": ["a", "b"], "a": ["shared"], "b": ["shared"], "shared": []}) == [
        "shared", "a", "b", "root"]
    with pytest.raises(ValueError, match="Cyclic"):
        copy.bottom_up({"a": ["b"], "b": ["a"]})


def test_occurrence_verification_detects_same_bounds_different_pose(tmp_path):
    a, b = tmp_path / "source.m3d", tmp_path / "copy.m3d"
    expected = [occurrence([0], a)]
    actual = [occurrence([0], b)]
    copy.assert_occurrences(expected, actual, {copy.path_key(a): str(b)})
    actual[0]["local_to_root"][12] = .001
    with pytest.raises(RuntimeError, match="Placement"):
        copy.assert_occurrences(expected, actual, {copy.path_key(a): str(b)})


def test_relative_dependency_resolved_by_owner_not_working_directory(tmp_path):
    assert copy.canonical("child.m3d", tmp_path / "project" / "root.a3d") == (
        tmp_path / "project" / "child.m3d").resolve()
    with pytest.raises(ValueError, match="pseudo"):
        copy.canonical("library.l3d|part")


def test_nested_relative_occurrence_uses_subassembly_owner(tmp_path, monkeypatch):
    def part(source, children=()):
        return SimpleNamespace(FileName=str(source), Fixed=False, Hidden=False,
                               Placement=SimpleNamespace(GetMatrix3D=lambda: list(IDENTITY)),
                               Parts=SimpleNamespace(Count=len(children), Part=lambda i: children[i]))

    root_path = tmp_path / "root.a3d"
    root = part(root_path, [part("sub/inner.a3d", [part("leaf.m3d")])])
    monkeypatch.setattr(copy, "_cast", lambda *args: SimpleNamespace(TopPart=root))
    k = SimpleNamespace(constants={"ksDocumentPart": 1, "ksDocumentAssembly": 2})
    rows = copy.occurrence_snapshot(k, SimpleNamespace(PathName=str(root_path), DocumentType=2))
    assert rows[2]["source"] == str((tmp_path / "sub" / "leaf.m3d").resolve())


def model_file(path, children=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"children": [str(p) for p in children]}), encoding="utf-8")
    return path


@pytest.fixture
def fake_native(monkeypatch):
    class Document:
        def __init__(self, path):
            self.PathName = str(path)
            self.data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.Changed = False
            self.DocumentType = 0  # non-3D native type; links still must rebind

        def ReplaceExternalFilesNames(self, recursive, old, new):
            assert recursive is False
            self.data["children"] = [new if p == old else p for p in self.data["children"]]
            self.Changed = True
            return True

        def SaveAs(self, path):
            Path(path).write_text(json.dumps(self.data), encoding="utf-8")
            self.Changed = False

    @contextmanager
    def opening(k, path, read_only=True):
        yield Document(path)

    monkeypatch.setattr(copy, "native_document", opening)
    monkeypatch.setattr(copy, "_cast", lambda k, doc, interface: doc)
    get_links = lambda k, d: [{"path": str(copy.canonical(p, d.PathName)), "native_path": p, "type": 11}
                            for p in d.data["children"]]
    monkeypatch.setattr(copy, "dependencies", get_links)
    monkeypatch.setattr(copy, "external_links", get_links)
    monkeypatch.setattr(copy, "occurrence_snapshot", lambda k, d: [])
    monkeypatch.setattr(copy, "_document", lambda k, handle: handle)
    return Document, SimpleNamespace(constants={"ksDocumentPart": 1, "ksDocumentAssembly": 2})


def test_complete_copy_dry_run_then_rebind_and_preserve_originals(tmp_path, fake_native):
    document, k = fake_native
    leaf = model_file(tmp_path / "source" / "part.m3d")
    child = model_file(tmp_path / "source" / "child.a3d", [leaf, leaf])
    root = model_file(tmp_path / "source" / "root.a3d", [child, leaf])
    hashes = {p: copy.digest(p) for p in (leaf, child, root)}
    destination = tmp_path / "isolated"
    plan = copy.create_isolated_copy(k, document(root), str(destination))
    assert plan["source_count"] == 3 and not destination.exists()
    result = copy.create_isolated_copy(k, document(root), str(destination), dry_run=False)
    assert result["status"] == "passed" and result["originals_unchanged"]
    assert result["persistence_verified"] and result["outside_links"] == []
    assert all(copy.digest(p) == hashes[p] for p in hashes)
    for row in result["files"]:
        children = json.loads(Path(row["copy"]).read_text(encoding="utf-8"))["children"]
        assert all(Path(p).is_relative_to(destination) for p in children)


def test_relative_link_rebind_uses_original_owner_not_new_folder(tmp_path, fake_native):
    document, k = fake_native
    model_file(tmp_path / "original" / "leaf.m3d")
    root = model_file(tmp_path / "original" / "root.a3d", ["leaf.m3d"])
    result = copy.create_isolated_copy(k, document(root), str(tmp_path / "copy"), dry_run=False)
    assert result["status"] == "passed", result
    assert result["originals_unchanged"] and result["source_count"] == 2
    target = Path(result["root"])
    links = json.loads(target.read_text("utf-8"))["children"]
    assert all(Path(p).is_file() and Path(p).is_relative_to(tmp_path / "copy") for p in links)


def test_inside_but_missing_link_never_skipped(tmp_path):
    target = tmp_path / "copy"
    target.mkdir()
    original = tmp_path / "original.m3d"
    missing = target / "missing.m3d"
    key = copy.path_key(original)
    plan = [{"path": str(original), "native_path": str(original), "type": 11}]
    current = [{"path": str(missing), "native_path": str(missing), "type": 11}]
    with pytest.raises(RuntimeError, match="absent"):
        copy.replacement_plan(plan, current, target / "root.a3d", {key: str(missing)}, target)


def test_missing_dependency_and_cycle_never_create_output(tmp_path, fake_native):
    document, k = fake_native
    root = model_file(tmp_path / "root.a3d", [tmp_path / "absent.m3d"])
    with pytest.raises(ValueError, match="Missing dependency"):
        copy.create_isolated_copy(k, document(root), str(tmp_path / "missing"), dry_run=False)
    a = model_file(tmp_path / "a.a3d", [tmp_path / "b.a3d"])
    model_file(tmp_path / "b.a3d", [a])
    with pytest.raises(ValueError, match="Cyclic"):
        copy.create_isolated_copy(k, document(a), str(tmp_path / "cyclic"), dry_run=False)
    assert not (tmp_path / "missing").exists() and not (tmp_path / "cyclic").exists()


def test_partial_copy_failure_is_manifested_not_accepted(tmp_path, fake_native, monkeypatch):
    document, k = fake_native
    leaf = model_file(tmp_path / "leaf.m3d")
    root = model_file(tmp_path / "root.a3d", [leaf])
    monkeypatch.setattr(document, "ReplaceExternalFilesNames", lambda *args: False)
    result = copy.create_isolated_copy(k, document(root), str(tmp_path / "failed"), dry_run=False)
    saved = json.loads((tmp_path / "failed" / "isolated-copy-manifest.json").read_text("utf-8"))
    assert result["status"] == saved["status"] == "failed"
    assert result["partial_output"] and not result["persistence_verified"]
    assert result["originals_unchanged"]


def test_transitive_occurrence_link_is_not_replaced_in_parent(tmp_path, fake_native, monkeypatch):
    document, k = fake_native
    leaf = model_file(tmp_path / "source" / "part.m3d")
    child = model_file(tmp_path / "source" / "child.a3d", [leaf])
    root = model_file(tmp_path / "source" / "root.a3d", [child])
    immediate = copy.external_links

    def with_nested(k, doc):
        rows = immediate(k, doc)
        for path in doc.data["children"]:
            nested = json.loads(Path(path).read_text("utf-8"))["children"]
            rows.extend({"path": p, "native_path": p, "type": None,
                         "discovered_by": "occurrence_tree"} for p in nested)
        return rows

    monkeypatch.setattr(copy, "dependencies", with_nested)
    original_replace = document.ReplaceExternalFilesNames

    def checked_replace(self, recursive, old, new):
        if Path(self.PathName).name == "root.a3d":
            assert Path(old).name == "child.a3d", "Transitive plate belongs to child, not root"
        return original_replace(self, recursive, old, new)

    monkeypatch.setattr(document, "ReplaceExternalFilesNames", checked_replace)
    result = copy.create_isolated_copy(k, document(root), str(tmp_path / "copy"), dry_run=False)
    assert result["status"] == "passed" and result["source_count"] == 3


def test_dirty_original_refused_before_any_copy(tmp_path, fake_native):
    document, k = fake_native
    root = model_file(tmp_path / "root.a3d")
    doc = document(root)
    doc.Changed = True
    with pytest.raises(ValueError, match="Save source"):
        copy.create_isolated_copy(k, doc, str(tmp_path / "copy"), dry_run=False)
    assert not (tmp_path / "copy").exists()


def native_frame(tx, ty, angle, origin=(0, 0, 0), u=(1, 0, 0), v=(0, 1, 0)):
    a = math.radians(angle)
    p = [q + tx*x + ty*y for q, x, y in zip(origin, u, v, strict=True)]
    pu = [q + math.cos(a)*x + math.sin(a)*y for q, x, y in zip(p, u, v, strict=True)]
    pv = [q - math.sin(a)*x + math.cos(a)*y for q, x, y in zip(p, u, v, strict=True)]
    return {"translation": [tx, ty], "angle": angle, "points": [p, pu, pv]}


@pytest.mark.parametrize("u,v", [((1, 0, 0), (0, 1, 0)), ((0, 1, 0), (0, 0, 1)),
                                  ((1, 0, 0), (0, 0, -1))])
def test_absolute_sketch_frame_35_degrees_in_arbitrary_support_plane(u, v):
    before = native_frame(4, 7, -22, (10, 20, 30), u, v)
    actual = frame.target_frame(before, [12, -8], 35)
    expected = native_frame(12, -8, 35, (10, 20, 30), u, v)
    frame.compare_frame(expected, actual)


def test_frame_stale_world_origin_and_nonrigid_axes_refused():
    old = native_frame(0, 0, 0)
    moved = native_frame(0, 0, 0, (0, 0, .1))
    with pytest.raises(ValueError, match="world frame"):
        frame.compare_frame(old, moved)
    old["points"][1] = [2, 0, 0]
    with pytest.raises(ValueError, match="orthonormal"):
        frame.target_frame(old, [1, 2], 35)


def test_frame_angle_wrap_and_nonfinite_input():
    frame.compare_frame(native_frame(1, 2, 0), native_frame(1, 2, 360))
    with pytest.raises(ValueError, match="finite"):
        frame.target_frame(native_frame(0, 0, 0), [math.nan, 0], 35)


@pytest.fixture
def fake_frame(monkeypatch):
    calls = []

    class Definition:
        angle = 0

        def SetLocation(self, x, y):
            calls.append(("SetLocation", x, y))
            return True

    definition = Definition()
    entity = SimpleNamespace(GetDefinition=lambda: definition,
                             Update=lambda: calls.append(("Update",)) or True)
    root = SimpleNamespace(Parts=SimpleNamespace(Count=0))
    doc = SimpleNamespace(ReadOnly=False, PathName="synthetic.m3d")
    k = SimpleNamespace(document=lambda token: SimpleNamespace(RebuildDocument=lambda: True),
                        invalidate_topology=lambda: calls.append(("invalidate",)))
    monkeypatch.setattr(frame, "_document", lambda *args: doc)
    monkeypatch.setattr(frame, "_cast", lambda *args: SimpleNamespace(TopPart=root))
    monkeypatch.setattr(frame, "verify_copy_tree", lambda *args: None)
    monkeypatch.setattr(frame, "verify_external_isolation", lambda *args: [])
    monkeypatch.setattr(frame, "_info", lambda *args: {"document_id": "synthetic"})
    monkeypatch.setattr(frame, "selected_sketches", lambda *args: [entity])
    monkeypatch.setattr(frame, "frame_snapshot", lambda *args: native_frame(0, 0, 0))
    return k, entity, calls


def test_sketch_apply_requires_fresh_frame_and_dry_run_is_read_only(fake_frame):
    k, _entity, calls = fake_frame
    result = frame.set_sketch_frame(k, "h", "copy", "sketch", None, [7, 13], 35)
    assert result["status"] == "planned" and calls == []
    with pytest.raises(ValueError, match="expected_frame"):
        frame.set_sketch_frame(k, "h", "copy", "sketch", None, [7, 13], 35, False)
    assert calls == []
    with pytest.raises(ValueError, match="Stale"):
        frame.set_sketch_frame(k, "h", "copy", "sketch", native_frame(1, 0, 0), [7, 13], 35, False)
    assert calls == []


def test_sketch_native_failure_reports_partial_mutation(fake_frame):
    k, entity, calls = fake_frame
    entity.Update = lambda: False
    result = frame.set_sketch_frame(k, "h", "copy", "sketch", native_frame(0, 0, 0), [7, 13], 35, False)
    assert result["status"] == "failed" and result["mutation_possible"]
    assert result["failed_phase"] == "set_angle" and not result["saved"]
    assert ("SetLocation", 7, 13) in calls
    assert result["after_failure"] == native_frame(0, 0, 0)


def test_sketch_false_world_readback_does_not_become_success(fake_frame):
    k, _entity, _calls = fake_frame
    result = frame.set_sketch_frame(k, "h", "copy", "sketch", native_frame(0, 0, 0), [7, 13], 35, False)
    assert result["status"] == "failed" and result["failed_phase"] == "verify_GetPoint3D"
    assert result["persistence_verified"] is False


def test_noncomponent_dependency_outside_copy_is_rejected(tmp_path, monkeypatch):
    folder = tmp_path / "copies"
    folder.mkdir()
    outside = tmp_path / "original-variable-source.csv"
    outside.write_text("dimension,42", encoding="utf-8")
    observed = []

    def links(k, doc, recursive=False):
        observed.append(recursive)
        return [{"path": str(outside), "type": 19}]

    monkeypatch.setattr(copy, "external_links", links)
    with pytest.raises(ValueError, match="outside-copy external"):
        copy.verify_external_isolation(None, None, folder)
    assert observed == [True]


def fake_body_graph(neighbors, native_multiple=True):
    class Collection:
        def __init__(self, items):
            self.items = items

        def GetCount(self):
            return len(self.items)

        def GetByIndex(self, index):
            return self.items[index]

    faces = []
    for index in range(len(neighbors)):
        entity = SimpleNamespace(_oleobj_=f"face-{index}")
        curve = SimpleNamespace(GetGabarit=lambda i=index: [True, i, 0, 0, i + 1, 1, 1])
        face = SimpleNamespace(GetEntity=lambda e=entity: e, GetArea=lambda units: 2.,
                               EdgeCollection=lambda c=curve: Collection([SimpleNamespace(GetCurve3D=lambda: c)]))
        faces.append(face)
    for index, face in enumerate(faces):
        face.ConnectedFaceCollection = lambda i=index: Collection([
            faces[j] if isinstance(j, int) else SimpleNamespace(GetEntity=lambda: SimpleNamespace(_oleobj_="unknown"))
            for j in neighbors[i]])
    return SimpleNamespace(IsSolid=lambda: True, MultiBodyParts=native_multiple,
                           FaceCollection=lambda: Collection(faces))


def test_face_graph_native_disconnected_flag_and_separate_bounded_patches():
    body = fake_body_graph([[1], [0], [3], [2]])
    result, count = bodies.analyze_body(body, 0, 100, 1000)
    assert count == 4 and result["face_graph_complete"]
    assert result["face_graph_component_count"] == 2
    assert result["material_connectedness"] == "disconnected"
    assert result["status"] == "warning"
    assert result["candidate_boundary_components"][0]["bounds_mm"] == [0, 0, 0, 2, 1, 1]


def test_unknown_neighbor_never_yields_verified_component_count():
    result, _ = bodies.analyze_body(fake_body_graph([["unknown"], []]), 0, 100, 1000)
    assert result["status"] == "inconclusive"
    assert result["face_graph_component_count"] is None and not result["face_graph_complete"]


def test_face_truncation_does_not_certify_one_component():
    result, count = bodies.analyze_body(fake_body_graph([[1], [0]]), 0, 1, 1000)
    assert count == 1 and result["truncated"]
    assert result["face_graph_component_count"] is None


def test_cavity_shells_are_not_called_disconnected_material():
    result, _ = bodies.analyze_body(fake_body_graph([[], []], native_multiple=False), 0, 100, 1000)
    assert result["face_graph_component_count"] == 2
    assert result["material_connectedness"] == "connected_by_native_flag"
    assert result["status"] == "passed"


def test_asymmetric_native_adjacency_is_inconclusive():
    result, _ = bodies.analyze_body(fake_body_graph([[1], []]), 0, 100, 1000)
    assert result["face_graph_component_count"] is None
    assert result["status"] == "inconclusive"


def test_history_flags_use_documented_api7_extension_only(monkeypatch):
    feature = SimpleNamespace(ModelObjectType=25, Reference=2, Name="Native operation",
                              Excluded=False, IsRollBacked=False, MultiBodyParts=True,
                              SubFeatures=lambda *args: [])
    root = SimpleNamespace(ModelObjectType=104, Reference=1,
                           SubFeatures=lambda *args: [feature])
    requested = []

    def cast(k, obj, interface):
        requested.append(interface)
        return obj

    monkeypatch.setattr(bodies, "_cast", cast)
    rows, errors, truncated = bodies.history_flags(None, root)
    assert rows[0]["native_multi_body_parts"] is True and not errors and not truncated
    assert "IModelObject1" in requested  # No API5 application or GetBodyParts is needed.


def test_default_diagnosis_never_reads_historical_side_effecting_properties(monkeypatch):
    body = fake_body_graph([[1], [0], []], native_multiple=True)
    collection = SimpleNamespace(GetCount=lambda: 1, GetByIndex=lambda i: body)
    native_part = SimpleNamespace(BodyCollection=lambda: collection)
    k = SimpleNamespace(document=lambda token: SimpleNamespace(GetPart=lambda kind: native_part))
    doc = SimpleNamespace(Changed=False, PathName="synthetic.m3d")
    monkeypatch.setattr(bodies, "_document", lambda *args: doc)
    monkeypatch.setattr(bodies, "_info", lambda *args: {"kind": "part", "document_id": "synthetic"})
    monkeypatch.setattr(bodies, "_cast", lambda *args: SimpleNamespace(TopPart=None))
    def forbidden(*args):
        raise AssertionError("Historical properties must never be queried by the read-only tool")

    monkeypatch.setattr(bodies, "history_flags", forbidden)
    monkeypatch.setattr(bodies, "history_outline", lambda *args: ([], [], False))
    result = bodies.inspect_body_components(k, "h")
    assert result["status"] == "warning" and result["bodies"][0]["native_multi_body_parts"]
    assert result["historical_multi_body_parts"].startswith("not_queried") and result["memory_unchanged"]


def test_cached_history_outline_never_reads_native_multipart_property(monkeypatch):
    class Feature:
        ModelObjectType = 25
        Reference = 2
        Name = "Existing operation"
        Excluded = False
        IsRollBacked = False

        @property
        def MultiBodyParts(self):
            raise AssertionError("Known mutating native getter must not be called")

        def SubFeatures(self, *args):
            return []

    feature = Feature()
    root = SimpleNamespace(ModelObjectType=104, Reference=1, SubFeatures=lambda *args: [feature])
    monkeypatch.setattr(bodies, "_cast", lambda k, obj, interface: obj)
    rows, errors, limited = bodies.history_outline(None, root)
    assert not errors and not limited
    assert rows[0]["name"] == "Existing operation"
    assert rows[0]["native_multi_body_parts"] is None
    assert rows[0]["multi_body_parts_status"].startswith("not_queried")
