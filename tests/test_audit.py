"""Safety/provenance contracts; live CAD cases are in validate_audit.py."""

import asyncio
import json
import threading
from types import SimpleNamespace as NS

import pytest

from kompas_mcp import audit, collisions, documents, features
from kompas_mcp.backend import Kompas
from kompas_mcp.worker import ComWorker


def test_nested_rotation_translation_and_parent_bounds():
    parent = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 100, 20, 0, 1]
    child = audit.IDENTITY.copy()
    child[12:15] = [10, 0, 3]
    combined = audit.multiply(child, parent)
    assert combined[12:15] == [100, 30, 3]
    # Child native bounds are already in its parent's coordinates.
    assert audit.transform_bounds([True, 10, 0, 3, 12, 4, 5], parent) == [96, 30, 3, 100, 32, 5]
    assert audit.transform_bounds([False, 0, 0, 0, 0, 0, 0], parent) is None
    assert audit.transform_bounds([True, 1, 0, 0, 0, 1, 1], parent) is None


def feature(**kwargs):
    return NS(State=0, FeatureType=1, Name="feature", Valid=True, ObjectError=0,
              Excluded=False, IsRollBacked=False, **kwargs)


@pytest.mark.parametrize("state,issue", [(2, "rebuild_required"), (1048576, "update_required"),
                                          (2097152, "broken_geometry_link")])
def test_nonzero_state_detected_even_with_zero_object_error(state, issue):
    f = feature()
    f.State = state
    result = audit.feature_state(f)
    assert result["object_error"] == 0
    assert issue in result["issues"]
    assert result["status"] == ("failed" if state == 2097152 else "warning")


def test_empty_service_folder_and_inapplicable_sketch_flag_are_not_geometry_errors():
    f = feature()
    f.FeatureType, f.Valid = 143, False
    assert audit.feature_state(f)["status"] == "passed"
    f.FeatureType, f.Valid, f.State = 104, True, 256
    assert audit.feature_state(f, sketch_type=5)["status"] == "passed"
    f.FeatureType = 5
    assert audit.feature_state(f, sketch_type=5)["issues"] == ["sketch_undefined"]


def test_excluded_errors_are_reported_but_inactive():
    f = feature()
    f.Excluded, f.ObjectError = True, 27
    result = audit.feature_state(f)
    assert result["object_error"] == 27
    assert result["status"] == "inactive"


def test_occurrences_with_same_name_are_resolved_by_path():
    leaves = [NS(Name="same"), NS(Name="same")]
    root = NS(Parts=NS(Count=2, Part=leaves.__getitem__))
    assert audit.resolve_occurrence(None, root, [1]) is leaves[1]
    with pytest.raises(ValueError, match="stale_occurrence"):
        audit.resolve_occurrence(None, root, [2])
    with pytest.raises(ValueError):
        audit.resolve_occurrence(None, root, [-1])


def test_handle_dedup_scoped_alias_release_and_stale_error():
    k = Kompas()
    obj = NS(_oleobj_=object())
    a = k.pack(obj, "doc-a")["handle"]
    assert k.pack(obj, "doc-a")["handle"] == a
    b = k.pack(obj, "doc-b")["handle"]
    unknown = k.pack(obj)["handle"]
    assert len(k.handles) == 3
    assert k.release_scope("doc-a") == 2
    assert k.get_handle(b) is obj
    for stale in (a, unknown):
        with pytest.raises(ValueError, match="stale_handle"):
            k.get_handle(stale)
    assert len(k.handle_keys) == 1


def test_reconcile_external_document_close_releases_all_owned_registries():
    k = Kompas()
    k.connect = lambda: None
    k.app = NS(ksGetApplication7=lambda: NS(Documents=NS(Count=0)))
    token = k.pack(NS(_oleobj_=object()), "closed")["handle"]
    k.document_scopes["doc"] = "closed"
    k.documents["doc"] = object()
    k.model_features["doc"] = object()
    k.entities["entity"] = ("doc", object())
    assert documents.list_documents(k) == {"documents": []}
    assert not k.model_features and not k.documents and not k.entities
    with pytest.raises(ValueError, match="stale_handle"):
        k.get_handle(token)


