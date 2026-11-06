"""All COM references live and die on one STA; status never enters its queue."""

import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Lock
from typing import TypeVar
from uuid import uuid4

T = TypeVar("T")


class ComWorker:
    def __init__(self, max_pending=8, history_limit=100):
        if max_pending < 1 or history_limit < 1:
            raise ValueError("Queue and history bounds must be positive")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kompas-sta")
        self.backend = None
        self.max_pending = max_pending
        self.history_limit = history_limit
        self.pending = 0
        self.lock = Lock()
        self.jobs = OrderedDict()
        self.futures = {}
        self.closing = False
        self.initialized = False
        self._com_initialized = False
        self.release_future = None
        self.created_at = time.time()

    def _run(self, fn):
        if self.backend is None:
            import pythoncom

            from kompas_mcp.backend import Kompas

            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            self._com_initialized = True
            try:
                self.backend = Kompas()
            except BaseException:
                pythoncom.CoUninitialize()
                self._com_initialized = False
                raise
            self.initialized = True
        try:
            return fn(self.backend)
        finally:
            import pythoncom

            pythoncom.PumpWaitingMessages()

    def _trim(self):
        # Bound completed history, never evict an active job or its future.
        completed = [key for key, value in self.jobs.items() if value["finished"] is not None]
        for key in completed[:-self.history_limit]:
            del self.jobs[key]

    def _execute(self, job_id, fn):
        with self.lock:
            job = self.jobs[job_id]
            job["state"] = "running"
            job["started"] = time.monotonic()
        return self._run(fn)

    async def call(self, fn: Callable[..., T], name: str | None = None) -> T:
        # Cancelling an awaiting client cannot interrupt a running native CAD call.
        operation = name or getattr(fn, "__name__", "operation")
        if operation == "<lambda>":
            names = getattr(getattr(fn, "__code__", None), "co_names", ())
            operation = names[-1] if names else "anonymous operation"
        job_id = uuid4().hex
        with self.lock:
            if self.closing:
                raise RuntimeError("worker_closing: no new CAD operations accepted")
            if self.pending >= self.max_pending:
                raise RuntimeError("queue_full: COM worker is busy; reconcile before retrying")
            self.pending += 1
            self.jobs[job_id] = {
                "id": job_id, "name": str(operation)[:160], "state": "queued",
                "submitted_at": time.time(), "submitted": time.monotonic(),
                "started": None, "finished": None, "cancel_requested": False, "error": None,
            }

        def finished(future):
            with self.lock:
                job = self.jobs[job_id]
                job["finished"] = time.monotonic()
                if future.cancelled():
                    job["state"] = "cancelled_before_start"
                else:
                    error = future.exception()
                    job["state"] = "failed" if error else "completed"
                    if error:
                        job["error"] = f"{type(error).__name__}: {error}"[:1000]
                self.pending -= 1
                self.futures.pop(job_id, None)
                self._trim()

        # Submission and shutdown must share the same lock: otherwise close()
        # could enqueue STA release between acceptance and executor submission.
        with self.lock:
            if self.closing:
                self.pending -= 1
                del self.jobs[job_id]
                raise RuntimeError("worker_closing: operation was not submitted")
            try:
                future = self.pool.submit(self._execute, job_id, fn)
            except BaseException:
                self.pending -= 1
                del self.jobs[job_id]
                raise
            self.futures[job_id] = future
        future.add_done_callback(finished)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            with self.lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["cancel_requested"] = True
            raise

    def status(self, job_id: str | None = None, limit: int = 30):
        """Thread-safe primitive snapshots, including while the STA is occupied."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        now = time.monotonic()
        with self.lock:
            if job_id is not None and job_id not in self.jobs:
                raise ValueError("Unknown or expired job_id")
            jobs = [self.jobs[job_id]] if job_id else list(self.jobs.values())[-limit:]
            result = []
            for job in jobs:
                end = job["finished"] if job["finished"] is not None else now
                start = job["started"]
                result.append({
                    "id": job["id"], "name": job["name"], "state": job["state"],
                    "submitted_at": job["submitted_at"],
                    "queue_seconds": max(0, (start if start is not None else end)-job["submitted"]),
                    "running_seconds": 0 if start is None else max(0, end-start),
                    "elapsed_seconds": max(0, end-job["submitted"]),
                    "cancel_requested": job["cancel_requested"], "error": job["error"],
                })
            return {
                "pending": self.pending, "max_pending": self.max_pending,
                "closing": self.closing, "sta_initialized": self.initialized,
                "history_limit": self.history_limit, "jobs": result,
                "cancellation": "Queued jobs can be cancelled; running COM calls cannot be interrupted.",
            }

    def cancel(self, job_id: str):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("Unknown or expired job_id")
            self.jobs[job_id]["cancel_requested"] = True
            future = self.futures.get(job_id)
        cancelled = future.cancel() if future is not None else False
        return {
            "job_id": job_id, "cancelled_before_start": cancelled,
            "native_call_interrupted": False,
            "status": self.status(job_id),
            "recovery": "Inspect CAD state after a running operation completes before retrying.",
        }

    def close(self, timeout: float = 2.0):
        """Bound the caller's wait; never kill CAD or free COM from another thread.

        A blocked native call can outlive this wait and hold Python at process exit:
        ThreadPoolExecutor does not provide a safe hard shutdown of an STA call.
        """
        if not math.isfinite(timeout) or not 0 <= timeout <= 30:
            raise ValueError("timeout must be finite and 0..30 seconds")

        def release():
            self.backend = None
            if self._com_initialized:
                import pythoncom

                pythoncom.CoUninitialize()
                self._com_initialized = False
            self.initialized = False

        with self.lock:
            self.closing = True
            futures = list(self.futures.values())
        for future in futures:
            future.cancel()  # only queued calls can be cancelled
        with self.lock:
            if self.release_future is None:
                self.release_future = self.pool.submit(release)
            release_future = self.release_future
        try:
            release_future.result(timeout=timeout)
            closed = True
        except TimeoutError:
            closed = False
        self.pool.shutdown(wait=False)
        return {
            "closed": closed, "wait_seconds": timeout, "native_call_interrupted": False,
            "release_pending": not release_future.done(),
            "limitation": "A running COM call may continue and delay Python process exit.",
        }
