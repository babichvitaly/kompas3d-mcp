"""Drawing safety contracts; real geometry is exercised by validate_drawings13."""

import asyncio
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from kompas_mcp import drawing_tools, drawings


class Items:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def Count(self):
        return len(self.values)

    def Item(self, index):
        return self.values[index]

    View = Item
    LineSegment = Item
    Circle = Item
    Arc = Item


@pytest.fixture
def native(monkeypatch, tmp_path):
    old, new, path = [tmp_path / name for name in ("old.m3d", "new.m3d", "copy.cdw")]
    for file in (old, new, path):
        file.write_bytes(file.name.encode())
    dimtext = NS(AutoNominalValue=True, NominalValue=10., Accuracy=2,
                 NominalText=NS(Str="10"))
    dim = NS(Reference=901, Valid=True, X1=0., Y1=0., X2=10., Y2=0., X3=5., Y3=-3.,
             Orientation=0, text=dimtext)
    events = []

    def dim_update():
        events.append("dimension")
        dimtext.NominalValue = abs(dim.X2-dim.X1)
        dim.X3 = (dim.X1+dim.X2)/2
        dimtext.NominalText.Str = str(dimtext.NominalValue)
        return True

    dim.Update = dim_update
    text = NS(Reference=902, X=5., Y=10., Angle=0., Height=3.5, Width=1., Valid=True,
              Str="Editable source note")
    line = NS(X1=0., Y1=0., X2=10., Y2=0., Style=1)
    container = NS(LineSegments=Items([line]), Circles=Items(), Arcs=Items(),
                   DrawingTexts=Items([text]))
    symbols = NS(LineDimensions=Items([dim]), Leaders=Items())

    class View:
        Reference = 101
        Number = 1
        Name = "Front"
        ViewType = 3
        X = 50.
        Y = 100.
        Scale = 1.
        Angle = 0.
        ObjectCount = 1
        Valid = True
        SourceFileName = str(old)
        UseOcclusion = False
        fail = False
        damage_text = False

        def Update(self):
            events.append("update")
            return not self.fail

        def Rebuild(self):
            events.append("rebuild")
            line.X2 = 12.
            if self.damage_text:
                text.Str = "Lost user text"
            return True

    view = View()

    class Stamp:
        def GetNextColumnId(self, index):
            return {0: 1, 1: 110, 110: 0}[index]

        def Text(self, index):
            return NS(Str={1: "Synthetic drawing", 110: "Engineer"}[index])

    sheet = NS(LayoutLibraryFileName="default.lyt", LayoutStyleNumber=1, SheetType=0,
               Stamp=Stamp())
    drawing = NS(ViewsAndLayersManager=NS(Views=Items([view])), LayoutSheets=Items([sheet]))
    extra = NS(RebuildDocument=lambda: events.append("document_rebuild") or True)
    doc = NS(Reference=1, DocumentType=1, ReadOnly=False, Changed=False, PathName=str(path),
             Visible=False, Active=False)
    app7 = NS(HideMessage=0, Documents=Items())
    k = NS(constants={"ksDocumentDrawing": 1, "vt_Arbitrary": 2, "vt_Standart": 3,
                      "vt_Projected": 4, "vt_Arrow": 5, "vt_Remote": 6, "vt_Section": 7,
                      "ksHideMessageNo": 2}, owned_documents={"1"},
           app=NS(ksGetApplication7=lambda: app7))
    monkeypatch.setattr(drawings, "_document", lambda k, handle: doc)
    monkeypatch.setattr(drawings, "verify_external_isolation", lambda k, doc, root: [])

    @contextmanager
    def linked_document(k, path, read_only=True):
        assert read_only
        yield NS(PathName=str(path))

    monkeypatch.setattr(drawings, "native_document", linked_document)

    def cast(k, obj, interface):
        if interface == "IKompasDocument2D":
            return drawing
        if interface == "IKompasDocument2D1":
            return extra
        if interface == "IDrawingContainer":
            return container
        if interface == "ISymbols2DContainer":
            return symbols
        if interface == "IDimensionText":
            return dimtext
        if interface == "IText":
            return obj
        return obj

    monkeypatch.setattr(drawings, "_cast", cast)
    result = NS(k=k, doc=doc, view=view, text=text, line=line, old=old, new=new, path=path,
                folder=tmp_path, dim=dim, dimtext=dimtext, events=events, app7=app7,
                container=container)

    def run(**kwargs):
        before = drawings.inspect_drawing(k, "h")
        plan = {"replacements": [{"view_number": 1, "expected_source": str(old),
                                   "source": str(new)}],
                "geometry_checks": [{"view_number": 1, "line_bounds": [0., 0., 12., 0.],
                                     "different_from_before": True}],
                "expected_fingerprint": before["fingerprint"]}
        plan.update(kwargs)
        return drawings.rebind_drawing_views(k, "h", str(tmp_path), **plan)

    result.run = run
    return result


