"""Common middleware implementations for OJS job processing.

Provides ready-to-use middleware for logging, timeouts, retries, and metrics.
Also re-exports core middleware types from the sibling ``middleware.py`` module
so that ``from ojs.middleware import EnqueueMiddleware`` works even when the
package directory shadows the module file.

Usage::

    from ojs.middleware.logging import logging_middleware
    from ojs.middleware.timeout import timeout_middleware
    from ojs.middleware.retry import retry_middleware
    from ojs.middleware.metrics import MetricsRecorder, metrics_middleware
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# --- Re-export core middleware types ---
# The sibling ``middleware.py`` (module) is shadowed by this package directory.
# We load it explicitly so ``from ojs.middleware import EnqueueMiddleware`` works.
_module_path = Path(__file__).parent.parent / "middleware.py"
if _module_path.exists():
    _spec = importlib.util.spec_from_file_location("ojs._middleware_types", str(_module_path))
    if _spec and _spec.loader:
        _mod: types.ModuleType = importlib.util.module_from_spec(_spec)
        sys.modules[_mod.__name__] = _mod
        _spec.loader.exec_module(_mod)

        EnqueueNext = _mod.EnqueueNext
        EnqueueMiddleware = _mod.EnqueueMiddleware
        ExecutionNext = _mod.ExecutionNext
        ExecutionMiddleware = _mod.ExecutionMiddleware
        EnqueueMiddlewareChain = _mod.EnqueueMiddlewareChain
        ExecutionMiddlewareChain = _mod.ExecutionMiddlewareChain

from ojs.middleware.logging import logging_middleware
from ojs.middleware.metrics import MetricsRecorder, metrics_middleware
from ojs.middleware.retry import retry_middleware
from ojs.middleware.timeout import TimeoutError as MiddlewareTimeoutError
from ojs.middleware.timeout import timeout_middleware

__all__ = [
    # Core types
    "EnqueueNext",
    "EnqueueMiddleware",
    "ExecutionNext",
    "ExecutionMiddleware",
    "EnqueueMiddlewareChain",
    "ExecutionMiddlewareChain",
    # Built-in middleware
    "logging_middleware",
    "timeout_middleware",
    "retry_middleware",
    "metrics_middleware",
    "MetricsRecorder",
    "MiddlewareTimeoutError",
]
