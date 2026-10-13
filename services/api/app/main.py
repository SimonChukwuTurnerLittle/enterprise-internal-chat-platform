from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.redis import get_redis
from app.modules.audit.routes import router as audit_router
from app.modules.chat.routes import router as chat_router
from app.modules.conversations.routes import router as conversations_router
from app.modules.identity.routes import router as auth_router
from app.modules.knowledge.routes import router as knowledge_router
from app.modules.registry.routes import router as registry_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()
    await get_redis().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    app = FastAPI(
        title="Enterprise Chat Platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "prod" else None,
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    for router in (
        auth_router,
        registry_router,
        conversations_router,
        chat_router,
        knowledge_router,
        audit_router,
    ):
        app.include_router(router)

    @app.get("/api/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/readyz", tags=["ops"])
    async def readyz() -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(checks, status_code=200 if ready else 503)

    return app


app = create_app()