def test_inventory_covers_native_stamp_geometry_text_and_dimensions(native):
    state = drawings.inspect_drawing(native.k, "h")
    assert state["views"][0]["geometry"]["lines"][0]["X2"] == 10.
    assert state["sheets"][0]["stamp"] == {"1": "Synthetic drawing", "110": "Engineer"}
    assert state["views"][0]["texts"][0]["text"] == "Editable source note"
    assert state["views"][0]["dimensions"][0]["text"]["NominalValue"] == 10.
    assert not native.events


def test_native_nominal_text_proxy_is_read_as_bstr_and_never_leaks_to_json(native):
    class ITextLine:
        _oleobj_ = object()
        Str = "12 $d1$2$"

        def __str__(self):
            raise AssertionError("A COM proxy representation is not document text")

    native.dimtext.NominalText = ITextLine()
    report = native.folder / "native-text.json"
    result = drawings.inspect_drawing(native.k, "h", report_path=str(report))
    assert result["views"][0]["dimensions"][0]["text"]["NominalText"] == "12 $d1$2$"
    assert json.loads(json.dumps(result)) == json.loads(report.read_text("utf-8"))


def test_non_bstr_native_text_value_fails_before_serialization(native):
    native.dimtext.NominalText = NS(Str=NS(_oleobj_=object()))
    with pytest.raises(TypeError, match="BSTR"):
        drawings.inspect_drawing(native.k, "h")
    assert not native.events


def test_dry_run_does_not_mutate_and_dirty_state_does_not_stale_plan(native):
    before = drawings.inspect_drawing(native.k, "h")
    native.doc.Changed = True
    assert drawings.inspect_drawing(native.k, "h")["fingerprint"] == before["fingerprint"]
    result = native.run()
    assert result["dry_run"] and not result["saved"]
    assert native.view.SourceFileName == str(native.old)
    assert not native.events


def test_rebind_preserves_native_objects_and_checks_real_projected_edges(native):
    result = native.run(dry_run=False)
    assert native.events == ["update", "rebuild", "document_rebuild"]
    assert result["native_content_preserved"] and result["source_files_unchanged"]
    assert result["after"]["views"][0]["reference"] == 101
    assert result["after"]["views"][0]["dimensions"][0]["reference"] == 901
    assert result["geometry_diff"]["1"]["before"] != result["geometry_diff"]["1"]["after"]


def test_explicit_coordinate_dimension_edits_allow_only_expected_auto_center(native):
    before = drawings.inspect_drawing(native.k, "h")
    old = before["views"][0]["dimensions"][0]
    expected = {key: old[key] for key in drawings.DIM_PROPS}
    expected.update(X2=12., X3=6., NominalValue=12.)
    result = native.run(dry_run=False, dimension_changes=[{
        "view_number": 1, "index": 0, "expected": old,
        "endpoints": {"X2": 12.}, "expected_after": expected}])
    assert result["after"]["views"][0]["dimensions"][0]["text"]["NominalValue"] == 12.
    assert native.events.count("dimension") == 1


