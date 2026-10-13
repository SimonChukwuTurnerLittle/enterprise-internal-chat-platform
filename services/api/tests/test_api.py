"""End-to-end API tests against a real PostgreSQL + pgvector (skipped if unavailable)."""

import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.audit.models import AuditEvent
from app.modules.chat.prompts import FALLBACK_ANSWER
from tests.conftest import ISSUER, FakeIdP, bearer, parse_sse

pytestmark = pytest.mark.usefixtures("db")

LEAVE_POLICY = b"""# Annual Leave Policy

## Entitlement

Full-time employees receive 25 days of annual leave per year, plus public holidays.

## Carry-over

Up to 5 unused days can be carried over into the next year and must be used by 31 March.
"""

SALARY_BANDS = b"""# Salary Bands

## Band structure

Salary band C ranges from 45,000 to 60,000 per year. Band D ranges from 60,000 to 80,000.
"""

ADMIN = ("carol", ["employee", "manager", "chat-admin"])
EMPLOYEE = ("alice", ["employee"])
MANAGER = ("dave", ["employee", "manager"])


async def _create_source(
    client: httpx.AsyncClient, idp: FakeIdP, slug: str, acl_roles: list[str]
) -> str:
    response = await client.post(
        "/api/v1/admin/knowledge/sources",
        json={"slug": slug, "name": slug.replace("-", " ").title(), "acl_roles": acl_roles},
        headers=bearer(idp, *ADMIN),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _upload(
    client: httpx.AsyncClient, idp: FakeIdP, source_id: str, name: str, data: bytes
) -> httpx.Response:
    return await client.post(
        f"/api/v1/admin/knowledge/sources/{source_id}/documents",
        files={"file": (name, data, "text/markdown")},
        headers=bearer(idp, *ADMIN),
    )


@pytest.fixture
async def knowledge(db: None, client: httpx.AsyncClient, idp: FakeIdP) -> None:
    open_source = await _create_source(client, idp, "hr-policies", [])
    restricted = await _create_source(client, idp, "hr-managers", ["manager"])
    assert (await _upload(client, idp, open_source, "leave.md", LEAVE_POLICY)).status_code == 201
    assert (await _upload(client, idp, restricted, "bands.md", SALARY_BANDS)).status_code == 201


async def _ask(
    client: httpx.AsyncClient, idp: FakeIdP, who: tuple[str, list[str]], question: str
) -> tuple[str, list[tuple[str, dict]]]:
    headers = bearer(idp, *who)
    conversation = await client.post("/api/v1/conversations", json={}, headers=headers)
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": question},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return conversation_id, parse_sse(response.text)


def _answer(events: list[tuple[str, dict]]) -> str:
    return "".join(data["text"] for event, data in events if event == "token")


def _citations(events: list[tuple[str, dict]]) -> list[dict]:
    return next(data["citations"] for event, data in events if event == "citations")


@pytest.mark.usefixtures("knowledge")
async def test_grounded_answer_streams_with_citations_and_is_persisted(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    conversation_id, events = await _ask(
        client, idp, EMPLOYEE, "How many days of annual leave do I get?"
    )
    names = [event for event, _ in events]
    assert names[0] == "message.start" and names[-1] == "message.end"
    citations = _citations(events)
    assert citations and citations[0]["document_title"] == "Annual Leave Policy"
    assert "[1]" in _answer(events)

    detail = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=bearer(idp, *EMPLOYEE)
    )
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["document_title"] == "Annual Leave Policy"
    assert detail.json()["title"] == "How many days of annual leave do I get?"

    async with get_sessionmaker()() as db:
        stmt = select(AuditEvent).where(AuditEvent.action == "chat.message")
        audit = (await db.scalars(stmt)).one()
    assert audit.actor_subject == "alice"
    assert audit.details["grounded"] is True
    assert "How many" not in json.dumps(audit.details)  # no message content in the audit log


@pytest.mark.usefixtures("knowledge")
async def test_restricted_knowledge_is_never_retrieved_for_unauthorised_roles(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    question = "What is the salary range for band C?"
    _, employee_events = await _ask(client, idp, EMPLOYEE, question)
    assert all(c["document_title"] != "Salary Bands" for c in _citations(employee_events))
    assert "45,000" not in _answer(employee_events)

    _, manager_events = await _ask(client, idp, MANAGER, question)
    assert _citations(manager_events)[0]["document_title"] == "Salary Bands"


@pytest.mark.usefixtures("knowledge")
async def test_unanswerable_question_gets_the_fallback(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    _, events = await _ask(client, idp, EMPLOYEE, "What will the weather be in Paris tomorrow?")
    assert _citations(events) == []
    assert _answer(events).strip() == FALLBACK_ANSWER


async def test_conversations_are_private_to_their_owner(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    created = await client.post("/api/v1/conversations", json={}, headers=bearer(idp, *EMPLOYEE))
    conversation_id = created.json()["id"]
    other = bearer(idp, "bob", ["employee"])
    read = await client.get(f"/api/v1/conversations/{conversation_id}", headers=other)
    assert read.status_code == 404
    send = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "hi"}, headers=other
    )
    assert send.status_code == 404
    listing = await client.get("/api/v1/conversations", headers=other)
    assert listing.json() == []


async def test_admin_endpoints_require_admin_role(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    response = await client.get("/api/v1/admin/knowledge/sources", headers=bearer(idp, *EMPLOYEE))
    assert response.status_code == 403
    response = await client.get("/api/v1/admin/audit", headers=bearer(idp, *EMPLOYEE))
    assert response.status_code == 403


async def test_reuploading_an_unchanged_document_is_skipped(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    source_id = await _create_source(client, idp, "it-kb", [])
    first = await _upload(client, idp, source_id, "leave.md", LEAVE_POLICY)
    second = await _upload(client, idp, source_id, "leave.md", LEAVE_POLICY)
    changed = await _upload(client, idp, source_id, "leave.md", LEAVE_POLICY + b"\nUpdated.\n")
    assert [r.json()["status"] for r in (first, second, changed)] == [
        "created",
        "unchanged",
        "updated",
    ]
    rejected = await _upload(client, idp, source_id, "virus.exe", b"MZ")
    assert rejected.status_code == 422


async def test_rate_limit_returns_429(
    client: httpx.AsyncClient, idp: FakeIdP, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_messages_per_minute", 1)
    headers = bearer(idp, *EMPLOYEE)
    created = await client.post("/api/v1/conversations", json={}, headers=headers)
    conversation_id = created.json()["id"]
    url = f"/api/v1/conversations/{conversation_id}/messages"
    assert (await client.post(url, json={"content": "hello"}, headers=headers)).status_code == 200
    limited = await client.post(url, json={"content": "hello"}, headers=headers)
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


async def test_browser_session_login_csrf_refresh_and_logout(
    client: httpx.AsyncClient, idp: FakeIdP, fake_redis: FakeRedis
) -> None:
    # 1. Login redirect stores single-use state
    login = await client.get("/api/auth/login", params={"return_to": "/c/123"})
    state = httpx.URL(login.headers["location"]).params["state"]
    stored = json.loads(await fake_redis.get(f"oidc_state:{state}"))
    idp.next_subject, idp.next_roles, idp.next_nonce = "erin", ["employee"], stored["nonce"]

    # 2. Callback sets an httpOnly session cookie and returns to the original page
    callback = await client.get("/api/auth/callback", params={"code": "abc", "state": state})
    assert callback.status_code == 302, callback.text
    assert callback.headers["location"] == "/c/123"
    assert "httponly" in callback.headers["set-cookie"].lower()
    replay = await client.get("/api/auth/callback", params={"code": "abc", "state": state})
    assert replay.status_code == 400

    # 3. Cookie-authenticated writes need the CSRF token
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["subject"] == "erin"
    csrf = me.json()["csrf_token"]
    assert (await client.post("/api/v1/conversations", json={})).status_code == 403
    created = await client.post("/api/v1/conversations", json={}, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201

    # 4. Near-expiry tokens are refreshed and roles re-read from the IdP
    session_key = next(k for k in await fake_redis.keys("session:*"))
    session = json.loads(await fake_redis.get(session_key))
    session["access_expires_at"] = 0
    await fake_redis.set(session_key, json.dumps(session), keepttl=True)
    idp.next_roles = ["employee", "manager"]
    refreshed = await client.get("/api/auth/me")
    assert refreshed.json()["roles"] == ["employee", "manager"]
    assert idp.token_requests[-1]["grant_type"] == "refresh_token"

    # 5. Logout clears the session and returns the IdP logout URL
    logout = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.json()["logout_url"].startswith(ISSUER)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_widget_config_is_public_and_validates_app(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/widget/config", params={"app_id": "nope"})
    assert response.status_code == 404
