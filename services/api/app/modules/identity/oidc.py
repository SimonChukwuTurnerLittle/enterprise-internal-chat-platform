"""Minimal OIDC relying-party client: discovery, auth-code + PKCE, refresh, JWT validation."""

import asyncio
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import Settings, get_settings

ALLOWED_ALGORITHMS = {"RS256", "RS384", "RS512", "PS256", "ES256"}
METADATA_TTL_SECONDS = 3600
JWKS_MIN_REFRESH_SECONDS = 60


class OidcError(Exception):
    pass


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    id_token: str | None
    refresh_token: str | None
    expires_at: float


class OidcClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._metadata: dict[str, Any] | None = None
        self._metadata_fetched_at = 0.0
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def metadata(self) -> dict[str, Any]:
        if self._metadata is None or time.time() - self._metadata_fetched_at > METADATA_TTL_SECONDS:
            response = await self._http.get(self._settings.oidc_discovery_endpoint)
            response.raise_for_status()
            self._metadata = response.json()
            self._metadata_fetched_at = time.time()
        return self._metadata

    async def _refresh_keys(self) -> None:
        jwks_uri = (await self.metadata())["jwks_uri"]
        response = await self._http.get(jwks_uri)
        response.raise_for_status()
        keys: dict[str, jwt.PyJWK] = {}
        for entry in response.json().get("keys", []):
            if entry.get("use", "sig") != "sig":
                continue  # skip encryption keys
            try:
                keys[entry.get("kid", "")] = jwt.PyJWK(entry)
            except jwt.PyJWTError:
                continue
        self._keys = keys
        self._keys_fetched_at = time.time()

    async def _signing_key(self, kid: str | None) -> jwt.PyJWK:
        async with self._lock:
            if not self._keys:
                await self._refresh_keys()
            key = self._keys.get(kid or "")
            # Unknown kid usually means the IdP rotated keys; refetch, but not too often.
            if key is None and time.time() - self._keys_fetched_at > JWKS_MIN_REFRESH_SECONDS:
                await self._refresh_keys()
                key = self._keys.get(kid or "")
        if key is None:
            raise OidcError("Token signed with an unknown key")
        return key

    async def validate(
        self, token: str, *, audience: str, nonce: str | None = None
    ) -> dict[str, Any]:
        """Verify signature, issuer, audience and expiry; return the claims."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OidcError("Malformed token") from exc
        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise OidcError("Unsupported token algorithm")
        key = await self._signing_key(header.get("kid"))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[algorithm],
                audience=audience,
                issuer=self._settings.oidc_issuer,
                leeway=self._settings.oidc_clock_skew_seconds,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise OidcError(f"Invalid token: {exc}") from exc
        if nonce is not None and claims.get("nonce") != nonce:
            raise OidcError("Nonce mismatch")
        return claims

    async def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        endpoint = (await self.metadata())["authorization_endpoint"]
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": self._settings.oidc_redirect_uri,
            "scope": self._settings.oidc_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._settings.oidc_redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def _token_request(self, form: dict[str, str]) -> TokenSet:
        endpoint = (await self.metadata())["token_endpoint"]
        response = await self._http.post(
            endpoint,
            data={
                **form,
                "client_id": self._settings.oidc_client_id,
                "client_secret": self._settings.oidc_client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            raise OidcError(f"Token endpoint returned {response.status_code}")
        body = response.json()
        return TokenSet(
            access_token=body["access_token"],
            id_token=body.get("id_token"),
            refresh_token=body.get("refresh_token"),
            expires_at=time.time() + int(body.get("expires_in", 300)),
        )

    async def end_session_url(
        self, id_token_hint: str | None, post_logout_redirect: str
    ) -> str | None:
        endpoint = (await self.metadata()).get("end_session_endpoint")
        if not endpoint:
            return None
        params = {
            "client_id": self._settings.oidc_client_id,
            "post_logout_redirect_uri": post_logout_redirect,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"


@lru_cache
def get_oidc_client() -> OidcClient:
    """FastAPI dependency: process-wide OIDC client (caches discovery and signing keys)."""
    return OidcClient(get_settings())


def extract_roles(claims: dict[str, Any], dotted_path: str) -> frozenset[str]:
    """Read a roles array from a (possibly nested) claim, e.g. 'realm_access.roles'."""
    node: Any = claims
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return frozenset()
        node = node.get(part)
    if isinstance(node, list):
        return frozenset(str(role) for role in node)
    return frozenset()


def new_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for the S256 PKCE method."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
