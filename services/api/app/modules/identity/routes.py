import hmac
import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.modules.audit.service import record_audit
from app.modules.identity.deps import get_principal
from app.modules.identity.models import upsert_user
from app.modules.identity.oidc import (
    OidcClient,
    OidcError,
    extract_roles,
    get_oidc_client,
    new_pkce_pair,
)
from app.modules.identity.principal import Principal
from app.modules.identity.session import (
    SessionData,
    SessionStore,
    new_csrf_token,
    pop_login_state,
    save_login_state,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/auth", tags=["auth"])


def is_safe_return_path(path: str) -> bool:
    """Only same-origin relative paths are allowed after login (prevents open redirects)."""
    return (
        path.startswith("/")
        and not path.startswith("//")
        and "\\" not in path
        and not any(ch in path for ch in "\r\n\t")
    )


@router.get("/login")
async def login(
    return_to: str = Query(default="/", max_length=2000),
    redis: Redis = Depends(get_redis),
    oidc: OidcClient = Depends(get_oidc_client),
) -> RedirectResponse:
    if not is_safe_return_path(return_to):
        return_to = "/"
    verifier, challenge = new_pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    await save_login_state(
        redis, state, {"verifier": verifier, "nonce": nonce, "return_to": return_to}
    )
    url = await oidc.authorization_url(state=state, nonce=nonce, code_challenge=challenge)
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=256),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oidc: OidcClient = Depends(get_oidc_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if error:
        log.info("auth.idp_error", error=error)
        raise HTTPException(status_code=400, detail="Sign-in was cancelled or failed.")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    login_state = await pop_login_state(redis, state)
    if login_state is None:
        raise HTTPException(status_code=400, detail="Sign-in expired. Please try again.")

    try:
        tokens = await oidc.exchange_code(code, login_state["verifier"])
        if not tokens.id_token:
            raise OidcError("No id_token returned")
        id_claims = await oidc.validate(
            tokens.id_token, audience=settings.oidc_client_id, nonce=login_state["nonce"]
        )
        access_claims = await oidc.validate(tokens.access_token, audience=settings.oidc_audience)
        if id_claims["sub"] != access_claims["sub"]:
            raise OidcError("Subject mismatch between id and access token")
    except OidcError as exc:
        log.warning("auth.login_failed", reason=str(exc))
        record_audit(db, action="auth.login", outcome="error", details={"reason": "token_error"})
        await db.commit()
        raise HTTPException(status_code=400, detail="Sign-in failed. Please try again.") from exc

    subject = id_claims["sub"]
    email = id_claims.get("email")
    name = id_claims.get("name") or id_claims.get("preferred_username")
    user_id = await upsert_user(db, subject, email, name)
    roles = sorted(extract_roles(access_claims, settings.oidc_roles_claim))

    store = SessionStore(redis, settings.session_ttl_seconds)
    if previous := request.cookies.get(settings.session_cookie_name):
        await store.delete(previous)  # never reuse a pre-login session id (session fixation)
    session_id = await store.create(
        SessionData(
            user_id=user_id,
            subject=subject,
            email=email,
            name=name,
            roles=roles,
            csrf_token=new_csrf_token(),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            id_token=tokens.id_token,
            access_expires_at=tokens.expires_at,
        )
    )
    record_audit(db, action="auth.login", actor_subject=subject, details={"roles": roles})
    await db.commit()

    response = RedirectResponse(login_state["return_to"], status_code=302)
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oidc: OidcClient = Depends(get_oidc_client),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    logout_url: str | None = None
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        store = SessionStore(redis, settings.session_ttl_seconds)
        session = await store.get(session_id)
        if session is not None:
            sent = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(sent, session.csrf_token):
                raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
            await store.delete(session_id)
            record_audit(db, action="auth.logout", actor_subject=session.subject)
            await db.commit()
            try:
                logout_url = await oidc.end_session_url(
                    session.id_token, settings.public_base_url.rstrip("/") + "/"
                )
            except Exception:  # IdP unreachable: the local session is gone either way
                log.warning("auth.end_session_url_failed")
    response = JSONResponse({"logout_url": logout_url})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


class MeResponse(BaseModel):
    user_id: uuid.UUID
    subject: str
    email: str | None
    name: str | None
    roles: list[str]
    is_admin: bool
    csrf_token: str | None


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        subject=principal.subject,
        email=principal.email,
        name=principal.name,
        roles=sorted(principal.roles),
        is_admin=principal.has_role(settings.admin_role),
        csrf_token=getattr(request.state, "csrf_token", None),
    )
