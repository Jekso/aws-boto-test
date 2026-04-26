"""Compatibility wrapper for tenacity.

Falls back to no-op decorators when tenacity is unavailable so the project can
still be imported in lightweight local test environments.
"""

from __future__ import annotations

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except Exception:  # pragma: no cover
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def retry_if_exception_type(*args, **kwargs):
        return None

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None
