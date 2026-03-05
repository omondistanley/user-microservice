"""
Simple in-memory rate limiting utilities.
For production with multiple instances, replace backing storage with Redis.
"""
import math
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Request

# key -> list of request timestamps (pruned to window)
_store: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    window_seconds: int


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(timestamps: list[float], window: int, now: float) -> None:
    cutoff = now - window
    while timestamps and timestamps[0] < cutoff:
        timestamps.pop(0)


def reset_rate_limit_store() -> None:
    _store.clear()


def evaluate_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int = _WINDOW_SECONDS,
) -> RateLimitDecision:
    if max_requests <= 0:
        return RateLimitDecision(
            allowed=False,
            limit=max_requests,
            remaining=0,
            retry_after_seconds=window_seconds,
            window_seconds=window_seconds,
        )
    now = time.monotonic()
    bucket = _store[key]
    _prune(bucket, window_seconds, now)
    if len(bucket) >= max_requests:
        oldest = bucket[0]
        retry_after = max(1, int(math.ceil(window_seconds - (now - oldest))))
        return RateLimitDecision(
            allowed=False,
            limit=max_requests,
            remaining=0,
            retry_after_seconds=retry_after,
            window_seconds=window_seconds,
        )

    bucket.append(now)
    remaining = max_requests - len(bucket)
    return RateLimitDecision(
        allowed=True,
        limit=max_requests,
        remaining=max(remaining, 0),
        retry_after_seconds=0,
        window_seconds=window_seconds,
    )


def allow_rate_limit(key: str, max_requests: int, window_seconds: int = _WINDOW_SECONDS) -> bool:
    return evaluate_rate_limit(key, max_requests=max_requests, window_seconds=window_seconds).allowed


def get_client_ip(request: Request) -> str:
    return _get_client_ip(request)


def rate_limit_dep(requests_per_minute: int = 10):
    """
    Dependency factory: limit to requests_per_minute per IP per minute.
    Use: Depends(rate_limit_dep(5)) on login/register routes.
    """

    def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        decision = evaluate_rate_limit(ip, requests_per_minute, _WINDOW_SECONDS)
        if not decision.allowed:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=429,
                detail={
                    "message": "Too many requests. Try again later.",
                    "limit": decision.limit,
                    "window_seconds": decision.window_seconds,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            )
        return None

    return _check
