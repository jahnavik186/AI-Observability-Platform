"""
ai-obs Collector — FastAPI application.

Endpoints:
    POST /v1/events     — ingest telemetry batches from the SDK
    POST /v1/scores     — ingest accuracy scores
    GET  /v1/metrics/*  — query API for Grafana and other consumers
    GET  /v1/health     — liveness probe
    GET  /v1/health/ready — readiness probe (checks Postgres + Redis)
    GET  /docs          — interactive API docs (Swagger UI)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import events, scores, metrics, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ai-obs Collector",
    description=(
        "Telemetry collector for the ai-obs AI observability platform. "
        "Accepts events from the ai-obs-sdk and exposes metrics for Grafana."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "ai-obs", "url": "https://github.com/your-org/ai-obs"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("ai-obs collector ready")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await engine.dispose()
    logger.info("ai-obs collector shutdown")


app.include_router(health.router,   prefix="/v1", tags=["health"])
app.include_router(events.router,   prefix="/v1", tags=["events"])
app.include_router(scores.router,   prefix="/v1", tags=["scores"])
app.include_router(metrics.router,  prefix="/v1", tags=["metrics"])


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "ai-obs-collector", "version": "0.2.0", "docs": "/docs"}
