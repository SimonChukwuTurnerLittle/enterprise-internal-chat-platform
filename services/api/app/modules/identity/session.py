"""Server-side sessions in Redis. The browser only ever holds an opaque, httpOnly session id;
OIDC tokens never reach JavaScript (backend-for-frontend pattern)."""

import hashlib
import json
import secrets
import uuid
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis

LOGIN_STATE_TTL_SECONDS = 600


class SessionData(BaseModel):
    user_id: uuid.UUID
    subject: str
    email: str | None
    name: str | None
    roles: list[str]
    csrf_token: str
    access_token: str
    refresh_token: str | None
    id_token: str | None
    access_expires_at: float


def _session_key(session_id: str) -> str:
    # Store a hash so a Redis dump does not contain usable cookie values.
    return "session:" + hashlib.sha256(session_id.encode()).hexdigest()


class SessionStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def create(self, data: SessionData) -> str:
        session_id = secrets.token_urlsafe(32)
        await self._redis.set(_session_key(session_id), data.model_dump_json(), ex=self._ttl)
        return session_id

    async def get(self, session_id: str) -> SessionData | None:
        raw = await self._redis.get(_session_key(session_id))
        return SessionData.model_validate_json(raw) if raw else None

    async def save(self, session_id: str, data: SessionData) -> None:
        # keepttl: sessions have an absolute lifetime from login; refreshes do not extend it.
        await self._redis.set(_session_key(session_id), data.model_dump_json(), keepttl=True)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(_session_key(session_id))


async def save_login_state(redis: Redis, state: str, data: dict[str, Any]) -> None:
    await redis.set(f"oidc_state:{state}", json.dumps(data), ex=LOGIN_STATE_TTL_SECONDS)


async def pop_login_state(redis: Redis, state: str) -> dict[str, Any] | None:
    """Single-use: the state is deleted as it is read, so a callback cannot be replayed."""
    raw = await redis.getdel(f"oidc_state:{state}")
    return json.loads(raw) if raw else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