def test_bad_geometry_is_failure_despite_true_native_returns_and_report_survives(native):
    report = native.folder / "failed.json"
    with pytest.raises(RuntimeError, match="partial changes remain"):
        native.run(dry_run=False, geometry_checks=[{"view_number": 1,
                   "line_bounds": [0., 0., 999., 0.]}], report_path=str(report))
    data = json.loads(report.read_text("utf-8"))
    assert data["phase"] == "failed_partial_mutation"
    assert data["after"]["views"][0]["geometry"]["lines"][0]["X2"] == 12.
    assert native.view.SourceFileName == str(native.new)
    assert native.events.count("update") == 1


def test_lost_editable_text_is_not_hidden_by_rebuild_success(native):
    native.view.damage_text = True
    with pytest.raises(RuntimeError, match="texts"):
        native.run(dry_run=False)


def test_native_failure_is_not_retried_or_rolled_back(native):
    native.view.fail = True
    with pytest.raises(RuntimeError, match="KOMPAS rejected"):
        native.run(dry_run=False)
    assert native.events == ["update"]
    assert native.view.SourceFileName == str(native.new)


def test_stale_fingerprint_prevents_all_mutations(native):
    with pytest.raises(ValueError, match="Stale drawing"):
        native.run(dry_run=False, expected_fingerprint="stale")
    assert not native.events


@pytest.mark.parametrize("problem", ["unowned", "readonly", "outside", "no_geometry", "only_count"])
def test_unsafe_rebind_plans_rejected_before_mutation(native, problem):
    kwargs = {"dry_run": False}
    if problem == "unowned":
        native.k.owned_documents.clear()
    elif problem == "readonly":
        native.doc.ReadOnly = True
    elif problem == "outside":
        kwargs["replacements"] = [{"view_number": 1, "expected_source": str(native.old),
                                   "source": str(native.folder.parent / "outside.m3d")}]
    elif problem == "no_geometry":
        kwargs["geometry_checks"] = []
    elif problem == "only_count":
        kwargs["geometry_checks"] = [{"view_number": 1, "line_count": 1}]
    with pytest.raises(ValueError):
        native.run(**kwargs)
    assert not native.events


def test_inventory_limit_fails_closed(native):
    with pytest.raises(ValueError, match="max_objects"):
        drawings.inspect_drawing(native.k, "h", max_objects=1)
    assert not native.events


def test_inspection_refuses_overwriting_existing_report(native):
    report = native.folder / "report.json"
    report.write_text("keep", "utf-8")
    with pytest.raises(FileExistsError):
        drawings.inspect_drawing(native.k, "h", report_path=str(report))
    assert report.read_text() == "keep"


def test_message_policy_restored_on_converter_exception(native):
    native.app7.HideMessage = 42
    with pytest.raises(RuntimeError, match="converter failed"), drawings._messages_no(native.k):
        assert native.app7.HideMessage == 2
        raise RuntimeError("converter failed")
    assert native.app7.HideMessage == 42


def test_ascii_dxf_validation_checks_native_dimensions_and_eof(tmp_path):
    path = tmp_path / "native.dxf"
    path.write_text("0\nSECTION\n2\nENTITIES\n0\nDIMENSION\n0\nENDSEC\n0\nEOF\n", "utf-8")
    result = drawings.validate_export(path, 1)
    assert result["dimensions"] == 1 and result["structural_validation_passed"]
    with pytest.raises(RuntimeError, match="DIMENSION"):
        drawings.validate_export(path, 2)
    path.write_text(path.read_text().replace("0\nEOF\n", ""))
    with pytest.raises(RuntimeError, match="EOF"):
        drawings.validate_export(path)


def dxf(tmp_path, blocks="", entities="", header=""):
    path = tmp_path / "blocks.dxf"
    text = ("0\nSECTION\n2\nHEADER\n"+header+"0\nENDSEC\n"
            "0\nSECTION\n2\nBLOCKS\n"+blocks+"0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n"+entities+"0\nENDSEC\n0\nEOF\n")
    path.write_text(text, "utf-8")
    return path