def test_full_audit_includes_hybrid_own_bodies_and_persisted_diagnostics(tmp_path, monkeypatch):
    k = Kompas()
    k.constants["o3d_sketch"] = 5
    source = tmp_path / "part.m3d"
    source.touch()
    assembly = tmp_path / "assembly.a3d"
    assembly.touch()

    def part(path, reference):
        f = feature()
        f._oleobj_ = object()
        f.ModelObjectType = 104
        f.Reference = reference
        f.FileName = str(path)
        f.Fixed, f.Hidden, f.LoadState = True, False, 0
        f.Placement = NS(GetMatrix3D=lambda: audit.IDENTITY)
        f.GetGabarit = lambda *args: [True, 0, 0, 0, 10, 10, 10]
        f.SubFeatures = lambda *args: []
        f.Parts = NS(Count=0)
        f.ResultBodies = NS(_oleobj_=object(), IsSolid=True, GetGabarit=f.GetGabarit)
        f.Collisions = NS(Count=0)
        f.CheckGeometries = NS(Count=0)
        return f

    root, child = part(assembly, 1), part(source, 2)
    root.Parts = NS(Count=1, Part=lambda i: child)
    diagnostic = feature()
    diagnostic.ObjectError, diagnostic.Valid = 145, False
    diagnostic.ModelObjectType = 656
    root.Collisions = NS(Count=1, Item=lambda i: diagnostic)
    doc = NS(PathName=str(assembly), Reference=123, Changed=False, TopPart=root)
    monkeypatch.setattr(audit, "_document", lambda *args: doc)
    monkeypatch.setattr(audit, "_cast", lambda k, obj, interface: obj)
    result = audit.audit_model(k, "doc", str(tmp_path / "report"))
    assert result["counts"]["body"] == 2  # own assembly body + source body
    assert result["counts"]["occurrence"] == 2
    assert result["counts"]["diagnostic"] == 1
    assert result["checks"]["native_object_errors"] == "failed"
    assert result["checks"]["brep_accuracy"].startswith("inconclusive")
    result = audit.audit_model(k, "doc", str(tmp_path / "bounded"), max_nodes=1)
    assert result["truncated"]
    assert result["checks"]["native_object_errors"] == "inconclusive"


def test_topology_pagination_reuses_explicit_snapshot_and_rejects_stale(monkeypatch):
    k = Kompas()
    k.constants["o3d_face"] = 6
    k.model_features["doc"] = NS(UpdateStamp=1)
    calls = []
    monkeypatch.setattr(features, "_solid_topology", lambda *args: calls.append(args) or [])
    first = features.entities(k, "doc", "o3d_face")
    features.entities(k, "doc", "o3d_face", offset=100, snapshot_id=first["snapshot_id"])
    assert len(calls) == 1
    k.model_features["doc"].UpdateStamp = 2  # external GUI rebuild
    with pytest.raises(ValueError, match="stale_snapshot"):
        features.entities(k, "doc", "o3d_face", snapshot_id=first["snapshot_id"])


def test_read_progress_after_client_loss_and_bound_page(tmp_path):
    audit.write_json(tmp_path / "status.json", {"state": "running"})
    (tmp_path / "journal.jsonl").write_text("\n".join(json.dumps({"i": i}) for i in range(8)))
    result = audit.read_report(str(tmp_path), 3, 2)
    assert result["rows"] == [{"i": 3}, {"i": 4}]
    assert result["summary"]["state"] == "running"
    with pytest.raises(ValueError):
        audit.read_report(str(tmp_path), limit=201)


def test_copy_guard_includes_excluded_dependencies(tmp_path):
    outside = tmp_path / "source.m3d"
    outside.touch()
    folder = tmp_path / "copy"
    folder.mkdir()
    part = NS(FileName=str(outside), Parts=NS(Count=0), Excluded=True)
    root = NS(FileName=str(folder / "a.a3d"), Parts=NS(Count=1, Part=lambda i: part))
    with pytest.raises(ValueError, match="Dependency outside"):
        collisions.verify_copy_tree(None, NS(PathName=root.FileName), root, str(folder))


def test_ghost_collision_endpoint_cannot_become_proven_pair(monkeypatch):
    monkeypatch.setattr(collisions, "_cast", lambda *args: NS(
        IsSolid=False, GetGabarit=lambda: [False, 0, 0, 0, 0, 0, 0]
    ))
    result = collisions.endpoint(None, object())
    assert not result["usable_body"]
    assert not result["occurrence_resolved"]


def test_open_reuses_canonical_path_and_checks_actual_readonly(tmp_path, monkeypatch):
    path = tmp_path / "part.m3d"
    path.touch()
    existing = NS(PathName=str(path), ReadOnly=False)
    collection = NS(Count=1, Item=lambda i: existing)
    k = Kompas()
    k.connect = lambda: None
    k.app = NS(ksGetApplication7=lambda: NS(Documents=collection))
    monkeypatch.setattr(documents, "_info", lambda k, doc: {"identity": id(doc)})
    result = documents.open_document(k, str(path.parent / "." / path.name))
    assert result == {"identity": id(existing), "reused": True}
    with pytest.raises(ValueError, match="read_only_mismatch"):
        documents.open_document(k, str(path), read_only=True)


def test_queue_bound_survives_cancellation_of_running_native_call():
    async def run():
        worker = ComWorker(max_pending=1)
        started, finish = threading.Event(), threading.Event()

        def blocked():
            started.set()
            assert finish.wait(5)

        worker._run = lambda fn: fn()
        task = asyncio.create_task(worker.call(blocked))
        try:
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(RuntimeError, match="queue_full"):
                await worker.call(lambda: None)
            assert worker.pending == 1
        finally:
            finish.set()
            await asyncio.to_thread(worker.close)
        assert worker.pending == 0

    asyncio.run(run())
