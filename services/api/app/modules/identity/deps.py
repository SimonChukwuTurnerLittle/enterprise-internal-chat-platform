"""Authentication dependencies. `Depends(get_principal)` plays the role Spring Security's
filter chain + @AuthenticationPrincipal play in a Spring app."""

import hmac
import time

import structlog
from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.modules.identity.models import upsert_user
from app.modules.identity.oidc import OidcClient, OidcError, extract_roles, get_oidc_client
from app.modules.identity.principal import Principal
from app.modules.identity.session import SessionData, SessionStore

log = structlog.get_logger()

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
REFRESH_MARGIN_SECONDS = 30


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def get_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    oidc: OidcClient = Depends(get_oidc_client),
    settings: Settings = Depends(get_settings),
) -> Principal:
    authorization = request.headers.get("authorization")
    if authorization:
        return await _principal_from_bearer(authorization, db, oidc, settings)

    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise _unauthorized()
    store = SessionStore(redis, settings.session_ttl_seconds)
    session = await store.get(session_id)
    if session is None:
        raise _unauthorized("Session expired")

    # Cookie-authenticated, state-changing requests must echo the session's CSRF token.
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, session.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")

    if session.access_expires_at - time.time() < REFRESH_MARGIN_SECONDS:
        session = await _refresh_session(session_id, session, store, oidc, settings)

    request.state.csrf_token = session.csrf_token
    return Principal(
        user_id=session.user_id,
        subject=session.subject,
        email=session.email,
        name=session.name,
        roles=frozenset(session.roles),
        auth_method="session",
    )


async def _principal_from_bearer(
    authorization: str, db: AsyncSession, oidc: OidcClient, settings: Settings
) -> Principal:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Unsupported authorization scheme")
    try:
        claims = await oidc.validate(token, audience=settings.oidc_audience)
    except OidcError as exc:
        log.info("auth.bearer_rejected", reason=str(exc))
        raise _unauthorized("Invalid or expired token") from exc
    user_id = await upsert_user(db, claims["sub"], claims.get("email"), claims.get("name"))
    await db.commit()
    return Principal(
        user_id=user_id,
        subject=claims["sub"],
        email=claims.get("email"),
        name=claims.get("name"),
        roles=extract_roles(claims, settings.oidc_roles_claim),
        auth_method="bearer",
    )


async def _refresh_session(
    session_id: str,
    session: SessionData,
    store: SessionStore,
    oidc: OidcClient,
    settings: Settings,
) -> SessionData:
    """Refresh tokens near expiry. Roles are re-read, so IdP role changes and account
    disablement take effect within one access-token lifetime."""
    if not session.refresh_token:
        await store.delete(session_id)
        raise _unauthorized("Session expired")
    try:
        tokens = await oidc.refresh(session.refresh_token)
        claims = await oidc.validate(tokens.access_token, audience=settings.oidc_audience)
    except OidcError as exc:
        log.info("auth.refresh_failed", subject=session.subject, reason=str(exc))
        await store.delete(session_id)
        raise _unauthorized("Session expired") from exc
    if claims["sub"] != session.subject:
        await store.delete(session_id)
        raise _unauthorized("Session expired")
    session = session.model_copy(
        update={
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or session.refresh_token,
            "id_token": tokens.id_token or session.id_token,
            "access_expires_at": tokens.expires_at,
            "roles": sorted(extract_roles(claims, settings.oidc_roles_claim)),
        }
    )
    await store.save(session_id, session)
    return session


async def require_admin(
    principal: Principal = Depends(get_principal), settings: Settings = Depends(get_settings)
) -> Principal:
    if not principal.has_role(settings.admin_role):
        raise HTTPException(status_code=403, detail="Administrator role required")
    return principal
