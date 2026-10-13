# Deployment (Coolify)

The production stack is [`deploy/docker-compose.coolify.yml`](../deploy/docker-compose.coolify.yml): `web` (Caddy: SPA, widget script, `/api` proxy), `api` (FastAPI, runs migrations on start), PostgreSQL with pgvector, and Redis.

## Steps

1. In Coolify, create a resource from this Git repository with the **Docker Compose** build pack and compose file `deploy/docker-compose.coolify.yml`.
2. Give the `web` service its domain, e.g. `https://chat.example.com` (port 80). Coolify's proxy terminates TLS. No other service needs a public domain.
3. Set environment variables (below) in Coolify.
4. Deploy. Check `https://chat.example.com/api/readyz` returns `{"database":"ok","redis":"ok"}`.
5. Load knowledge: upload documents in **Admin**, or run `python -m app.cli seed --path /seed` in the `api` container terminal for the sample set.

**Hosting tip:** put the chat on the same parent domain as the business apps (`chat.example.com` next to `hr.example.com`). The widget then reuses the employee's session without a sign-in popup.

## Environment variables

| Variable | Example | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | long random | Used by `postgres` and `api` |
| `PUBLIC_BASE_URL` | `https://chat.example.com` | Must match the domain; the OIDC redirect is `{PUBLIC_BASE_URL}/api/auth/callback` |
| `OIDC_ISSUER` | `https://login.microsoftonline.com/<tenant-id>/v2.0` | Exact `iss` claim of tokens |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | from the app registration | Secret stays in Coolify |
| `OIDC_AUDIENCE` | `api://<client-id>` or `<client-id>` | Must equal the access token `aud` |
| `OIDC_SCOPES` | `openid profile email offline_access api://<client-id>/access_as_user` | `offline_access` enables refresh |
| `OIDC_ROLES_CLAIM` | `roles` | Keycloak: `realm_access.roles` |
| `ADMIN_ROLE` | `chat-admin` | App role that unlocks the Admin page |
| `LLM_PROVIDER` | `azure_openai` or `openai` | `mock` is refused in prod |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | | When using Azure OpenAI. The embedding deployment must output 1536 dimensions (e.g. `text-embedding-3-small`) |
| `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` | | When using the OpenAI API |
| `FRAME_ANCESTORS` | `https://hr.example.com https://finance.example.com` | Origins allowed to embed the widget (also register them on the application) |
| `ORGANISATION_NAME` | `Example Corp` | Used in the assistant's instructions |

The API refuses to start in prod with insecure settings (non-secure cookies, default client secret, mock LLM).

## Microsoft Entra ID setup

1. **App registrations → New registration**: name "Enterprise Chat", single tenant, redirect URI (Web) `https://chat.example.com/api/auth/callback`.
2. **Certificates & secrets**: create a client secret → `OIDC_CLIENT_SECRET`.
3. **Expose an API**: set the Application ID URI (`api://<client-id>`) and add the scope `access_as_user`.
4. **Manifest**: set `"requestedAccessTokenVersion": 2` so access tokens use the v2 issuer above. With v2 tokens, `aud` is the client id, so set `OIDC_AUDIENCE=<client-id>`.
5. **App roles**: create `employee`, `manager`, `hr`, `chat-admin` and assign them to groups in **Enterprise applications → Users and groups**. They arrive in the `roles` claim.
6. **Token configuration**: add the optional claim `email`.

Knowledge source `acl_roles` must use the same role values.

## Operations

- **Backups:** back up the `pgdata` volume (conversations, knowledge, audit). Redis holds only sessions and can be lost; users simply sign in again.
- **Logs:** the API writes JSON lines to stdout with `request_id`; view them in Coolify.
- **Upgrades:** redeploy; the API runs `alembic upgrade head` before starting.
- **Changing the embedding model:** re-ingest all documents. A model with different dimensions also needs a migration of `chunks.embedding`.
