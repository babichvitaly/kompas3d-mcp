"""Job evidence, persistence and timings without a CAD process or COM import."""

import asyncio
import hashlib
import json
import threading

import pytest

from kompas_mcp.job_results import (
    JobResultStore,
    PhaseTimer,
    assess_result,
    main,
    phase,
    result_exit_code,
    verify_result_file,
)
from kompas_mcp.worker import ComWorker


@pytest.mark.parametrize("phase_name", ["failed_left_open", "failed", "error"])
def test_launcher_zero_cannot_hide_returned_failure(tmp_path, phase_name):
    receipt = tmp_path / "result.json"
    receipt.write_text(json.dumps({"phase": phase_name, "elapsed_seconds": 2}))
    result = verify_result_file(receipt, launcher_returncode=0)
    assert result["execution_status"] == "failed"
    assert result["exit_code"] == 1
    assert not result["retry_allowed"]


def test_wrapper_completion_does_not_imply_geometry_or_physical_acceptance():
    result = assess_result({"phase": "complete_closed"}, launcher_returncode=0)
    assert result["execution_status"] == "succeeded"
    assert result["artifact_verification_status"] == "not_verified"
    assert result["physical_acceptance_status"] == "not_reported"
    assert result_exit_code(result) == 0
    assert result_exit_code(result, require_artifact_verification=True) == 2


@pytest.mark.parametrize("payload", [{"phase": "timed_out"}, {"phase": "running"},
                                     {"phase": "future_unknown_phase"}, {}])
def test_timeout_and_unknown_receipts_require_reconciliation(payload):
    result = assess_result(payload, launcher_returncode=0)
    assert result_exit_code(result) == 2
    assert not result["retry_allowed"]


def test_launcher_failure_overrides_claimed_success_and_physical_is_independent():
    result = assess_result({"phase": "complete_closed", "verification": {
        "artifacts": "verified", "physical_acceptance": "accepted",
    }}, launcher_returncode=7)
    assert result["execution_status"] == "failed"
    assert result["physical_acceptance_status"] == "accepted"
    assert result_exit_code(result) == 1