def test_dxf_orphan_block_dimension_does_not_confirm_a_drawing_dimension(tmp_path):
    path = dxf(tmp_path, blocks="0\nBLOCK\n2\nOrphan\n0\nDIMENSION\n0\nENDBLK\n")
    result = drawings.validate_export(path)
    assert result["dimensions"] == 0 and result["block_definitions"] == 1
    with pytest.raises(RuntimeError, match="DIMENSION"):
        drawings.validate_export(path, 1)


def test_dxf_explicit_block_instances_and_arrays_are_counted(tmp_path):
    blocks = ("0\nBLOCK\n2\nInner\n0\nDIMENSION\n0\nENDBLK\n"
              "0\nBLOCK\n2\nOuter\n0\nINSERT\n2\ninner\n70\n2\n71\n3\n0\nENDBLK\n"
              "0\nBLOCK\n2\nUnused\n0\nDIMENSION\n0\nENDBLK\n")
    path = dxf(tmp_path, blocks=blocks, entities="0\nDIMENSION\n0\nINSERT\n2\nOUTER\n",
               header="9\n$DIMSTYLE\n2\nStandard\n")
    result = drawings.validate_export(path, 7)
    assert result["dimensions"] == 7
    assert result["direct_dimensions"] == 1
    assert result["dimensions_in_instantiated_blocks"] == 6


@pytest.mark.parametrize("blocks,entities,error", [
    ("", "0\nINSERT\n2\nMissing\n", "unresolved"),
    ("0\nBLOCK\n2\nLoop\n0\nINSERT\n2\nLoop\n0\nENDBLK\n",
     "0\nINSERT\n2\nLoop\n", "cyclic"),
    ("0\nBLOCK\n2\nA\n0\nDIMENSION\n0\nENDBLK\n",
     "0\nINSERT\n2\nA\n70\n1000000\n71\n1000000\n", "instance count"),
])
def test_dxf_ambiguous_instance_graph_fails_closed(tmp_path, blocks, entities, error):
    with pytest.raises(RuntimeError, match=error):
        drawings.validate_export(dxf(tmp_path, blocks, entities))


def test_dependency_closure_hashes_recursive_files_and_all_source_roots(native, monkeypatch):
    linked = native.folder / "linked-variable.txt"
    linked.write_text("controlled source", "utf-8")
    seen = []

    def isolation(k, doc, root):
        seen.append(Path(doc.PathName))
        return [{"path": str(linked)}] if Path(doc.PathName) == native.new else []

    monkeypatch.setattr(drawings, "verify_external_isolation", isolation)
    result = native.run()
    assert set(seen) == {native.path, native.old, native.new}
    assert set(result["source_hashes"]) == {str(path) for path in
                                            (native.path, native.old, native.new, linked)}
    assert not native.events


def test_dirty_open_linked_model_refuses_rebind_before_any_write(native):
    native.app7.Documents = Items([NS(PathName=str(native.new), Changed=True)])
    with pytest.raises(ValueError, match="Unsaved linked document"):
        native.run(dry_run=False)
    assert not native.events


def test_outside_recursive_dependency_refuses_rebind_before_any_write(native, monkeypatch):
    outside = native.folder.parent / "outside-variable.txt"
    outside.write_text("outside", "utf-8")
    monkeypatch.setattr(drawings, "verify_external_isolation", lambda *args: [{"path": str(outside)}])
    with pytest.raises(ValueError, match="outside-copy dependency"):
        native.run(dry_run=False)
    assert not native.events


def test_mutated_recursive_dependency_rejects_native_success(native, monkeypatch):
    dependency = native.folder / "linked.txt"
    dependency.write_text("before", "utf-8")
    monkeypatch.setattr(drawings, "verify_external_isolation", lambda *args: [{"path": str(dependency)}])
    original = native.view.Rebuild

    def mutate():
        original()
        dependency.write_text("changed", "utf-8")
        return True

    native.view.Rebuild = mutate
    with pytest.raises(RuntimeError, match="dependency file changed"):
        native.run(dry_run=False)


def test_pdf_validation_parses_content_and_rejects_empty_page(tmp_path):
    import pymupdf

    path = tmp_path / "page.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.draw_line((20, 20), (100, 20))
        doc.save(path)
    result = drawings.validate_export(path)
    assert result["pages"][0]["drawing_paths"] == 1
    assert not result["visual_layout_verified"]
    empty = tmp_path / "empty.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(empty)
    with pytest.raises(RuntimeError, match="empty page"):
        drawings.validate_export(empty)


