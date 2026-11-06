"""Runtime 13 contracts; no COM import or native CAD process is needed."""

import asyncio
import threading
import time
from types import SimpleNamespace as NS

import pytest
from mcp.server.fastmcp import FastMCP

from kompas_mcp import bridge, documents, runtime_tools
from kompas_mcp.backend import Kompas
from kompas_mcp.worker import ComWorker


@pytest.fixture
def document_case(monkeypatch):
    k = Kompas()
    k.constants = {constant: i for i, (constant, _) in enumerate(documents.KINDS.values())}
    k.constants["kdDoNotSaveChanges"] = 0
    rows = []

    class Collection:
        @property
        def Count(self):
            return len(rows)

        def Item(self, index):
            return rows[index]

    k.connect = lambda: None
    k.app = NS(ksGetApplication7=lambda: NS(Documents=Collection()))
    monkeypatch.setattr(documents, "_cast", lambda k, obj, interface: obj)

    def add(reference, changed=False, owned=False):
        doc = NS(_oleobj_=object(), Reference=reference, DocumentType=0,
                 Name=f"part-{reference}", PathName=f"C:/copies/{reference}.m3d",
                 Changed=changed, ReadOnly=False, Visible=True, Active=False)
        doc.Close = lambda option: rows.remove(doc) is None
        rows.append(doc)
        handle = k.pack(doc, str(reference))["handle"]
        if owned:
            k.owned_documents.add(str(reference))
        return doc, handle

    return k, rows, add


def test_summary_avoids_top_part_and_preserves_actual_visibility(document_case):
    k, rows, add = document_case
    doc, handle = add(1)
    doc.Visible = False
    result = documents.list_documents(k, details=False)["documents"]
    assert result[0]["document"]["handle"] == handle
    assert result[0]["visible"] is False
    assert not result[0]["owned_by_server"]
    assert "top_part" not in result[0]
    assert not k.documents and not k.model_features
    assert len(rows) == 1


def test_api5_registration_adoption_and_external_close_share_scope(document_case):
    k, rows, add = document_case
    _doc, handle = add(7)
    native = NS(_oleobj_=object(), reference=7)
    legacy_id = k.register_document(native)
    assert k.register_document(native) == legacy_id
    assert k.document_scopes[legacy_id] == "7"
    assert not k.owned_documents
    k.remember(legacy_id, object())
    k.model_features[legacy_id] = object()
    rows.clear()  # externally closed in the UI
    documents.list_documents(k, details=False)
    assert not k.documents and not k.document_scopes and not k.entities and not k.model_features
    with pytest.raises(ValueError, match="stale_handle"):
        k.get_handle(handle)


def test_batch_default_only_owned_and_explicit_dry_run(document_case):
    k, rows, add = document_case
    _, keep = add(1, owned=True)
    _, own = add(2, owned=True)
    _, adopted = add(3)
    _, changed = add(4, changed=True, owned=True)
    plan = documents.close_documents(k, [keep])
    assert plan["dry_run"] and len(rows) == 4
    assert {row["handle"]: row["state"] for row in plan["documents"]} == {
        keep: "kept", own: "candidate", changed: "skipped_changed"}
    assert adopted not in {row["handle"] for row in plan["documents"]}
    result = documents.close_documents(k, [keep], dry_run=False)
    assert result["closed_count"] == 1 and len(rows) == 3
    assert not result["discarded_changes"]
    # Explicit adopted unchanged documents can be closed, without being claimed.
    assert documents.close_documents(k, [keep], [adopted], False)["closed_count"] == 1
    assert "3" not in k.owned_documents


def test_batch_rechecks_changed_after_an_earlier_close(document_case):
    k, rows, add = document_case
    first, a = add(1, owned=True)
    second, b = add(2, owned=True)

    def close_first(option):
        rows.remove(first)
        second.Changed = True
        return True

    first.Close = close_first
    result = documents.close_documents(k, [], [a, b], False)
    assert [row["state"] for row in result["documents"]] == ["closed", "skipped_changed"]
    assert rows == [second] and second.Changed


def test_batch_refuses_stale_and_keep_candidate_overlap(document_case):
    k, rows, add = document_case
    _, handle = add(1)
    with pytest.raises(ValueError, match="overlap"):
        documents.close_documents(k, [handle], [handle], False)
    with pytest.raises(ValueError, match="stale_handle"):
        documents.close_documents(k, [], ["not-a-handle"], False)
    assert len(rows) == 1


