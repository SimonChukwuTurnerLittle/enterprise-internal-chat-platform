import time

from fastapi import HTTPException
from redis.asyncio import Redis


async def enforce_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int = 60) -> None:
    """Fixed-window counter in Redis. Raises 429 once `limit` is exceeded in the window."""
    now = int(time.time())
    bucket = now // window_seconds
    redis_key = f"ratelimit:{key}:{bucket}"
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, window_seconds)
    if count > limit:
        retry_after = window_seconds - (now % window_seconds)
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )
