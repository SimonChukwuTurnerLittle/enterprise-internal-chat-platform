from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CLIENT_SECRET = "dev-chat-platform-secret"  # noqa: S105 - matches infra/keycloak realm export


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+asyncpg://chat:chat@localhost:5432/chat"
    database_pool_disabled: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # Browser-facing origin of the chat web app. The API is served under {public_base_url}/api.
    public_base_url: str = "http://localhost:5173"

    # --- OIDC: Keycloak in dev, Microsoft Entra ID (or any OIDC provider) in prod ---
    oidc_issuer: str = "http://localhost:8180/realms/enterprise"
    # Issuer URL as reachable from the API process, when it differs from the public issuer
    # (e.g. http://keycloak:8080/realms/enterprise inside docker compose).
    oidc_internal_base_url: str | None = None
    oidc_client_id: str = "chat-platform"
    oidc_client_secret: SecretStr = SecretStr(DEV_CLIENT_SECRET)
    oidc_audience: str = "chat-platform"
    oidc_scopes: str = "openid profile email"
    # Dotted path to the roles array in the access token.
    # Keycloak: realm_access.roles; Entra ID: roles.
    oidc_roles_claim: str = "realm_access.roles"
    oidc_clock_skew_seconds: int = 30

    session_cookie_name: str = "ecp_session"
    session_ttl_seconds: int = 8 * 3600
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    admin_role: str = "chat-admin"

    # --- LLM ---
    llm_provider: Literal["mock", "openai", "azure_openai"] = "mock"
    llm_temperature: float = 0.1
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None

    # --- RAG & chat ---
    organisation_name: str = "your organisation"
    rag_top_k: int = 5
    rag_min_score: float | None = None
    history_messages: int = 10
    max_message_chars: int = 4000
    rate_limit_messages_per_minute: int = 20
    max_upload_bytes: int = 10 * 1024 * 1024

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.environment == "prod":
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in prod")
            if self.oidc_client_secret.get_secret_value() == DEV_CLIENT_SECRET:
                raise ValueError("OIDC_CLIENT_SECRET must be set in prod")
            if self.llm_provider == "mock":
                raise ValueError("LLM_PROVIDER=mock is not allowed in prod")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")
        return self

    @property
    def oidc_discovery_endpoint(self) -> str:
        base = (self.oidc_internal_base_url or self.oidc_issuer).rstrip("/")
        return f"{base}/.well-known/openid-configuration"

    @property
    def oidc_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/auth/callback"

    @property
    def effective_rag_min_score(self) -> float:
        """Cosine-similarity cut-off below which retrieved chunks are treated as irrelevant."""
        if self.rag_min_score is not None:
            return self.rag_min_score
        # The mock embedder is a bag-of-words hash, so its scores run lower than real embeddings.
        return 0.12 if self.llm_provider == "mock" else 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()