def test_export_refuses_dirty_document_and_existing_paths(native):
    native.doc.Changed = True
    with pytest.raises(ValueError, match="Save and reopen"):
        drawings.export_drawing(native.k, "h", str(native.folder), [str(native.folder / "out.pdf")])
    native.doc.Changed = False
    path = native.folder / "out.pdf"
    path.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        drawings.export_drawing(native.k, "h", str(native.folder), [str(path)])
    assert path.read_bytes() == b"keep"


def test_registration_sends_native_operations_only_through_worker(monkeypatch):
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

    monkeypatch.setattr(drawings, "inspect_drawing", lambda *args: args)
    drawing_tools.register(MCP(), Worker())
    result = asyncio.run(registered["inspect_drawing"]("handle"))
    assert calls == ["STA"] and result == ("backend", "handle", True, None, 50000)


def test_strict_preservation_detects_native_dimension_replacement(native):
    before, _ = drawings._inventory(native.k, native.doc, True, 100)
    after = copy.deepcopy(before)
    after["views"][0]["dimensions"][0]["reference"] = 999
    with pytest.raises(RuntimeError, match="reference"):
        drawings._preserve(before, after, {}, {}, {}, {})


def test_explicit_native_view_shift_is_checked_but_never_written(native):
    original_rebuild = native.view.Rebuild

    def shift():
        original_rebuild()
        native.view.X = 51.
        return True

    native.view.Rebuild = shift
    with pytest.raises(RuntimeError, match="view 1.X"):
        native.run(dry_run=False)
    native.view.SourceFileName = str(native.old)
    native.view.X = 50.
    native.line.X2 = 10.
    result = native.run(dry_run=False, view_changes=[{
        "view_number": 1, "expected_x": 51., "expected_y": 100.}])
    assert result["after"]["views"][0]["X"] == 51.


def test_unselected_system_view_dimension_can_be_changed_explicitly(native):
    before, _ = drawings._inventory(native.k, native.doc, True, 100)
    after = copy.deepcopy(before)
    dim = after["views"][0]["dimensions"][0]
    dim.update(X2=12., X3=6.)
    dim["text"].update(NominalValue=12., NominalText="12")
    expected = {key: dim[key] for key in drawings.DIM_PROPS}
    expected["NominalValue"] = 12.
    drawings._preserve(before, after, {}, {(1, 0): {"expected_after": expected}}, {}, {})


def test_invalid_geometry_expectation_is_rejected_before_native_writes(native):
    with pytest.raises(ValueError, match="finite"):
        native.run(dry_run=False, geometry_checks=[{
            "view_number": 1, "line_bounds": [0., 0., float("nan"), 0.]}])
    assert not native.events


AUTO_CAPTION = (
    "^(#0~)brackets=0;param=2;type=view;viewName=2;~"
    "^(#0~)brackets=0;param=3;type=view;viewName=2;~"
    "^(#5~(1:1))brackets=1;param=1;type=view;viewName=2;~"
    "^(#0~)brackets=0;param=5;type=view;viewName=2;~"
)


def native_caption(native, content=AUTO_CAPTION, reference=990):
    caption = NS(Reference=reference, X=40., Y=55., Angle=0., Height=14., Width=16.,
                 Valid=True, Str=content)

    def delete():
        native.events.append(("delete_caption", reference))
        native.container.DrawingTexts.values.remove(caption)
        caption.Valid = False
        return True

    caption.Delete = delete
    return caption


def generate_caption(native, caption, owned_by_view=True):
    old_rebuild = native.view.Rebuild

    def rebuild():
        result = old_rebuild()
        native.container.DrawingTexts.values.append(caption)
        native.view.DrawingText = caption if owned_by_view else NS(Reference=999999)
        return result

    native.view.Rebuild = rebuild


