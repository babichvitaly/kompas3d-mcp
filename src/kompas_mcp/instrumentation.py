"""Opt-in native phase timings; no live COM objects enter the result ledger."""

from functools import wraps

from .job_results import phase


def timed_phase(name):
    def decorate(fn):
        @wraps(fn)
        def measured(*args, **kwargs):
            with phase(name, counts={"function_calls": 1}):
                return fn(*args, **kwargs)
        return measured
    return decorate
