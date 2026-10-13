"""Test fixtures.

Unit tests need nothing running. Tests that use the `db` fixture need PostgreSQL with pgvector
(TEST_DATABASE_URL, default: the docker-compose database `chat_test`) and are skipped otherwise.
Redis is replaced by fakeredis, and the identity provider by an in-memory fake (FakeIdP).
"""

import os

ISSUER = "https://idp.test/realms/enterprise"
CLIENT_ID = "chat-platform"

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+asyncpg://chat:chat@localhost:5432/chat_test"
        ),
        "DATABASE_POOL_DISABLED": "true",
        "LLM_PROVIDER": "mock",
        "OIDC_ISSUER": ISSUER,
        "OIDC_CLIENT_ID": CLIENT_ID,
        "OIDC_AUDIENCE": CLIENT_ID,
        "OIDC_ROLES_CLAIM": "realm_access.roles",
        "PUBLIC_BASE_URL": "http://testserver",
        "RATE_LIMIT_MESSAGES_PER_MINUTE": "1000",
        "ADMIN_ROLE": "chat-admin",
    }
)

import asyncio  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fakeredis.aioredis import FakeRedis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.redis import set_redis  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.modules.identity.oidc import OidcClient, get_oidc_client  # noqa: E402


class FakeIdP:
    """In-memory OIDC provider: discovery, JWKS and token endpoints, plus a token factory."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key"
        self.next_subject = "alice"
        self.next_roles: list[str] = ["employee"]
        self.next_nonce: str | None = None
        self.token_requests: list[dict[str, str]] = []

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid=self.kid, use="sig", alg="RS256")
        return {"keys": [jwk]}

    def token(
        self,
        sub: str = "alice",
        roles: list[str] | tuple[str, ...] = ("employee",),
        *,
        aud: str = CLIENT_ID,
        issuer: str = ISSUER,
        expires_in: int = 300,
        key: Any = None,
        **extra: Any,
    ) -> str:
        now = int(time.time())
        payload = {
            "iss": issuer,
            "sub": sub,
            "aud": aud,
            "iat": now,
            "exp": now + expires_in,
            "email": f"{sub}@example.com",
            "name": sub.title(),
            "realm_access": {"roles": list(roles)},
            **extra,
        }
        return jwt.encode(payload, key or self.key, algorithm="RS256", headers={"kid": self.kid})

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        base = f"{ISSUER}/protocol/openid-connect"
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{base}/auth",
                    "token_endpoint": f"{base}/token",
                    "jwks_uri": f"{base}/certs",
                    "end_session_endpoint": f"{base}/logout",
                },
            )
        if path.endswith("/certs"):
            return httpx.Response(200, json=self.jwks())
        if path.endswith("/token"):
            form = dict(httpx.QueryParams(request.content.decode()))
            self.token_requests.append(form)
            sub, roles = self.next_subject, self.next_roles
            return httpx.Response(
                200,
                json={
                    "access_token": self.token(sub, roles),
                    "id_token": self.token(sub, roles, nonce=self.next_nonce),
                    "refresh_token": f"refresh-{sub}",
                    "expires_in": 300,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)


@pytest.fixture(scope="session")
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
def fake_redis() -> Iterator[FakeRedis]:
    client = FakeRedis(decode_responses=True)
    set_redis(client)
    yield client
    set_redis(None)


@pytest.fixture
def oidc_client(idp: FakeIdP) -> OidcClient:
    transport = httpx.MockTransport(idp.handler)
    return OidcClient(get_settings(), http=httpx.AsyncClient(transport=transport))


@pytest.fixture
def app(oidc_client: OidcClient, fake_redis: FakeRedis) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_oidc_client] = lambda: oidc_client
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


_schema_ready = False


@pytest.fixture
async def db() -> None:
    """A clean database for each test (schema created once per run, tables truncated)."""
    global _schema_ready
    engine = get_engine()
    if not _schema_ready:
        try:
            async with asyncio.timeout(5):
                async with engine.begin() as conn:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    await conn.run_sync(Base.metadata.drop_all)
                    await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:
            pytest.skip(f"PostgreSQL + pgvector not available (TEST_DATABASE_URL): {exc!r}")
        _schema_ready = True
        return
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def bearer(idp: FakeIdP, sub: str, roles: list[str] | tuple[str, ...]) -> dict[str, str]:
    return {"Authorization": f"Bearer {idp.token(sub, roles)}"}


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        event, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data += line[len("data: ") :]
        events.append((event, json.loads(data) if data else {}))
    return events
