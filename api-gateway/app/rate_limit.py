"""
Redis-backed rate limiting. Sliding window via sorted set.
If Redis is unavailable, allow and log (fail-open for availability).
"""
import logging
import time
from dataclasses import dataclass

from redis.asyncio import Redis

from app.config import REDIS_URL

logger = logging.getLogger("gateway.rate_limit")

_WINDOW_SECONDS = 60


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    limit: int
    remaining: int


async def check_rate_limit(
    redis: Redis | None,
    key: str,
    limit: int,
    window_seconds: int = _WINDOW_SECONDS,
) -> RateLimitResult:
    """
    Sliding window: add current timestamp to sorted set, remove old entries, count.
    Key should be e.g. ratelimit:user:123 or ratelimit:ip:1.2.3.4
    """
    if not redis or limit <= 0:
        return RateLimitResult(allowed=True, retry_after_seconds=0, limit=limit, remaining=limit)

    full_key = f"ratelimit:{key}"
    now = time.time()
    window_start = now - window_seconds

    try:
        pipe = redis.pipeline()
        pipe.zremrangebyscore(full_key, 0, window_start)
        pipe.zadd(full_key, {str(now): now})
        pipe.zcard(full_key)
        pipe.expire(full_key, window_seconds + 1)
        results = await pipe.execute()
        count = results[2] if isinstance(results[2], int) else 0

        if count <= limit:
            remaining = max(0, limit - count)
            return RateLimitResult(
                allowed=True,
                retry_after_seconds=0,
                limit=limit,
                remaining=remaining,
            )

        # Over limit: compute retry_after from oldest in window
        oldest = await redis.zrange(full_key, 0, 0, withscores=True)
        if oldest:
            oldest_ts = oldest[0][1]
            retry_after = max(1, int(window_seconds - (now - oldest_ts)))
        else:
            retry_after = 1

        return RateLimitResult(
            allowed=False,
            retry_after_seconds=min(retry_after, window_seconds),
            limit=limit,
            remaining=0,
        )
    except Exception as e:
        logger.warning("rate_limit_redis_error key=%s error=%s", key, e)
        return RateLimitResult(allowed=True, retry_after_seconds=0, limit=limit, remaining=limit)


def get_redis() -> Redis | None:
    if not REDIS_URL:
        return None
    try:
        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning("redis_connect_failed url=%s error=%s", REDIS_URL, e)
        return None