def test_default_strict_policy_preserves_and_rejects_new_auto_caption(native):
    caption = native_caption(native)
    generate_caption(native, caption)
    with pytest.raises(RuntimeError, match="texts"):
        native.run(dry_run=False)
    assert caption.Valid and caption in native.container.DrawingTexts.values
    assert not any(isinstance(event, tuple) for event in native.events)


def test_explicit_caption_cleanup_deletes_only_new_native_owned_scale_caption(native):
    caption = native_caption(native)
    generate_caption(native, caption)
    result = native.run(dry_run=False, remove_new_auto_captions=[1])
    assert result["native_content_preserved"]
    assert result["after_before_caption_cleanup"]["views"][0]["texts"][-1]["text"] == AUTO_CAPTION
    removed = result["removed_new_auto_captions"]
    assert len(removed) == 1 and removed[0]["native_designation_reference"] == 990
    assert removed[0]["caption"]["text"] == AUTO_CAPTION
    assert result["after"]["views"][0]["texts"] == result["before"]["views"][0]["texts"]
    assert native.text in native.container.DrawingTexts.values
    assert ("delete_caption", 990) in native.events


def test_existing_auto_caption_is_protected_even_when_cleanup_is_explicit(native):
    existing = native_caption(native, reference=989)
    native.container.DrawingTexts.values.append(existing)
    native.view.DrawingText = existing
    result = native.run(dry_run=False, remove_new_auto_captions=[1])
    assert existing.Valid and existing in native.container.DrawingTexts.values
    assert not result.get("removed_new_auto_captions")
    assert not any(isinstance(event, tuple) for event in native.events)


@pytest.mark.parametrize("text,owned", [
    ("User note: scale 1:1", True),
    (AUTO_CAPTION+" preserve my extra note", True),
    (AUTO_CAPTION.replace("(1:1)", "(1:5)"), True),
    (AUTO_CAPTION.replace("type=view", "type=user"), True),
    (AUTO_CAPTION.replace("viewName=2", "viewName=2;custom=1"), True),
    (AUTO_CAPTION, False),
])
def test_cleanup_never_deletes_user_text_malformed_markup_or_foreign_designation(native, text, owned):
    caption = native_caption(native, text)
    generate_caption(native, caption, owned_by_view=owned)
    with pytest.raises(RuntimeError, match="texts"):
        native.run(dry_run=False, remove_new_auto_captions=[1])
    assert caption.Valid and caption in native.container.DrawingTexts.values
    assert not any(isinstance(event, tuple) for event in native.events)


def test_cleanup_keeps_baseline_caption_when_deleting_a_new_duplicate(native):
    existing = native_caption(native, reference=989)
    native.container.DrawingTexts.values.append(existing)
    new = native_caption(native, reference=990)
    generate_caption(native, new)
    result = native.run(dry_run=False, remove_new_auto_captions=[1])
    assert existing.Valid and not new.Valid
    assert [row["caption"]["reference"] for row in result["removed_new_auto_captions"]] == [990]


@pytest.mark.parametrize("selection", [True, [2], [1, 1], [True], [{"number": 1}]])
def test_invalid_cleanup_view_selection_fails_before_any_native_write(native, selection):
    with pytest.raises(ValueError, match="explicitly select"):
        native.run(dry_run=False, remove_new_auto_captions=selection)
    assert not native.events


def test_pdf_manifest_discovery_uses_installed_manifest_not_guessed_command(monkeypatch, tmp_path):
    sdk, binary = tmp_path / "SDK", tmp_path / "Bin"
    sdk.mkdir()
    binary.mkdir()
    (binary / "Pdf2d.dll").write_bytes(b"library")
    (binary / "Pdf2d.xml").write_text('<root><appCommand id="17" title="Export PDF"/></root>')
    monkeypatch.setenv("KOMPAS_SDK_PATH", str(sdk))
    library, command, manifest = drawings._pdf_converter()
    assert library == (binary / "Pdf2d.dll").resolve() and command == 17
    assert manifest == Path(binary / "Pdf2d.xml").resolve()


