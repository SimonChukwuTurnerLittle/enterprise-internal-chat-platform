import base64
import hashlib
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fakeredis.aioredis import FakeRedis

from app.modules.identity.oidc import OidcClient, OidcError, extract_roles, new_pkce_pair
from app.modules.identity.routes import is_safe_return_path
from tests.conftest import CLIENT_ID, FakeIdP


async def test_valid_token_is_accepted(oidc_client: OidcClient, idp: FakeIdP) -> None:
    claims = await oidc_client.validate(idp.token("alice", ["employee"]), audience=CLIENT_ID)
    assert claims["sub"] == "alice"
    assert extract_roles(claims, "realm_access.roles") == frozenset({"employee"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "some-other-api"},
        {"issuer": "https://evil.example/realms/enterprise"},
        {"expires_in": -3600},
    ],
)
async def test_invalid_claims_are_rejected(
    oidc_client: OidcClient, idp: FakeIdP, overrides: dict[str, Any]
) -> None:
    with pytest.raises(OidcError):
        await oidc_client.validate(idp.token("alice", **overrides), audience=CLIENT_ID)


async def test_token_signed_by_another_key_is_rejected(
    oidc_client: OidcClient, idp: FakeIdP
) -> None:
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OidcError):
        await oidc_client.validate(idp.token("alice", key=attacker_key), audience=CLIENT_ID)


async def test_unsigned_token_is_rejected(oidc_client: OidcClient) -> None:
    token = jwt.encode({"sub": "alice"}, key="", algorithm="none")
    with pytest.raises(OidcError, match="algorithm"):
        await oidc_client.validate(token, audience=CLIENT_ID)


async def test_nonce_must_match(oidc_client: OidcClient, idp: FakeIdP) -> None:
    with pytest.raises(OidcError, match="Nonce"):
        await oidc_client.validate(idp.token("alice", nonce="a"), audience=CLIENT_ID, nonce="b")


def test_extract_roles_handles_missing_and_flat_claims() -> None:
    assert extract_roles({}, "realm_access.roles") == frozenset()
    assert extract_roles({"roles": ["a", "b"]}, "roles") == frozenset({"a", "b"})
    assert extract_roles({"realm_access": "oops"}, "realm_access.roles") == frozenset()


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = new_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode()


@pytest.mark.parametrize(
    ("path", "safe"),
    [
        ("/", True),
        ("/c/123?x=1", True),
        ("//evil.example", False),
        ("https://evil.example", False),
        ("/\\evil.example", False),
        ("/ok\r\nSet-Cookie: x", False),
    ],
)
def test_return_path_validation(path: str, safe: bool) -> None:
    assert is_safe_return_path(path) is safe


async def test_login_redirects_to_idp_with_pkce(
    client: httpx.AsyncClient, fake_redis: FakeRedis
) -> None:
    response = await client.get("/api/auth/login", params={"return_to": "//evil.example"})
    assert response.status_code == 302
    location = httpx.URL(response.headers["location"])
    assert location.path.endswith("/protocol/openid-connect/auth")
    assert location.params["code_challenge_method"] == "S256"
    assert location.params["redirect_uri"] == "http://testserver/api/auth/callback"
    state = await fake_redis.get(f"oidc_state:{location.params['state']}")
    assert state is not None and '"return_to": "/"' in state


async def test_requests_without_credentials_get_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 401
