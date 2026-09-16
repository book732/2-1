from __future__ import annotations

from functools import wraps
from time import perf_counter
from typing import Any, Callable, TypeVar


_Result = TypeVar("_Result")


def log_execution(_function: Callable[..., _Result]) -> Callable[..., _Result]:
    """Record service operation duration without changing its result."""

    @wraps(_function)
    def _wrapped(_self: Any, *args: Any, **kwargs: Any) -> _Result:
        _started_at = perf_counter()
        try:
            return _function(_self, *args, **kwargs)
        finally:
            _elapsed_ms = (perf_counter() - _started_at) * 1000
            _self._logger.info("operation=%s elapsed_ms=%.2f", _function.__name__, _elapsed_ms)

    return _wrapped
