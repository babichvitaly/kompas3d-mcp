"""Portable job receipts and timings; no COM imports or application access.

An executor finishing, an artifact being verified, and physical acceptance are
different observations.  In particular an exit code of zero cannot turn a
``failed_left_open`` receipt into a successful CAD operation.
"""

import argparse
import contextvars
import hashlib
import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

SCHEMA = "kompas-job-result/1"
SUCCESS_PHASES = frozenset({"complete", "complete_closed", "completed", "succeeded", "success"})
FAILURE_PHASES = frozenset({"failed", "error", "cancelled_before_start", "cancelled"})
INCOMPLETE_PHASES = frozenset({
    "created", "queued", "running", "timed_out", "timeout", "reconciliation_required",
})
_CURRENT_TIMER = contextvars.ContextVar("kompas_current_phase_timer", default=None)


def _json_copy(value):
    """Reject non-finite numbers, COM objects and other non-JSON state."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _state(value, allowed, default):
    return value if isinstance(value, str) and value in allowed else default


def assess_result(payload, launcher_returncode=None):
    """Classify a receipt without turning a generic tool reply into a certificate.

    ``None`` means no launcher observation, not a synthetic zero.  Legacy native
    dictionaries with a known phase remain usable; unknown phases fail closed in
    the CLI.  Worker callers may still return arbitrary ordinary values.
    """
    phase = payload.get("phase") if isinstance(payload, dict) else None
    phase = phase if isinstance(phase, str) else None
    failure = phase in FAILURE_PHASES or bool(phase and phase.startswith("failed_"))
    if launcher_returncode is not None and launcher_returncode != 0:
        execution = "failed"
        reason = "launcher_nonzero"
    elif failure:
        execution, reason = "failed", "returned_failure_phase"
    elif phase in SUCCESS_PHASES:
        execution, reason = "succeeded", "known_success_phase"
    elif phase in INCOMPLETE_PHASES:
        execution, reason = "incomplete", "reconcile_before_retry"
    else:
        execution, reason = "unreported", "no_known_terminal_phase"

    verification = payload.get("verification", {}) if isinstance(payload, dict) else {}
    verification = verification if isinstance(verification, dict) else {}
    artifact = _state(verification.get("artifacts"),
                      {"verified", "failed", "not_verified", "not_applicable"}, "not_verified")
    physical = _state(verification.get("physical_acceptance"),
                      {"accepted", "rejected", "pending", "not_reported"}, "not_reported")
    if artifact == "failed" and execution == "succeeded":
        execution, reason = "failed", "artifact_verification_failed"
    # Physical acceptance is deliberately independent of wrapper/CAD execution.
    return {
        "phase": phase,
        "execution_status": execution,
        "artifact_verification_status": artifact,
        "physical_acceptance_status": physical,
        "launcher_returncode": launcher_returncode,
        "reason": reason,
        "retry_allowed": False,
        "recovery": "Reconcile the final receipt, owned documents and artifacts before retrying.",
    }


def result_exit_code(assessment, require_artifact_verification=False):
    """0: declared execution passed; 1: failure; 2: incomplete/unknown evidence."""
    if assessment["execution_status"] == "failed":
        return 1
    if assessment["execution_status"] != "succeeded":
        return 2
    if require_artifact_verification and (
        assessment["artifact_verification_status"] != "verified"
        or assessment.get("artifact_integrity_status") != "verified"
    ):
        return 2
    return 0


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def verify_result_file(path, launcher_returncode=None, require_artifact_verification=False):
    """Read UTF-8/BOM JSON and check listed artifact SHA without importing COM.

    SHA agreement proves file integrity, not geometric correctness.  The latter
    remains the producer's explicit verification observation.  Reading a receipt
    never authorizes retrying a possibly still running native mutation.
    """
    source = Path(path)
    raw = source.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_strict_object,
                         parse_constant=_reject_constant)
    if not isinstance(payload, dict):
        raise TypeError("Result receipt must be a JSON object")
    if "schema" in payload and payload["schema"] != SCHEMA:
        raise ValueError("Unsupported job-result schema")
    assessment = assess_result(payload, launcher_returncode)
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise TypeError("artifacts must be a list")
    checked = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            raise TypeError("Each artifact requires a path and SHA-256")
        expected = artifact.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ValueError("Each artifact requires a SHA-256 hex digest")
        file = Path(artifact["path"])
        if not file.is_absolute():
            file = source.parent / file
        try:
            actual = hashlib.sha256(file.read_bytes()).hexdigest()
            matches = actual == expected.lower()
        except OSError:
            actual, matches = None, False
        checked.append({"path": str(file), "sha256": actual, "matches": matches})
    integrity = "verified" if checked and all(x["matches"] for x in checked) else "not_reported"
    if any(not x["matches"] for x in checked):
        integrity = "failed"
        assessment.update(execution_status="failed", reason="artifact_integrity_failed")
    assessment.update(
        artifact_integrity_status=integrity, checked_artifacts=checked,
        receipt_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assessment["exit_code"] = result_exit_code(assessment, require_artifact_verification)
    return assessment


def _union_duration(intervals):
    total = 0
    end = None
    for start, stop in sorted(intervals):
        if end is None or start > end:
            total += max(0, stop - start)
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total


class PhaseTimer:
    """Thread-safe monotonic spans with context-local parents and no double count."""

    def __init__(self, clock=None):
        self._clock = clock or time.perf_counter_ns
        self._parents = contextvars.ContextVar(f"phase_parents_{uuid4().hex}", default=())
        self._records = []
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name, *, counts=None, cache_hit=False, metadata=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Span name must be nonempty")
        if not isinstance(cache_hit, bool):
            raise TypeError("cache_hit must be boolean")
        counters = _json_copy(counts or {})
        if not isinstance(counters, dict) or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counters.values()
        ):
            raise ValueError("Span counts must be nonnegative integer counters")
        parents = self._parents.get()
        record = {
            "span_id": uuid4().hex, "parent_id": parents[-1] if parents else None,
            "name": name, "started_ns": self._clock(), "finished_ns": None,
            "state": "running", "counts": counters, "cache_hit": cache_hit,
            "metadata": _json_copy(metadata or {}),
        }
        with self._lock:
            self._records.append(record)
        token = self._parents.set((*parents, record["span_id"]))
        timer_token = _CURRENT_TIMER.set(self)
        try:
            yield record["span_id"]
        except BaseException:
            with self._lock:
                record["state"] = "failed"
            raise
        else:
            with self._lock:
                record["state"] = "completed"
        finally:
            finished = self._clock()
            with self._lock:
                record["finished_ns"] = finished
            self._parents.reset(token)
            _CURRENT_TIMER.reset(timer_token)

    def snapshot(self):
        now = self._clock()
        with self._lock:
            records = _json_copy(self._records)
        roots = []
        for record in records:
            start = record["started_ns"]
            end = record["finished_ns"] if record["finished_ns"] is not None else now
            children = []
            for child in records:
                if child["parent_id"] == record["span_id"]:
                    child_end = child["finished_ns"] if child["finished_ns"] is not None else now
                    children.append((max(start, child["started_ns"]), min(end, child_end)))
            elapsed = max(0, end - start)
            record["elapsed_seconds"] = elapsed / 1e9
            record["exclusive_seconds"] = max(0, elapsed - _union_duration(children)) / 1e9
            if record["parent_id"] is None:
                roots.append((start, end))
        return {
            "clock": "monotonic_nanoseconds",
            "total_wall_seconds": _union_duration(roots) / 1e9,
            "spans": records,
            "scope": "Inclusive child spans overlap parents; do not sum elapsed_seconds.",
        }


@contextmanager
def phase(name, *, counts=None, cache_hit=False, **metadata):
    """Instrument an existing backend function without changing its signature.

    Outside a worker/runner span this is a no-op.  Within a span, parentage is
    context-local; no timer or COM object is transferred into another thread.
    """
    timer = _CURRENT_TIMER.get()
    if timer is None:
        yield None
    else:
        with timer.span(name, counts=counts, cache_hit=cache_hit, metadata=metadata) as span_id:
            yield span_id


def _atomic_json(path, payload):
    raw = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Windows does not expose the same directory-fsync contract as POSIX.
        if os.name != "nt":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


class JobResultStore:
    """Exclusive per-job directory; atomically replaced result plus append-only events.

    Metadata may carry input SHA, runtime fingerprint, app PID/creation time and
    the owned-document ledger.  No value is invented when that evidence is absent.
    A timeout receipt remains reconcilable; terminal success/failure is immutable.
    """

    def __init__(self, directory, job_id, metadata=None):
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", job_id):
            raise ValueError("job_id must be 1..96 ASCII letters/digits, '_' or '-'")
        self.metadata = _json_copy(metadata or {})
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a JSON object")
        self.job_id = job_id
        base = Path(directory).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.directory = base / job_id
        self.directory.mkdir(exist_ok=False)
        self.result_path = self.directory / "result.json"
        self.events_path = self.directory / "events.jsonl"
        self.timer = PhaseTimer()
        self._lock = threading.Lock()
        self._sequence = 0
        self._terminal = False
        self.write("created")

    def write(self, phase, *, verification=None, artifacts=None, owned_documents=None, error=None):
        if not isinstance(phase, str) or not phase:
            raise ValueError("phase must be nonempty")
        payload = _json_copy({
            "schema": SCHEMA, "job_id": self.job_id, "metadata": self.metadata,
            "phase": phase, "verification": verification or {}, "artifacts": artifacts or [],
            "owned_documents": owned_documents, "error": error, "retry_allowed": False,
            "timing": self.timer.snapshot(),
        })
        assessment = assess_result(payload)
        with self._lock:
            if self._terminal:
                raise RuntimeError("Terminal result is immutable; reconcile or use a new job_id")
            self._sequence += 1
            payload["sequence"] = self._sequence
            payload["recorded_unix_ns"] = time.time_ns()
            event = (json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n").encode()
            with self.events_path.open("ab") as stream:
                stream.write(event)
                stream.flush()
                os.fsync(stream.fileno())
            _atomic_json(self.result_path, payload)
            self._terminal = assessment["execution_status"] in {"succeeded", "failed"}
        return _json_copy(payload)

    def mark_timeout(self, reason="client_timeout"):
        """Record uncertainty; do not cancel, close, kill or retry native work."""
        return self.write("reconciliation_required", error=str(reason))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect CAD job evidence without COM")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-result", help="Check terminal phase and artifact hashes")
    verify.add_argument("path")
    verify.add_argument("--launcher-returncode", type=int, default=None)
    verify.add_argument("--require-artifact-verification", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify_result_file(args.path, args.launcher_returncode,
                                    args.require_artifact_verification)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"execution_status": "unreported", "reason": str(exc),
                          "exit_code": 2, "retry_allowed": False}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
