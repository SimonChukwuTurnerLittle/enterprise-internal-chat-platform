# Architecture decisions

Short records of the main decisions and their trade-offs. Add a new entry rather than editing an accepted one; mark superseded entries.

## ADR-001: Modular monolith

**Decision:** one deployable API with strict internal modules (`identity`, `knowledge`, `chat`, …).
**Why:** one team, early product, shared transactions (message + audit in one commit), simple operations on a single Coolify server.
**Trade-off:** modules cannot scale independently. Revisit if ingestion or the agent needs separate scaling; module boundaries make extraction straightforward.

## ADR-002: Python, FastAPI and (from M2) LangGraph

**Decision:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic; LangGraph for agent orchestration in M2.
**Why:** the most mature ecosystem for LLM, RAG, MCP and evaluation tooling; FastAPI gives typed request models and OpenAPI docs for free. The team chose it partly to build Python/AI skills.
**Trade-off:** the team's strongest language is Java. Mitigated by strict typing (mypy), a small set of libraries, and the Python-for-Java guide in [dev-guide.md](dev-guide.md). Spring Boot + Spring AI was the main alternative.

## ADR-003: Hybrid MCP + REST connectors (M2)

**Decision:** MCP is the preferred way for an application to expose AI tools; a declarative REST manifest covers applications that cannot host an MCP server.
**Why:** MCP standardises tool discovery and schemas, so new apps can be onboarded without platform code changes; REST manifests avoid blocking on legacy apps.
**Trade-off:** two connector implementations to maintain. Both hide behind one interface, and authorisation stays in the platform and the app, not in the protocol.

## ADR-004: pgvector instead of a managed search service

**Decision:** store embeddings in PostgreSQL with pgvector (HNSW index).
**Why:** self-hosted on Coolify, one database to operate and back up, and ACL filters are ordinary SQL in the same query as the vector search.
**Trade-off:** no built-in hybrid keyword + vector ranking or semantic re-ranking. Revisit (e.g. add PostgreSQL full-text search, or a dedicated engine) if retrieval quality or corpus size demands it.

## ADR-005: Widget = Web Component + sandboxed iframe

**Decision:** a tiny script defines `<enterprise-chat>`; the chat UI runs in an iframe from the platform origin; host and iframe exchange context over `postMessage`.
**Why:** works in React, Angular, Vue, ASP.NET and plain HTML without per-framework builds; the chat's session, CSS and release cycle stay isolated from host apps.
**Trade-off:** cookies inside the iframe are third-party unless the chat runs on the same site as the hosts (recommended: `chat.example.com` next to `hr.example.com`). Otherwise sign-in falls back to a popup and browsers' third-party cookie rules apply.

## ADR-006: Backend-for-frontend auth in the API; React + Vite SPA

**Decision:** the FastAPI service performs the OIDC code flow and stores tokens in Redis; the browser holds only an httpOnly session cookie. The frontend is a static React + Vite SPA served from the same origin.
**Why:** current OAuth guidance for browser apps recommends keeping tokens out of JavaScript; one security boundary (the API) instead of two; no Node server to run in production.
**Trade-off:** replaces the originally suggested Next.js. Server-side rendering is not needed for an authenticated chat UI; Next.js can still be adopted later without changing the API.

## ADR-007: Pluggable LLM provider with a mock

**Decision:** `LLM_PROVIDER=mock|openai|azure_openai`, chosen at deploy time.
**Why:** start with the OpenAI API; move to Azure OpenAI when enterprise data-residency and compliance terms are required; run tests and local development with no key and no cost.
**Trade-off:** the mock is keyword-based, so retrieval quality in development differs from production. Real-model checks belong in an evaluation set (planned).

## ADR-008: Docker Compose on self-hosted Coolify

**Decision:** two images (`api`, `web`) plus PostgreSQL and Redis, deployed as a Compose stack on Coolify.
**Why:** the organisation self-hosts on Coolify; Compose keeps local and production topologies identical.
**Trade-off:** no automatic horizontal scaling. The API is stateless (state in PostgreSQL/Redis), so more replicas can be added behind Coolify's proxy when needed.
