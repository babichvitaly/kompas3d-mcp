"""Synthetic view/anchor contracts; these tests never load COM or a CAD process."""

import asyncio
import copy
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from kompas_mcp import drawing_tools, view_state

IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
TURN = [0., -1., 0., 0., 1., 0., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


class Items:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def Count(self):
        return len(self.values)

    def Item(self, index):
        return self.values[index]

    LineSegment = Item
    Circle = Item
    Arc = Item


@pytest.fixture
def native(monkeypatch, tmp_path):
    source = tmp_path / "asymmetric.m3d"
    source.write_bytes(b"synthetic source: asymmetric part, no CAD bytes")
    drawing_doc = NS(DocumentType=1, Reference=10, PathName=str(tmp_path / "copy.cdw"))
    source_doc = NS(DocumentType=4, Reference=20, PathName=str(source), Changed=False)
    calls = []

    def forbidden():
        calls.append("mutation")
        raise AssertionError("Read-only state operation attempted native mutation")

    class View:
        Number = 1
        Reference = 11
        ViewType = 2
        Valid = True
        ObjectCount = 3
        SourceFileName = str(source)
        ProjectionMatrix = IDENTITY.copy()
        Scale = .5
        X = 40.
        Y = 90.
        Angle = 0.
        Unfold = False
        current = True
        Update = staticmethod(forbidden)
        Rebuild = staticmethod(forbidden)

        @property
        def Current(self):
            return self.current

        @Current.setter
        def Current(self, value):
            forbidden()

    view = View()
    line = NS(kind="line", Reference=100, Valid=True, Temp=False,
              IsVisibleInAssociationView=True, X1=0., Y1=0., X2=10., Y2=0., Style=1,
              GetView=lambda: view)
    line2 = NS(kind="line", Reference=101, Valid=True, Temp=False,
               IsVisibleInAssociationView=True, X1=0., Y1=0., X2=0., Y2=20., Style=1,
               GetView=lambda: view)
    circle = NS(kind="circle", Reference=102, Valid=True, Temp=False,
                IsVisibleInAssociationView=True, Xc=2., Yc=3., Radius=2., Style=1,
                GetView=lambda: view)
    curves = [line, line2, circle]
    view.AssociationObjects = lambda component: tuple(curves)
    container = NS(LineSegments=Items([line, line2]), Circles=Items([circle]), Arcs=Items())
    views = NS(ViewByNumber=lambda number: view, ActiveView=view)
    drawing = NS(ViewsAndLayersManager=NS(Views=views))
    extra = NS(GetObjectsGabarit=lambda v: [True, 0., 0., 10., 20.])
    docs = {"drawing": drawing_doc, "source": source_doc}
    monkeypatch.setattr(view_state, "_document", lambda k, handle: docs[handle])

    def cast(k, obj, interface):
        if interface == "IKompasDocument2D":
            return drawing
        if interface == "IKompasDocument2D1":
            return extra
        if interface == "IDrawingContainer":
            return container
        if interface == "ILineSegment" and getattr(obj, "kind", None) != "line":
            raise TypeError("Not a line")
        if interface == "ICircle" and getattr(obj, "kind", None) != "circle":
            raise TypeError("Not a circle")
        return obj

    monkeypatch.setattr(view_state, "_cast", cast)
    k = NS(constants={"ksDocumentDrawing": 1, "vt_Arbitrary": 2, "vt_Standart": 3,
                      "vt_Projected": 4, "vt_Arrow": 5, "vt_Remote": 6, "vt_Section": 7},
           handle_scopes={"part": "20"}, get_handle=lambda handle: NS(Reference=30))
    result = NS(k=k, source=source, source_doc=source_doc, doc=drawing_doc, view=view,
                container=container, extra=extra, curves=curves, line=line, circle=circle,
                calls=calls, views=views)
    result.inspect = lambda **kw: view_state.inspect_view_state(k, "drawing", 1, **kw)

    def anchor(**kw):
        before = result.inspect()
        args = {"expected_fingerprint": before["fingerprint"]}
        args.update(kw)
        return view_state.find_visible_anchor(k, "drawing", 1, "source", "part", **args)

    result.anchor = anchor
    return result


def test_inspection_captures_real_geometry_unfold_and_camera_without_mutation(native):
    result = native.inspect()
    assert result["state"]["matrix"] == IDENTITY
    assert result["state"]["unfold"] is False
    assert result["state"]["bounds"] == [0., 0., 10., 20.]
    assert result["supported_geometry_objects"] == 3
    assert result["source_geometry_current_verified"] is False
    assert not native.calls


def test_asymmetric_camera_rotation_is_detected_even_with_same_bounds(native):
    expected = native.inspect()["state"]
    native.view.ProjectionMatrix = TURN
    result = view_state.compare_view_state(native.k, "drawing", 1, expected)
    assert not result["matches"] and result["differences"] == ["matrix"]
    assert not native.calls


def test_unfold_change_is_not_hidden_by_equal_bounds_and_count(native):
    expected = native.inspect()["state"]
    native.view.Unfold = True
    result = view_state.compare_view_state(native.k, "drawing", 1, expected)
    assert result["differences"] == ["unfold"]


def test_actual_internal_curve_change_is_detected_with_unchanged_bounds_and_count(native):
    expected = native.inspect()["state"]
    native.line.X2 = 9.
    actual = native.inspect()["state"]
    assert actual["bounds"] == expected["bounds"] and actual["objects"] == expected["objects"]
    assert view_state.compare_view_states(actual, expected)["differences"] == ["geometry_digest"]


def test_geometry_digest_ignores_collection_order_and_session_references(native):
    expected = native.inspect()["state"]
    native.container.LineSegments.values.reverse()
    native.view.Reference = 999
    native.line.Reference = 1234
    assert view_state.compare_view_states(native.inspect()["state"], expected)["matches"]


def test_source_hash_change_invalidates_captured_state(native):
    expected = native.inspect()["state"]
    native.source.write_bytes(b"new source bytes")
    assert "source_sha256" in view_state.compare_view_states(native.inspect()["state"], expected)["differences"]


@pytest.mark.parametrize("problem", ["missing_source", "zero_scale", "nan_pose", "empty_curves",
                                     "invalid_view", "non_associative", "bad_bounds"])
def test_invalid_or_incomplete_state_fails_closed(native, problem):
    if problem == "missing_source":
        native.source.unlink()
    elif problem == "zero_scale":
        native.view.Scale = 0.
    elif problem == "nan_pose":
        native.view.X = float("nan")
    elif problem == "empty_curves":
        native.container.LineSegments.values.clear()
        native.container.Circles.values.clear()
    elif problem == "invalid_view":
        native.view.Valid = False
    elif problem == "non_associative":
        native.view.ViewType = 1
    else:
        native.extra.GetObjectsGabarit = lambda v: [True, 0., 0., 0., 0.]
    with pytest.raises((ValueError, ValidationError)):
        native.inspect()
    assert not native.calls


@pytest.mark.parametrize("matrix", [
    [float("nan")]+IDENTITY[1:],
    [-1.]+IDENTITY[1:],  # orthonormal reflection must still fail
    [2.]+IDENTITY[1:],
    IDENTITY[:12]+[1., 0., 0., 1.],  # translation
    IDENTITY[:15],
])
def test_matrix_preflight_rejects_bad_basis(matrix):
    with pytest.raises(ValueError):
        view_state.rotation_matrix(matrix)


def test_typed_state_rejects_malformed_or_unknown_plan_fields(native):
    state = native.inspect()["state"]
    for change in ({"scale": True}, {"unfold": "true"}, {"unexpected": 1}, {"number": True}):
        with pytest.raises(ValidationError):
            view_state.ViewState.model_validate({**state, **change})


def test_comparison_validates_both_arrays_and_does_not_zip_truncate(native):
    expected = native.inspect()["state"]
    bad = copy.deepcopy(expected)
    bad["matrix"].pop()
    with pytest.raises(ValidationError):
        view_state.compare_view_states(bad, expected)


def test_anchor_selects_an_actual_visible_curve_and_returns_state_provenance(native):
    result = native.anchor()
    assert result["actual_visible_native_projection"]
    assert result["anchor_ref"] == "101"
    assert result["anchor_model_xy"] == [0., 10.]
    assert result["source_sha256"] == native.inspect()["state"]["source_sha256"]
    assert not native.calls


@pytest.mark.parametrize("problem", ["missing", "invalid", "number", "reference"])
def test_pending_current_rejects_before_inspection(native, monkeypatch, problem):
    # Native put_Current(True) can be pending until IDrawingObject.Update.
    fingerprint = native.inspect()["fingerprint"]
    assert native.view.Current is True
    active = NS(Valid=True, Number=1, Reference=11)
    if problem == "missing":
        active = None
    elif problem == "invalid":
        active.Valid = False
    elif problem == "number":
        active.Number = 2
    else:
        active.Reference = 222
    native.views.ActiveView = active
    native.view.Scale = 0.  # Native pending Current can expose a zero scale getter.
    monkeypatch.setattr(view_state, "inspect_view_state", lambda *args, **kw: pytest.fail(
        "Pending Current must not inspect view state"))
    monkeypatch.setattr(view_state, "_geometry", lambda *args, **kw: pytest.fail(
        "Pending Current must not inspect geometry"))
    native.view.AssociationObjects = lambda component: pytest.fail("Pending Current must not enumerate")
    with pytest.raises(ValueError, match="committed Current"):
        view_state.find_visible_anchor(native.k, "drawing", 1, "source", "part", fingerprint)
    assert native.view.Current is True and not native.calls


def test_committed_active_view_uses_native_identity_not_python_wrapper_identity(native):
    native.views.ActiveView = NS(Valid=True, Number=1, Reference=11)
    assert native.views.ActiveView is not native.view
    assert native.anchor()["actual_visible_native_projection"]
    assert not native.calls


@pytest.mark.parametrize("inspection", [1, 2])
def test_anchor_rechecks_context_after_each_inspection(native, monkeypatch, inspection):
    fingerprint = native.inspect()["fingerprint"]
    inspect = view_state.inspect_view_state
    inspected, enumerated = [], []

    def changed(*args, **kw):
        result = inspect(*args, **kw)
        inspected.append(True)
        if len(inspected) == inspection:
            native.views.ActiveView = NS(Valid=True, Number=0, Reference=12)
        return result

    def enumerate_curves(component):
        enumerated.append(True)
        return tuple(native.curves)

    monkeypatch.setattr(view_state, "inspect_view_state", changed)
    native.view.AssociationObjects = enumerate_curves
    with pytest.raises(RuntimeError, match="Current view changed during anchor resolution"):
        view_state.find_visible_anchor(native.k, "drawing", 1, "source", "part", fingerprint)
    assert len(enumerated) == inspection-1
    assert native.view.Current is True and not native.calls


@pytest.mark.parametrize("problem", ["missing", "invalid", "number", "reference"])
def test_anchor_rechecks_active_view_before_final_inspection(native, monkeypatch, problem):
    fingerprint = native.inspect()["fingerprint"]
    inspect = view_state.inspect_view_state
    inspected = []

    def inspect_once(*args, **kw):
        inspected.append(True)
        if len(inspected) > 1:
            pytest.fail("Changed active context must be rejected before final state inspection")
        return inspect(*args, **kw)

    def changed(component):
        active = NS(Valid=True, Number=1, Reference=11)
        if problem == "missing":
            active = None
        elif problem == "invalid":
            active.Valid = False
        elif problem == "number":
            active.Number = 2
        else:
            active.Reference = 222
        native.views.ActiveView = active
        native.view.Scale = 0.
        return tuple(native.curves)

    monkeypatch.setattr(view_state, "inspect_view_state", inspect_once)
    native.view.AssociationObjects = changed
    with pytest.raises(RuntimeError, match="Current view changed during anchor resolution"):
        view_state.find_visible_anchor(native.k, "drawing", 1, "source", "part", fingerprint)
    assert len(inspected) == 1 and native.view.Current is True and not native.calls


@pytest.mark.parametrize("when", ["before", "during"])
def test_active_view_native_getter_failure_is_not_hidden(native, when):
    class BrokenActiveView:
        Valid = True
        Reference = 11

        @property
        def Number(self):
            raise RuntimeError("synthetic disconnected ActiveView getter")

    if when == "before":
        native.views.ActiveView = BrokenActiveView()
        native.view.AssociationObjects = lambda component: pytest.fail(
            "Invalid native active context must not enumerate")
    else:
        def changed(component):
            native.views.ActiveView = BrokenActiveView()
            return tuple(native.curves)

        native.view.AssociationObjects = changed
    with pytest.raises(RuntimeError, match="disconnected ActiveView getter"):
        native.anchor()
    assert not native.calls


def test_circle_anchor_is_on_circumference_not_bbox_or_center(native):
    native.view.AssociationObjects = lambda component: native.circle
    result = native.anchor(near_point=[2., 10.])
    assert result["curve_kind"] == "circle" and result["anchor_model_xy"] == pytest.approx([2., 5.])


@pytest.mark.parametrize("problem", ["hidden", "temporary", "invalid", "other_view", "unscoped",
                                     "dirty_source", "not_current"])
def test_anchor_rejects_invisible_ambiguous_or_unsafe_context(native, problem):
    if problem == "hidden":
        for obj in native.curves:
            obj.IsVisibleInAssociationView = False
    elif problem == "temporary":
        for obj in native.curves:
            obj.Temp = True
    elif problem == "invalid":
        native.view.AssociationObjects = lambda component: NS(
            kind="line", Valid=False, Temp=False, IsVisibleInAssociationView=True,
            GetView=lambda: native.view)
    elif problem == "other_view":
        for obj in native.curves:
            obj.GetView = lambda: NS(Reference=222)
    elif problem == "unscoped":
        native.k.handle_scopes.clear()
    elif problem == "dirty_source":
        native.source_doc.Changed = True
    else:
        native.view.current = False
    with pytest.raises(ValueError):
        native.anchor()
    assert not native.calls


def test_projection_coordinate_does_not_substitute_for_visible_association(native):
    native.view.GetProjectionPoint = lambda *xyz: [True, 10., 20.]
    native.view.AssociationObjects = lambda component: None
    with pytest.raises(ValueError, match="no supported visible"):
        native.anchor()


def test_stale_view_fingerprint_prevents_anchor_enumeration(native):
    stale = native.inspect()["fingerprint"]
    native.view.ProjectionMatrix = TURN
    native.view.AssociationObjects = lambda component: pytest.fail("Stale anchor must not enumerate")
    with pytest.raises(ValueError, match="Stale view"):
        native.anchor(expected_fingerprint=stale)


def test_native_pose_change_during_anchor_resolution_is_not_silently_repaired(native):
    def changed(component):
        native.view.Scale = .25
        return tuple(native.curves)

    native.view.AssociationObjects = changed
    with pytest.raises(RuntimeError, match="View changed"):
        native.anchor()
    assert native.view.Scale == .25 and not native.calls


@pytest.mark.parametrize("change", ["source_dirty", "source_path", "source_reference",
                                    "not_current", "drawing_reference", "component_scope"])
def test_anchor_rechecks_document_identity_changed_and_current_at_end(native, change):
    def changed(component):
        if change == "source_dirty":
            native.source_doc.Changed = True
        elif change == "source_path":
            native.source_doc.PathName = str(native.source.with_name("other.m3d"))
        elif change == "source_reference":
            native.source_doc.Reference = 222
        elif change == "not_current":
            native.view.current = False
        elif change == "drawing_reference":
            native.doc.Reference = 333
        else:
            native.k.handle_scopes["part"] = "222"
        return tuple(native.curves)

    native.view.AssociationObjects = changed
    with pytest.raises(RuntimeError, match="changed during anchor resolution"):
        native.anchor()
    assert not native.calls


def test_skipped_candidates_are_diagnosed_and_native_numeric_failures_are_not_hidden(native):
    native.circle.IsVisibleInAssociationView = False
    result = native.anchor()
    assert result["skipped_candidates"] == {"hidden": 1}
    # Use an extra projected object, outside the main curve inventory, to prove
    # that an anchor getter failure cannot be swallowed as unsupported geometry.
    broken = copy.copy(native.line)
    broken.X1 = float("nan")
    native.view.AssociationObjects = lambda component: (broken, *native.curves)
    with pytest.raises(ValueError, match="non-finite"):
        native.anchor()


def test_unsupported_curve_type_is_counted_and_other_native_errors_propagate(native, monkeypatch):
    unsupported = copy.copy(native.line)
    unsupported.kind = "unsupported"
    native.view.AssociationObjects = lambda component: (unsupported, *native.curves)
    assert native.anchor()["skipped_candidates"] == {"unsupported_curve_type": 1}
    original = view_state._cast

    def disconnected(k, obj, interface):
        if obj is unsupported and interface == "ILineSegment":
            raise RuntimeError("synthetic disconnected native object")
        return original(k, obj, interface)

    monkeypatch.setattr(view_state, "_cast", disconnected)
    with pytest.raises(RuntimeError, match="disconnected native"):
        native.anchor()


def test_anchor_budget_refuses_partial_selection(native):
    with pytest.raises(ValueError, match="exceeds max_objects"):
        native.anchor(max_objects=1)


def test_readonly_tools_still_route_all_native_access_through_existing_worker(monkeypatch):
    registered, calls = {}, []

    class MCP:
        def tool(self):
            def add(fn):
                registered[fn.__name__] = fn
                return fn
            return add

    class Worker:
        async def call(self, fn):
            calls.append("STA")
            return fn("backend")

    monkeypatch.setattr(view_state, "inspect_view_state", lambda *args: {"args": args})
    drawing_tools.register(MCP(), Worker())
    result = asyncio.run(registered["inspect_drawing_view_state"]("drawing", 7))
    assert result == {"args": ("backend", "drawing", 7, 50000)} and calls == ["STA"]