def test_verified_hashes_are_required_and_are_rechecked(tmp_path):
    artifact = tmp_path / "drawing.pdf"
    artifact.write_bytes(b"synthetic artifact")
    result_file = tmp_path / "result.json"
    payload = {"phase": "complete_closed", "verification": {"artifacts": "verified"},
               "artifacts": [{"path": "drawing.pdf",
                              "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
    result_file.write_text(json.dumps(payload))
    result = verify_result_file(result_file, require_artifact_verification=True)
    assert result["exit_code"] == 0
    assert result["artifact_integrity_status"] == "verified"
    artifact.write_bytes(b"changed after producer verification")
    result = verify_result_file(result_file, require_artifact_verification=True)
    assert result["exit_code"] == 1
    assert result["reason"] == "artifact_integrity_failed"
    artifact.unlink()
    assert verify_result_file(result_file)["exit_code"] == 1


def test_claimed_artifact_verification_without_artifacts_is_not_enough(tmp_path):
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps({"phase": "complete_closed",
                                     "verification": {"artifacts": "verified"}}))
    result = verify_result_file(result_file, require_artifact_verification=True)
    assert result["exit_code"] == 2
    assert result["artifact_integrity_status"] == "not_reported"


@pytest.mark.parametrize("raw", [
    '{"phase":"complete_closed","phase":"failed_left_open"}',
    '{"phase":"complete_closed","elapsed":NaN}',
    '[]', '{"schema":"kompas-job-result/99","phase":"completed"}',
])
def test_strict_json_and_unknown_schema_fail_closed(tmp_path, raw):
    result_file = tmp_path / "result.json"
    result_file.write_text(raw)
    with pytest.raises((ValueError, TypeError)):
        verify_result_file(result_file)


def test_cli_returns_failure_for_zero_launcher_failed_payload(tmp_path, capsys):
    result = tmp_path / "result.json"
    result.write_bytes(b'\xef\xbb\xbf{"phase":"failed_left_open"}')
    assert main(["verify-result", str(result), "--launcher-returncode", "0"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["execution_status"] == "failed"
    assert report["artifact_verification_status"] == "not_verified"
    assert main(["verify-result", str(tmp_path / "missing.json")]) == 2


def test_store_owns_unique_directory_and_terminal_is_immutable(tmp_path):
    store = JobResultStore(tmp_path, "synthetic-001", {"input_sha256": "a" * 64})
    store.write("running", owned_documents=[{"id": "owned-copy"}])
    store.write("failed_left_open", owned_documents=[{"id": "owned-copy"}], error="native error")
    receipt = json.loads(store.result_path.read_text())
    events = [json.loads(line) for line in store.events_path.read_text().splitlines()]
    assert [event["phase"] for event in events] == ["created", "running", "failed_left_open"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[-1] == receipt
    assert receipt["owned_documents"] == [{"id": "owned-copy"}]
    assert not list(store.directory.glob("*.tmp"))
    with pytest.raises(RuntimeError, match="immutable"):
        store.write("complete_closed")
    with pytest.raises(FileExistsError):
        JobResultStore(tmp_path, "synthetic-001")
    assert json.loads(store.result_path.read_text()) == receipt


def test_timeout_can_be_reconciled_but_never_authorizes_retry(tmp_path):
    store = JobResultStore(tmp_path, "timed-out")
    store.write("running")
    store.mark_timeout()
    assert verify_result_file(store.result_path)["exit_code"] == 2
    assert not verify_result_file(store.result_path)["retry_allowed"]
    store.write("complete_closed")  # an observed final result from the original job
    assert verify_result_file(store.result_path)["exit_code"] == 0


@pytest.mark.parametrize("job_id", ["../escape", "", "job/one", "a" * 97])
def test_bad_job_identity_cannot_escape_owned_result_directory(tmp_path, job_id):
    with pytest.raises(ValueError, match="job_id"):
        JobResultStore(tmp_path, job_id)
    assert list(tmp_path.iterdir()) == []


def test_nonjson_metadata_rejected_before_job_directory_creation(tmp_path):
    with pytest.raises(ValueError):
        JobResultStore(tmp_path, "nan-input", {"untrusted": float("nan")})
    assert list(tmp_path.iterdir()) == []


def test_nested_monotonic_spans_do_not_double_count():
    clock = iter([0, 1_000_000_000, 3_000_000_000, 5_000_000_000, 6_000_000_000])
    timer = PhaseTimer(clock=lambda: next(clock))
    with timer.span("job") as root_id, phase(
        "source_hash", counts={"files": 7}, cache_hit=True,
    ) as child_id:
        pass
    timing = timer.snapshot()
    parent, child = timing["spans"]
    assert parent["span_id"] == root_id
    assert child["span_id"] == child_id and child["parent_id"] == root_id
    assert parent["elapsed_seconds"] == 5
    assert child["elapsed_seconds"] == 2
    assert parent["exclusive_seconds"] == 3
    assert timing["total_wall_seconds"] == 5
    assert child["counts"] == {"files": 7} and child["cache_hit"]


def test_phase_is_noop_outside_runner_and_context_resets_after_error():
    with phase("unobserved") as span_id:
        assert span_id is None
    timer = PhaseTimer()
    with pytest.raises(RuntimeError), timer.span("failing"), phase("native.save", source="owned-copy"):
        raise RuntimeError("failed native call")
    with phase("unobserved-again") as span_id:
        assert span_id is None
    rows = timer.snapshot()["spans"]
    assert all(row["state"] == "failed" for row in rows)
    assert rows[1]["metadata"] == {"source": "owned-copy"}


def test_thread_context_does_not_inherit_native_span_parent():
    timer = PhaseTimer()
    child_parent = []

    def separate_thread():
        with phase("must remain unobserved") as span_id:
            child_parent.append(span_id)
        with timer.span("thread-job"):
            pass

    with timer.span("main-job"):
        thread = threading.Thread(target=separate_thread)
        thread.start()
        thread.join()
    rows = timer.snapshot()["spans"]
    assert child_parent == [None]
    assert all(row["parent_id"] is None for row in rows)


def test_worker_marks_returned_failure_without_breaking_generic_replies(tmp_path):
    async def run():
        worker = ComWorker(result_directory=tmp_path, runtime_metadata={"fingerprint": "synthetic"})
        worker._run = lambda fn: fn()
        try:
            payload = {"phase": "failed_left_open", "owned_documents": ["owned-copy"]}
            assert await worker.call(lambda: payload, name="mutate-copy") == payload
            row = worker.status()["jobs"][-1]
            assert row["state"] == "failed" and row["execution_status"] == "failed"
            assert row["wrapper_status"] == "completed"
            assert row["result_phase"] == "failed_left_open" and row["receipt_status"] == "written"
            assert verify_result_file(row["receipt_path"], 0)["exit_code"] == 1
            assert await worker.call(lambda: {"count": 4}, name="inspect") == {"count": 4}
            row = worker.status()["jobs"][-1]
            assert row["state"] == "completed" and row["execution_status"] == "unreported"
            assert row["artifact_verification_status"] == "not_verified"
            assert verify_result_file(row["receipt_path"])["exit_code"] == 2
            assert verify_result_file(row["receipt_path"])["phase"] == "wrapper_completed"
            assert row["timing"]["spans"][0]["name"] == "execution"
        finally:
            worker.close()
    asyncio.run(run())


def test_atomic_commit_failure_preserves_previous_readable_snapshot(tmp_path, monkeypatch):
    store = JobResultStore(tmp_path, "commit-failure")
    previous = store.result_path.read_bytes()

    def reject_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("kompas_mcp.job_results.os.replace", reject_replace)
    with pytest.raises(OSError, match="replace failure"):
        store.write("failed_left_open")
    assert store.result_path.read_bytes() == previous
    assert verify_result_file(store.result_path)["exit_code"] == 2
    assert not list(store.directory.glob(".*.tmp"))
    assert json.loads(store.events_path.read_text().splitlines()[-1])["phase"] == "failed_left_open"


def test_queued_cancellation_persists_result_without_running_callback(tmp_path):
    async def run():
        worker = ComWorker(result_directory=tmp_path)
        worker._run = lambda fn: fn()
        started, finish = threading.Event(), threading.Event()
        calls = []

        def blocked():
            started.set()
            assert finish.wait(5)

        active = asyncio.create_task(worker.call(blocked, name="active"))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            queued = asyncio.create_task(worker.call(lambda: calls.append("must not execute"),
                                                     name="queued"))
            await asyncio.sleep(0)
            row = next(row for row in worker.status()["jobs"] if row["name"] == "queued")
            assert worker.cancel(row["id"])["cancelled_before_start"]
            with pytest.raises(asyncio.CancelledError):
                await queued
            row = worker.status(row["id"])["jobs"][0]
            assert row["receipt_status"] == "written"
            assert verify_result_file(row["receipt_path"])["phase"] == "cancelled_before_start"
            assert calls == []
        finally:
            finish.set()
            await active
            worker.close()
    asyncio.run(run())


def test_worker_receipts_survive_bounded_history_and_environment_config(tmp_path, monkeypatch):
    monkeypatch.setenv("KOMPAS_MCP_JOB_DIR", str(tmp_path))

    async def run():
        worker = ComWorker(history_limit=1)
        worker._run = lambda fn: fn()
        try:
            for index in range(3):
                await worker.call(lambda: {"phase": "complete_closed"}, name=f"copy-{index}")
            assert len(worker.status()["jobs"]) == 1
            files = list(tmp_path.glob("*/result.json"))
            assert len(files) == 3
            assert all(verify_result_file(file)["exit_code"] == 0 for file in files)
        finally:
            worker.close()
    asyncio.run(run())


def test_worker_propagates_receipt_failure_after_native_completion(tmp_path, monkeypatch):
    def failed_write(*args, **kwargs):
        raise OSError("simulated full disk")

    async def run():
        worker = ComWorker(result_directory=tmp_path)
        worker._run = lambda fn: fn()
        calls = []
        try:
            # The first created receipt succeeds; fail only the terminal commit.
            original_write = JobResultStore.write

            def write(store, phase_name, **kwargs):
                if phase_name != "created":
                    return failed_write()
                return original_write(store, phase_name, **kwargs)

            monkeypatch.setattr(JobResultStore, "write", write)
            with pytest.raises(RuntimeError, match="receipt_write_failed"):
                await worker.call(lambda: calls.append("executed once"), name="copy")
            row = worker.status()["jobs"][-1]
            assert row["receipt_status"] == "failed" and row["state"] == "failed"
            assert calls == ["executed once"]
        finally:
            worker.close()
    asyncio.run(run())


def test_persistence_remains_pending_and_is_not_evicted_before_commit(tmp_path, monkeypatch):
    async def run():
        worker = ComWorker(result_directory=tmp_path, history_limit=1)
        worker._run = lambda fn: fn()
        native_started, native_finish = threading.Event(), threading.Event()
        writing, publish = threading.Event(), threading.Event()
        original_write = JobResultStore.write

        def blocked_write(store, phase_name, **kwargs):
            if phase_name != "created":
                writing.set()
                assert publish.wait(5)
            return original_write(store, phase_name, **kwargs)

        def operation():
            native_started.set()
            assert native_finish.wait(5)
            return {"phase": "complete_closed"}

        monkeypatch.setattr(JobResultStore, "write", blocked_write)
        active = asyncio.create_task(worker.call(operation, name="persisting"))
        try:
            assert await asyncio.to_thread(native_started.wait, 2)
            native_finish.set()
            assert await asyncio.to_thread(writing.wait, 2)
            status = worker.status()
            assert status["pending"] == 1
            assert status["jobs"][-1]["state"] == "persisting_result"
            assert status["jobs"][-1]["receipt_status"] == "pending"
            publish.set()
            await active
            status = worker.status()
            assert status["pending"] == 0 and status["jobs"][-1]["receipt_status"] == "written"
        finally:
            native_finish.set()
            publish.set()
            await active
            worker.close()
    asyncio.run(run())


@pytest.mark.parametrize("publication_fails", [False, True])
def test_late_wrap_future_waits_for_publication_and_propagates_late_failure(
    tmp_path, monkeypatch, publication_fails,
):
    async def run():
        worker = ComWorker(result_directory=tmp_path)
        worker._run = lambda fn: fn()
        native_finish, writing, publish = threading.Event(), threading.Event(), threading.Event()
        original_write = JobResultStore.write
        original_wrap = asyncio.wrap_future
        wrapped_native = False

        def delayed_write(store, phase_name, **kwargs):
            if phase_name != "created":
                writing.set()
                assert publish.wait(5)
                if publication_fails:
                    raise OSError("late publication failure")
            return original_write(store, phase_name, **kwargs)

        def late_wrap(future, *args, **kwargs):
            nonlocal wrapped_native
            if not wrapped_native:
                wrapped_native = True
                native_finish.set()
                # Deliberately attach the asyncio wrapper *after* the native
                # future is done and its publication callback is blocked.
                assert writing.wait(2)
                assert future.done()
            return original_wrap(future, *args, **kwargs)

        def operation():
            assert native_finish.wait(5)
            return {"phase": "complete_closed"}

        monkeypatch.setattr(JobResultStore, "write", delayed_write)
        monkeypatch.setattr(asyncio, "wrap_future", late_wrap)
        active = asyncio.create_task(worker.call(operation, name="late-wrap"))
        try:
            await asyncio.sleep(0.01)
            assert writing.is_set()
            assert not active.done()
            assert worker.status()["jobs"][-1]["state"] == "persisting_result"
            publish.set()
            if publication_fails:
                with pytest.raises(RuntimeError, match="late publication failure"):
                    await active
            else:
                assert await active == {"phase": "complete_closed"}
            assert worker.pending == 0
        finally:
            native_finish.set()
            publish.set()
            await asyncio.gather(active, return_exceptions=True)
            worker.close()
    asyncio.run(run())