def test_save_as_void_noop_does_not_validate_preexisting_output(tmp_path, monkeypatch):
    k = Kompas()
    k.constants = {constant: i for i, (constant, _) in enumerate(documents.KINDS.values())}
    target = tmp_path / "existing.m3d"
    target.write_bytes(b"old")
    doc = NS(ReadOnly=False, DocumentType=0, PathName=str(target), Changed=False,
             SaveAs=lambda path: None)
    monkeypatch.setattr(documents, "_document", lambda *args: doc)
    with pytest.raises(RuntimeError, match="no write evidence"):
        documents.save_document(k, "doc", str(target), overwrite=True)

    def write(path):
        target.write_bytes(b"new native contents")
    doc.SaveAs = write
    result = documents.save_document(k, "doc", str(target), overwrite=True)
    assert result["write_evidence"] == "updated" and len(result["sha256"]) == 64
    doc.Changed = True
    with pytest.raises(RuntimeError, match="postcondition"):
        documents.save_document(k, "doc", str(target), overwrite=True)


def test_cached_sdk_description_is_deep_copied_and_type_specific():
    def method(self, value=1):
        return value

    wrapper = type("ISynthetic", (), {"__module__": "win32com.gen_py.synthetic",
                   "Call": method, "_prop_map_get_": {"Name": object()}, "_prop_map_put_": {}})
    bridge._describe_type.cache_clear()
    first = bridge.describe_type(wrapper)
    first["methods"]["Call"]["parameters"][0]["name"] = "corrupted"
    second = bridge.describe_type(wrapper)
    assert second["methods"]["Call"]["parameters"][0]["name"] == "value"
    assert bridge._describe_type.cache_info().hits == 1


def test_health_and_job_status_while_native_queue_is_occupied():
    async def run():
        worker = ComWorker(max_pending=2)
        started, finish = threading.Event(), threading.Event()
        worker._run = lambda fn: fn()

        def blocked():
            started.set()
            assert finish.wait(5)
            return "done"

        task = asyncio.create_task(worker.call(blocked, name="native mutation"))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            before = time.monotonic()
            health = runtime_tools.health_snapshot(worker, [{"name": "health", "inputSchema": {}}])
            assert time.monotonic() - before < 1
            assert health["tool_count"] == 1
            assert health["worker"]["jobs"][0]["state"] == "running"
            job_id = health["worker"]["jobs"][0]["id"]
            cancelled = worker.cancel(job_id)
            assert not cancelled["cancelled_before_start"]
            assert not cancelled["native_call_interrupted"] and worker.pending == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert worker.status(job_id)["jobs"][0]["cancel_requested"]
        finally:
            finish.set()
            await asyncio.to_thread(worker.close)
        final = worker.status(job_id)["jobs"][0]
        assert final["state"] == "completed" and final["running_seconds"] >= 0
        assert worker.pending == 0
    asyncio.run(run())


def test_queued_cancel_never_invokes_callback_and_close_wait_is_bounded():
    async def run():
        worker = ComWorker(max_pending=3, history_limit=2)
        worker._run = lambda fn: fn()
        started, finish = threading.Event(), threading.Event()
        calls = []

        def blocked():
            started.set()
            assert finish.wait(5)
        active = asyncio.create_task(worker.call(blocked, name="blocked"))
        assert await asyncio.to_thread(started.wait, 2)
        queued = asyncio.create_task(worker.call(lambda: calls.append("must not run"), name="queued"))
        await asyncio.sleep(0)
        queued_id = next(job["id"] for job in worker.status()["jobs"] if job["name"] == "queued")
        assert worker.cancel(queued_id)["cancelled_before_start"]
        with pytest.raises(asyncio.CancelledError):
            await queued
        begin = time.monotonic()
        result = await asyncio.to_thread(worker.close, 0.01)
        assert time.monotonic() - begin < 1
        assert not result["closed"] and result["release_pending"]
        assert not result["native_call_interrupted"]
        with pytest.raises(RuntimeError, match="worker_closing"):
            await worker.call(lambda: None)
        finish.set()
        await active
        assert (await asyncio.to_thread(worker.close, 2))["closed"]
        assert calls == []
        assert worker.status(queued_id)["jobs"][0]["state"] == "cancelled_before_start"
    asyncio.run(run())


def test_history_bounded_and_schema_fingerprint_order_canonical():
    async def run():
        worker = ComWorker(history_limit=2)
        worker._run = lambda fn: fn()
        try:
            for number in range(5):
                assert await worker.call(lambda value=number: value, name=f"read {number}") == number
            state = worker.status()
            assert len(state["jobs"]) == 2
            assert [job["name"] for job in state["jobs"]] == ["read 3", "read 4"]
            mcp = FastMCP("runtime-unit")
            runtime_tools.register(mcp, worker)
            health = await mcp.call_tool("runtime_health", {})
            assert health is not None
            names = {tool.name for tool in await mcp.list_tools()}
            assert names == {"runtime_health", "job_status", "cancel_job", "document_details",
                             "close_documents"}
        finally:
            await asyncio.to_thread(worker.close)
    asyncio.run(run())
