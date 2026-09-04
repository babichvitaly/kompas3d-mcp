"""All COM references live and die on one STA thread, never on MCP's pool."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


class ComWorker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kompas-sta")
        self.backend = None

    def _run(self, fn):
        if self.backend is None:
            import pythoncom

            from kompas_mcp.backend import Kompas

            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            self.backend = Kompas()
        try:
            return fn(self.backend)
        finally:
            import pythoncom

            pythoncom.PumpWaitingMessages()

    async def call(self, fn: Callable[..., T]) -> T:
        # Cancellation cannot interrupt a running CAD mutation. The single worker
        # still finishes it before accepting the next operation.
        return await asyncio.wrap_future(self.pool.submit(self._run, fn))

    def close(self):
        def release():
            if self.backend is not None:
                import pythoncom

                self.backend = None
                pythoncom.CoUninitialize()

        self.pool.submit(release).result()
        self.pool.shutdown(wait=True)