def test_native_acceptance_uses_measured_oracle_text_anchor_not_nominal_center():
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_drawings13.py"
    spec = importlib.util.spec_from_file_location("drawing_acceptance_fixture", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dimension = {"X1": 60., "Y1": 10., "X2": 72., "Y2": 10.,
                 "X3": 62.444167137145996, "Y3": 3., "Orientation": 1,
                 "text": {"AutoNominalValue": True, "NominalValue": 12.}}
    result = module.expected_dimension({"views": [{"Number": 0, "dimensions": [dimension]}]})
    assert result["X3"] == 62.444167137145996
    assert result["X3"] != (result["X1"]+result["X2"])/2
    row = {"Number": 2, "X": 120., "Y": 150., "Scale": 1.}
    assert module.expected_view_position("top", row) == {
        "view_number": 2, "expected_x": 120., "expected_y": 152.}
    assert module.expected_view_position("left", row)["expected_y"] == 150.


def test_native_acceptance_isolates_style_bytes_and_rebinds_without_changing_format(tmp_path):
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_drawings13.py"
    spec = importlib.util.spec_from_file_location("drawing_acceptance_resources", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    installed = tmp_path / "installed" / "graphic.lyt"
    installed.parent.mkdir()
    installed.write_bytes(b"synthetic-layout-style-resource")
    format_values = {"Format": 4, "FormatHeight": 297., "FormatMultiplicity": 1.,
                     "FormatWidth": 210., "VerticalOrientation": True}
    sheet = {"LayoutLibraryFileName": str(installed), "LayoutStyleNumber": 1., "SheetType": 0}
    operations = []

    async def call(name, **kwargs):
        assert name == "api_cast" and kwargs["interface"] == "IKompasDocument2D"
        return {"handle": "drawing"}

    async def invoke(obj, member, *args, action="call", value=None):
        token = obj["handle"]
        if token == "drawing" and member == "LayoutSheets":
            return {"handle": "sheets"}
        if token == "sheets":
            return 1 if member == "Count" else {"handle": "sheet"}
        if token == "sheet":
            if member == "Format":
                return {"handle": "format"}
            if member == "Update":
                operations.append("Update")
                return True
            if action == "set":
                operations.append((member, value))
                sheet[member] = value
                return None
            return sheet[member]
        assert token == "format" and action == "get"
        return format_values[member]

    resource_dir = tmp_path / "isolated" / "resources"
    resources = asyncio.run(module.isolate_layout_resources(
        call, invoke, {"document": {"handle": "doc"}}, resource_dir))
    assert len(resources) == 1
    row = resources[0]
    assert Path(row["copy"]).is_relative_to(resource_dir)
    assert Path(row["copy"]).read_bytes() == installed.read_bytes()
    assert row["format_before"] == row["format_after"] == format_values
    assert operations == [("LayoutLibraryFileName", row["copy"]), "Update"]


@pytest.fixture
def converter_lifecycle(native, monkeypatch):
    expected, _ = drawings._inventory(native.k, native.doc, True, 100)
    before = drawings._export_identity(native.doc)
    live, events = [], []
    fresh = NS(Reference=77, PathName=str(native.path), Changed=False, ReadOnly=False,
               Visible=False, Active=False)

    def info():
        return {"path": str(native.path), "changed": bool(fresh.Changed),
                "read_only": bool(fresh.ReadOnly), "visible": bool(fresh.Visible),
                "document": {"handle": "fresh"}}

    def listed(k, details=False):
        assert not details
        events.append("reconcile")
        k.owned_documents.discard("1")
        return {"documents": [info()] if live else []}

    def opened(k, path, read_only=False, visible=True):
        events.append(("open", path, read_only, visible))
        assert Path(path) == native.path and read_only is False and visible is False
        live.append(fresh)
        return {**info(), "reused": False}

    monkeypatch.setattr(drawings.documents, "list_documents", listed)
    monkeypatch.setattr(drawings.documents, "open_document", opened)
    monkeypatch.setattr(drawings.documents, "document_details", lambda k, handle: info())
    monkeypatch.setattr(drawings, "_document", lambda k, handle: fresh)
    return NS(native=native, expected=expected, before=before, live=live,
              fresh=fresh, events=events)


def test_converter_closed_input_is_reopened_verified_and_returns_fresh_handle(converter_lifecycle):
    case = converter_lifecycle
    doc, info, receipt = drawings._restore_export_source(
        case.native.k, case.native.path, case.before, case.expected)
    assert doc is case.fresh and info["document"]["handle"] == "fresh"
    assert receipt["input_absent_after_native_call"] and receipt["reopened_by_server"]
    assert receipt["native_identity_changed"] and receipt["content_verified"]
    assert receipt["before"]["reference"] == 1 and receipt["after"]["reference"] == 77
    assert case.events == ["reconcile", ("open", str(case.native.path), False, False)]
    assert "77" in case.native.k.owned_documents and "1" not in case.native.k.owned_documents


def test_converter_existing_replacement_is_verified_without_opening_again(converter_lifecycle):
    case = converter_lifecycle
    case.live.append(case.fresh)
    _, _, receipt = drawings._restore_export_source(
        case.native.k, case.native.path, case.before, case.expected)
    assert not receipt["input_absent_after_native_call"] and not receipt["reopened_by_server"]
    assert receipt["native_identity_changed"] and case.events == ["reconcile"]


@pytest.mark.parametrize("problem", ["dirty", "wrong_flags", "changed_text"])
def test_converter_reload_does_not_claim_success_for_dirty_changed_or_wrong_flags(
    converter_lifecycle, problem,
):
    case = converter_lifecycle
    case.live.append(case.fresh)
    if problem == "dirty":
        case.fresh.Changed = True
    elif problem == "wrong_flags":
        case.fresh.Visible = True
    else:
        case.native.text.Str = "Changed during export"
    with pytest.raises(RuntimeError):
        drawings._restore_export_source(case.native.k, case.native.path, case.before, case.expected)
    assert "77" not in case.native.k.owned_documents


def acceptance_module():
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_drawings13.py"
    spec = importlib.util.spec_from_file_location("drawing_acceptance_close", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_close_uses_fresh_path_identity_after_converter_reload(tmp_path):
    module = acceptance_module()
    path = tmp_path / "owned.cdw"
    calls = []
    live = [{"path": str(path), "changed": False, "document": {"handle": "fresh"}}]

    async def call(name, **kwargs):
        calls.append((name, kwargs))
        if name == "list_documents":
            return {"documents": list(live)}
        assert name == "close_document" and kwargs["handle"] == "fresh"
        live.clear()
        return {"closed": True}

    receipt = asyncio.run(module.close_owned_document(call, {"document": {"handle": "stale"}}, path))
    assert receipt["actual_handle"] == "fresh" and receipt["absence_confirmed"]
    assert [name for name, _ in calls] == ["list_documents", "close_document", "list_documents"]


def test_synthetic_close_false_is_reconciled_as_observed_absence_not_invented_true(tmp_path):
    module = acceptance_module()
    path = tmp_path / "owned.cdw"
    live = [{"path": str(path), "changed": False, "document": {"handle": "owned"}}]
    attempts = []

    async def call(name, **kwargs):
        if name == "list_documents":
            return {"documents": list(live)}
        attempts.append(name)
        live.clear()
        raise RuntimeError("Native Close returned False")

    receipt = asyncio.run(module.close_owned_document(call, {"document": {"handle": "owned"}}, path))
    assert receipt["absence_confirmed"] and "native_error" in receipt
    assert "native_result" not in receipt and attempts == ["close_document"]


def test_synthetic_close_error_leaving_document_live_is_failure_without_retry(tmp_path):
    module = acceptance_module()
    path = tmp_path / "owned.cdw"
    live = [{"path": str(path), "changed": False, "document": {"handle": "owned"}}]
    attempts = []

    async def call(name, **kwargs):
        if name == "list_documents":
            return {"documents": list(live)}
        attempts.append(name)
        raise RuntimeError("Native Close returned False")

    with pytest.raises(RuntimeError, match="no automatic retry"):
        asyncio.run(module.close_owned_document(call, {"document": {"handle": "owned"}}, path))
    assert attempts == ["close_document"]
