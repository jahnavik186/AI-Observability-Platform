"""GET /v1/health — liveness + readiness probes."""
from __future__ import annotations
import os
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

router = APIRouter()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@router.get("/health", summary="Liveness probe")
async def health():
    return {"status": "ok", "service": "ai-obs-collector"}


@router.get("/health/ready", summary="Readiness probe — checks all dependencies")
async def readiness(db: AsyncSession = Depends(get_db)):
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
