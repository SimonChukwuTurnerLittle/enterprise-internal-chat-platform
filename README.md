# Enterprise Chat Platform

One AI assistant for every internal application. Employees use it as a standalone web app or as a widget embedded in business apps. It answers from approved company knowledge with sources, and only from content they are allowed to see.

**Status: milestone 1 (foundation + RAG).** Live business-data tools via an agent and MCP connectors arrive in milestone 2. See [docs/architecture.md](docs/architecture.md#milestones).

## What's in milestone 1

- Company SSO (OIDC; Keycloak for development, Microsoft Entra ID in production) with tokens kept server-side
- Chat UI with streamed answers, citations and conversation history
- Embeddable `<enterprise-chat>` widget for any web app (React, Angular, Vue, ASP.NET, plain HTML)
- Knowledge ingestion (Markdown, text, PDF) with role-based access per source, enforced inside the vector search
- "Couldn't find it" fallback instead of guesses when no permitted source matches
- Audit log, rate limiting, problem+json errors, request ids
- Admin page for knowledge sources, documents and audit events
- Pluggable LLM: mock (no key needed), OpenAI, Azure OpenAI
- Docker Compose for local development and for self-hosted Coolify

## Quick start

Needs Docker Desktop, Node 22+ and [uv](https://docs.astral.sh/uv/).

```bash
docker compose -f deploy/docker-compose.yml up -d

cd services/api && cp .env.example .env && uv sync
uv run alembic upgrade head
uv run python -m app.cli seed --path ../../knowledge-seed
uv run uvicorn app.main:app --reload --port 8000

# second terminal, repo root
npm install && npm run dev
```

Open http://localhost:5173 and sign in as `alice` / `Passw0rd!`. The widget demo runs at http://localhost:8081. Full details are in [docs/dev-guide.md](docs/dev-guide.md).

## Documentation

| Document | For |
|---|---|
| [Architecture](docs/architecture.md) | Components, flows, data model, security controls, roadmap |
| [Decisions](docs/decisions.md) | Why these technologies and patterns, and the trade-offs |
| [API reference](docs/api.md) | Endpoints, SSE streaming contract, errors |
| [Widget integration](docs/widget-integration.md) | Teams embedding the assistant in their app |
| [Developer guide](docs/dev-guide.md) | Setup, tests, project layout, Python for Java developers |
| [Deployment](docs/deployment.md) | Coolify, environment variables, Entra ID setup |
