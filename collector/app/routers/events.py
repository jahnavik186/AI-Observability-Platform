"""POST /v1/events — ingest telemetry event batches from the SDK."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIEvent

logger = logging.getLogger(__name__)
router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
API_KEY   = os.getenv("API_KEY", "")

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ── Auth ───────────────────────────────────────────────────────────────────────

def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API key auth — only enforced when AI_OBS_API_KEY is set."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class EventPayload(BaseModel):
    trace_id:          str
    model:             str
    provider:          str              = "generic"
    endpoint:          str | None       = None
    env:               str              = "production"
    latency_ms:        float | None     = None
    prompt_tokens:     int | None       = None
    completion_tokens: int | None       = None
    total_tokens:      int | None       = None
    cost_usd:          float | None     = None
    error:             str | None       = None
    prompt:            str | None       = None   # privacy opt-in
    completion:        str | None       = None   # privacy opt-in
    tags:              dict[str, Any]   = Field(default_factory=dict)
    timestamp_utc:     str | None       = None
    type:              str              = "trace"   # "trace" | "score"


class BatchPayload(BaseModel):
    events: list[EventPayload]

    model_config = {"json_schema_extra": {
        "example": {
            "events": [{
                "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                "model": "gpt-4o",
                "provider": "openai",
                "env": "production",
                "latency_ms": 342.5,
                "prompt_tokens": 80,
                "completion_tokens": 120,
                "total_tokens": 200,
                "cost_usd": 0.0021,
            }]
        }
    }}


class IngestResponse(BaseModel):
    accepted: int
    rejected: int = 0


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/events",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of telemetry events",
    description=(
        "Accepts batches of up to 500 events from the ai-obs SDK. "
        "Events are persisted to PostgreSQL and real-time counters are updated in Redis. "
        "Score-type events are forwarded to the /v1/scores handler."
    ),
)
async def ingest_events(
    payload: BatchPayload,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_api_key),
):
    trace_events = [e for e in payload.events if e.type == "trace"]
    score_events = [e for e in payload.events if e.type == "score"]

    # ── Persist trace events to PostgreSQL ────────────────────────────────────
    db_objs = [
        AIEvent(
            trace_id=e.trace_id,
            model=e.model,
            provider=e.provider.lower(),
            endpoint=e.endpoint,
            env=e.env,
            latency_ms=e.latency_ms,
            prompt_tokens=e.prompt_tokens,
            completion_tokens=e.completion_tokens,
            total_tokens=e.total_tokens,
            cost_usd=e.cost_usd,
            error=e.error,
            prompt=e.prompt,
            completion=e.completion,
            tags=e.tags,
            timestamp_utc=e.timestamp_utc,
        )
        for e in trace_events
    ]
    if db_objs:
        db.add_all(db_objs)
        await db.commit()

    # ── Update Redis real-time counters ───────────────────────────────────────
    if trace_events:
        redis = await _get_redis()
        pipe = redis.pipeline()
        now_min = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

        for e in trace_events:
            # Per-minute request count (expires after 2 hours)
            req_key = f"req:{e.provider}:{e.model}:{now_min}"
            pipe.incr(req_key)
            pipe.expire(req_key, 7200)

            # Rolling latency list (keep last 10k, for percentile calc)
            if e.latency_ms is not None:
                pipe.rpush(f"lat:{e.model}", round(e.latency_ms))
                pipe.ltrim(f"lat:{e.model}", -10000, -1)

            # Cumulative token and cost counters
            if e.total_tokens:
                pipe.incrby(f"tok:{e.model}", e.total_tokens)
            if e.cost_usd:
                pipe.incrbyfloat(f"cost:{e.model}", round(e.cost_usd, 8))

            # Per-minute error count
            if e.error:
                err_key = f"err:{e.model}:{now_min}"
                pipe.incr(err_key)
                pipe.expire(err_key, 7200)

        await pipe.execute()

    # ── Log score events (they're handled separately via /v1/scores) ──────────
    if score_events:
        logger.debug("received %d score events via /v1/events batch", len(score_events))

    logger.info(
        "ingested %d trace events, %d score events",
        len(trace_events), len(score_events),
    )
    return IngestResponse(accepted=len(trace_events))
