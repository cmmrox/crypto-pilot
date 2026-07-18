"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, events, health, market, ops, settings_api, strategies_api
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    log = get_logger("app")
    log.info("app_starting", version=settings.version, environment=settings.environment)

    from app.bot.ingest import ingest_service

    if settings.environment != "test":
        await ingest_service.start()

    yield

    if settings.environment != "test":
        await ingest_service.stop()
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
    return app


app = create_app()
