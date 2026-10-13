from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """FastAPI dependency returning the shared Redis client."""
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def set_redis(client: Redis | None) -> None:
    """Swap the shared client (used by tests to inject fakeredis)."""
    global _client
    _client = client
