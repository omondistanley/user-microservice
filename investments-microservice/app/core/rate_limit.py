"""
Sprint 5 — In-process rate limiting for investments API endpoints.
Mirrors expense-microservice/app/core/rate_limit.py.
Sliding window counter by client IP; no Redis dependency.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_store: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 60


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(timestamps: list[float], window: int) -> None:
    cutoff = time.monotonic() - window
    while timestamps and timestamps[0] < cutoff:
        timestamps.pop(0)


def rate_limit_dep(requests_per_minute: int = 60):
    def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        _prune(_store[ip], _WINDOW_SECONDS)
        if len(_store[ip]) >= requests_per_minute:
            raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
        _store[ip].append(time.monotonic())
    return _check
