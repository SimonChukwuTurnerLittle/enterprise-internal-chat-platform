# Developer guide

## Prerequisites

- Docker Desktop (PostgreSQL, Redis, Keycloak run in containers)
- Node.js 22+ (the frontend uses npm workspaces)
- [uv](https://docs.astral.sh/uv/) for Python. It installs Python 3.12 itself:
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows) or `pip install uv`
- Optional: an OpenAI API key. Without one, the **mock LLM** answers by quoting the best source.

## First run

```bash
# 1. Infrastructure: Postgres+pgvector :5432, Redis :6379, Keycloak :8180, demo host page :8081
docker compose -f deploy/docker-compose.yml up -d

# 2. API (terminal 1)
cd services/api
cp .env.example .env            # defaults work with the compose stack
uv sync                         # creates .venv and installs dependencies (+ uv.lock)
uv run alembic upgrade head     # create tables
uv run python -m app.cli seed --path ../../knowledge-seed
uv run uvicorn app.main:app --reload --port 8000

# 3. Web (terminal 2, repo root)
npm install                     # creates package-lock.json
npm run dev                     # builds the widget, starts Vite on :5173
```

Open http://localhost:5173 and sign in:

| User | Password | Roles | Try |
|---|---|---|---|
| `alice` | `Passw0rd!` | employee | "How many days of annual leave do I get?" |
| `bob` | `Passw0rd!` | employee, hr | "What is salary band C?" (sees manager guidance) |
| `carol` | `Passw0rd!` | employee, manager, chat-admin | Admin page: upload documents, view audit |

Ask alice "What is salary band C?" and she gets the "couldn't find" answer, because that document is restricted to managers and HR. That is the permission filter working.

**Widget:** open http://localhost:8081, the demo "HR Portal" page, and click the launcher at the bottom right.

**Full stack in containers** (as deployed): `docker compose -f deploy/docker-compose.yml --profile app up -d --build`, then http://localhost:8080. Seed it with `docker compose -f deploy/docker-compose.yml exec api python -m app.cli seed --path /seed`. The demo host for this stack is http://localhost:8081/?chat=http://localhost:8080.

**Real LLM:** set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in `services/api/.env`, then **re-seed**, because the embeddings differ from the mock's. To re-embed cleanly, delete the documents in the Admin page or reset the database (`docker compose -f deploy/docker-compose.yml down -v`).

## Tests and checks

```bash
cd services/api
uv run pytest            # unit tests always; DB tests need the compose Postgres (chat_test database)
uv run ruff check .
uv run mypy app

cd ../..                 # repo root
npm test                 # widget SDK + web unit tests (Vitest)
npm run typecheck
```

DB-backed tests skip themselves with a clear message if PostgreSQL is not reachable. They use the `chat_test` database, which the compose stack creates on first start.

## Project layout

```
apps/web/             React + Vite SPA: /, /c/:id, /admin, /embed (widget iframe)
packages/widget-sdk/  <enterprise-chat> custom element + postMessage protocol
services/api/         FastAPI modular monolith (app/modules/*), Alembic migrations, tests
knowledge-seed/       Sample (fictional) policies and IT articles + manifest.yaml
infra/keycloak/       Development realm: client, roles, test users
deploy/               docker-compose (dev) and docker-compose.coolify.yml (prod)
sample-apps/demo-host Static "business app" page that embeds the widget
docs/                 Architecture, decisions, API, widget integration, deployment
```

## Adding a database change

```bash
cd services/api
uv run alembic revision -m "add something"   # write upgrade()/downgrade() by hand, or use --autogenerate
uv run alembic upgrade head
```

## Python for Java developers

| Java / Spring | This codebase |
|---|---|
| Maven/Gradle + `pom.xml` | `uv` + `pyproject.toml`; `uv.lock` is the lockfile |
| Spring Boot app | `app/main.py` → `create_app()` returns a FastAPI app |
| `@RestController` + `@GetMapping` | `router = APIRouter(...)` + `@router.get("/path")` |
| DTO + Bean Validation | Pydantic `BaseModel` with `Field(max_length=…)`; invalid input → 422 automatically |
| `@Autowired` / constructor injection | `Depends(...)` parameters, e.g. `db: AsyncSession = Depends(get_db)` |
| Spring Security filter + `@AuthenticationPrincipal` | `principal: Principal = Depends(get_principal)` |
| `@PreAuthorize("hasRole('ADMIN')")` | `Depends(require_admin)` |
| JPA entity / `EntityManager` | SQLAlchemy 2 model (`Mapped[...]`) / `AsyncSession` |
| Flyway / Liquibase | Alembic (`migrations/versions/*.py`) |
| `application.yml` + `@ConfigurationProperties` | `app/core/config.py` (`Settings`, read from env vars / `.env`) |
| Interface + multiple `@Component`s | `typing.Protocol` + classes, chosen in a factory (`llm/factory.py`) |
| `CompletableFuture` / WebFlux | `async def` + `await`; streaming via async generators (`yield`) |
| JUnit + Mockito + Testcontainers | pytest + fixtures (`tests/conftest.py`) + fakes (FakeIdP, fakeredis) |
| `@ControllerAdvice` | `app/core/errors.py` exception handlers (problem+json) |

Conventions: type hints everywhere (mypy checks them), `ruff` for lint and import order, no business logic in route functions beyond orchestration, and every admin or data-access action goes through `record_audit`.
