"""
GET /v1/metrics/* — query API for Grafana and external consumers.

All endpoints return plain JSON that works with the Grafana JSON API datasource.
They can also be queried directly from your own code or dashboards.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ── Summary ────────────────────────────────────────────────────────────────────

@router.get(
    "/metrics/summary",
    summary="Aggregate metrics for all models",
    description="Returns request counts, latency percentiles, token usage, and cost per model.",
)
async def metrics_summary(
    window_hours: int = Query(24, description="Lookback window in hours"),
    env: str | None = Query(None, description="Filter by environment (production, staging, etc.)"),
    provider: str | None = Query(None, description="Filter by provider"),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    where = ["created_at >= :since"]
    params: dict = {"since": since}
    if env:
        where.append("env = :env")
        params["env"] = env
    if provider:
        where.append("provider = :provider")
        params["provider"] = provider
    where_clause = " AND ".join(where)

    rows = await db.execute(text(f"""
        SELECT
            provider,
            model,
            env,
            COUNT(*)                                                           AS requests,
            COUNT(*) FILTER (WHERE error IS NOT NULL)                          AS errors,
            ROUND(AVG(latency_ms)::numeric, 2)                                 AS avg_latency_ms,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY latency_ms)::numeric, 2) AS p50_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric, 2) AS p95_ms,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)::numeric, 2) AS p99_ms,
            SUM(prompt_tokens)                                                  AS prompt_tokens,
            SUM(completion_tokens)                                              AS completion_tokens,
            SUM(total_tokens)                                                   AS total_tokens,
            ROUND(SUM(cost_usd)::numeric, 6)                                   AS total_cost_usd,
            ROUND(
                COUNT(*) FILTER (WHERE error IS NOT NULL)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                                   AS error_rate
        FROM ai_events
        WHERE {where_clause}
        GROUP BY provider, model, env
        ORDER BY requests DESC
    """), params)

    models = []
    for r in rows:
        row = dict(r._mapping)
        for k, v in row.items():
            if hasattr(v, "__float__") and v is not None:
                row[k] = float(v)
        models.append(row)

    return {
        "window_hours": window_hours,
        "since": since.isoformat(),
        "total_requests": sum(m["requests"] for m in models),
        "total_cost_usd": round(sum((m.get("total_cost_usd") or 0) for m in models), 6),
        "models": models,
    }


# ── Timeseries ─────────────────────────────────────────────────────────────────

@router.get(
    "/metrics/timeseries",
    summary="Per-bucket time series for Grafana panels",
)
async def metrics_timeseries(
    model: str | None     = Query(None),
    provider: str | None  = Query(None),
    env: str | None       = Query(None),
    bucket: str           = Query("hour", description="minute | hour | day"),
    window_hours: int     = Query(24),
    db: AsyncSession      = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    trunc = {"minute": "minute", "hour": "hour", "day": "day"}.get(bucket, "hour")

    where = ["created_at >= :since"]
    params: dict = {"since": since}
    if model:
        where.append("model = :model")
        params["model"] = model
    if provider:
        where.append("provider = :provider")
        params["provider"] = provider
    if env:
        where.append("env = :env")
        params["env"] = env
    where_clause = " AND ".join(where)

    rows = await db.execute(text(f"""
        SELECT
            DATE_TRUNC('{trunc}', created_at)              AS bucket,
            COUNT(*)                                        AS requests,
            ROUND(AVG(latency_ms)::numeric, 2)             AS avg_latency_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric, 2) AS p95_ms,
            SUM(total_tokens)                               AS total_tokens,
            ROUND(SUM(cost_usd)::numeric, 8)               AS total_cost_usd,
            COUNT(*) FILTER (WHERE error IS NOT NULL)       AS errors
        FROM ai_events
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 1
    """), params)

    return {
        "bucket_size": trunc,
        "series": [
            {
                "bucket":          str(r.bucket),
                "requests":        r.requests,
                "avg_latency_ms":  float(r.avg_latency_ms or 0),
                "p95_ms":          float(r.p95_ms or 0),
                "total_tokens":    r.total_tokens or 0,
                "total_cost_usd":  float(r.total_cost_usd or 0),
                "errors":          r.errors,
            }
            for r in rows
        ],
    }


# ── Accuracy ───────────────────────────────────────────────────────────────────

@router.get(
    "/metrics/accuracy",
    summary="Accuracy score distribution and drift trend",
)
async def metrics_accuracy(
    window_hours: int    = Query(168, description="Default 7 days"),
    env: str | None      = Query(None),
    db: AsyncSession     = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    where = ["created_at >= :since"]
    params: dict = {"since": since}
    if env:
        where.append("env = :env")
        params["env"] = env
    where_clause = " AND ".join(where)

    # Daily trend
    trend_rows = await db.execute(text(f"""
        SELECT
            DATE_TRUNC('day', created_at)       AS day,
            ROUND(AVG(score)::numeric, 4)        AS avg_score,
            ROUND(MIN(score)::numeric, 4)        AS min_score,
            ROUND(MAX(score)::numeric, 4)        AS max_score,
            COUNT(*)                             AS count,
            label
        FROM ai_scores
        WHERE {where_clause}
        GROUP BY 1, label
        ORDER BY 1
    """), params)

    # Overall distribution buckets
    dist_rows = await db.execute(text(f"""
        SELECT
            CASE
                WHEN score < 0.2 THEN '0.0–0.2'
                WHEN score < 0.4 THEN '0.2–0.4'
                WHEN score < 0.6 THEN '0.4–0.6'
                WHEN score < 0.8 THEN '0.6–0.8'
                ELSE '0.8–1.0'
            END AS bucket,
            COUNT(*) AS count
        FROM ai_scores
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 1
    """), params)

    return {
        "window_hours": window_hours,
        "trend": [
            {
                "day":       str(r.day),
                "avg_score": float(r.avg_score),
                "min_score": float(r.min_score),
                "max_score": float(r.max_score),
                "count":     r.count,
                "label":     r.label,
            }
            for r in trend_rows
        ],
        "distribution": [
            {"bucket": r.bucket, "count": r.count}
            for r in dist_rows
        ],
    }


# ── Cost breakdown ─────────────────────────────────────────────────────────────

@router.get(
    "/metrics/cost",
    summary="Cost breakdown by model and provider",
)
async def metrics_cost(
    window_hours: int = Query(720, description="Default 30 days"),
    db: AsyncSession  = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    rows = await db.execute(text("""
        SELECT
            provider,
            model,
            ROUND(SUM(cost_usd)::numeric, 6)     AS total_cost_usd,
            SUM(total_tokens)                     AS total_tokens,
            COUNT(*)                              AS requests,
            ROUND(AVG(cost_usd)::numeric, 8)      AS avg_cost_per_request
        FROM ai_events
        WHERE created_at >= :since AND cost_usd IS NOT NULL
        GROUP BY provider, model
        ORDER BY total_cost_usd DESC
    """), {"since": since})

    items = [dict(r._mapping) for r in rows]
    for item in items:
        for k, v in item.items():
            if hasattr(v, "__float__") and v is not None:
                item[k] = float(v)

    return {
        "window_hours": window_hours,
        "grand_total_usd": round(sum(i.get("total_cost_usd") or 0 for i in items), 6),
        "breakdown": items,
    }


# ── Real-time (Redis) ──────────────────────────────────────────────────────────

@router.get(
    "/metrics/realtime",
    summary="Live request counters from Redis (last 60 minutes)",
)
async def metrics_realtime():
    redis = await _get_redis()
    req_keys = await redis.keys("req:*")

    buckets: dict[str, int] = {}
    for key in req_keys:
        val = await redis.get(key)
        buckets[key] = int(val or 0)

    # Cumulative totals
    tok_keys = await redis.keys("tok:*")
    token_totals: dict[str, int] = {}
    for key in tok_keys:
        val = await redis.get(key)
        token_totals[key.replace("tok:", "")] = int(val or 0)

    cost_keys = await redis.keys("cost:*")
    cost_totals: dict[str, float] = {}
    for key in cost_keys:
        val = await redis.get(key)
        cost_totals[key.replace("cost:", "")] = float(val or 0)

    return {
        "realtime_request_buckets": buckets,
        "cumulative_tokens_by_model": token_totals,
        "cumulative_cost_by_model":   cost_totals,
    }


# ── Provider list (useful for Grafana template variables) ─────────────────────

@router.get("/metrics/providers", summary="List all observed providers and models")
async def metrics_providers(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT DISTINCT provider, model
        FROM ai_events
        ORDER BY provider, model
    """))
    return {
        "providers": list({r.provider for r in rows}),
    }


@router.get("/metrics/models", summary="List all observed models")
async def metrics_models(
    provider: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    where = "WHERE provider = :provider" if provider else ""
    params = {"provider": provider} if provider else {}
    rows = await db.execute(text(f"SELECT DISTINCT model FROM ai_events {where} ORDER BY model"), params)
    return {"models": [r.model for r in rows]}
