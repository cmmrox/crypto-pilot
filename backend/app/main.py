"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_settings,
    auth,
    bot,
    events,
    health,
    market,
    monthly,
    news,
    ops,
    overview,
    settings_api,
    strategies_api,
    trades,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    log = get_logger("app")
    import os

    os.environ.setdefault("CODEX_HOME", settings.codex_home)
    log.info("app_starting", version=settings.version, environment=settings.environment)

    # Alembic adds the encrypted key column without receiving CP_MASTER_KEY.
    # Clear every legacy plaintext key before the server accepts requests.
    from app.db.session import get_sessionmaker
    from app.services.credentials import migrate_plaintext_keys

    async with get_sessionmaker()() as session:
        migrated_keys = await migrate_plaintext_keys(session)
        await session.commit()
    if migrated_keys:
        log.info("legacy_api_keys_encrypted", count=migrated_keys)

    from app.bot.ingest import ingest_service

    if settings.environment != "test":
        await ingest_service.start()
        from app.news.scheduler import news_scheduler
        await news_scheduler.start()

    yield

    if settings.environment != "test":
        await ingest_service.stop()
        from app.news.scheduler import news_scheduler
        await news_scheduler.stop()
    from app.db.session import dispose_engine

    await dispose_engine()
    log.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )
    from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(events.router)
    app.include_router(market.router)
    app.include_router(settings_api.router)
    app.include_router(strategies_api.router)
    app.include_router(ops.router)
    app.include_router(bot.router)
    app.include_router(overview.router)
    app.include_router(trades.router)
    app.include_router(monthly.router)
    app.include_router(news.router)
    app.include_router(news.codex_router)
    app.include_router(admin_settings.router)
    return app


app = create_app()
