"""POST /v1/scores — ingest manual and auto accuracy scores."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIScore
from app.routers.events import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


class ScorePayload(BaseModel):
    trace_id: str
    score:    float   = Field(..., ge=0.0, le=1.0, description="Quality score 0.0–1.0")
    label:    str | None = Field(None, description="e.g. 'correct', 'hallucination', 'autoscore'")
    metadata: dict[str, Any] = Field(default_factory=dict)
    env:      str = "production"

    model_config = {"json_schema_extra": {
        "example": {
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "score": 0.95,
            "label": "correct",
            "env": "production",
        }
    }}


class BatchScorePayload(BaseModel):
    scores: list[ScorePayload]


@router.post(
    "/scores",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit accuracy scores for traces",
    description=(
        "Accepts manual scores (human review) or automated scores (LLM-as-judge). "
        "Scores are linked to traces via trace_id and power the Accuracy dashboard."
    ),
)
async def ingest_scores(
    payload: BatchScorePayload,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_api_key),
):
    db_objs = [
        AIScore(
            trace_id=s.trace_id,
            score=round(s.score, 6),
            label=s.label,
            metadata_=s.metadata,
            env=s.env,
        )
        for s in payload.scores
    ]
    db.add_all(db_objs)
    await db.commit()
    logger.info("stored %d scores", len(db_objs))
    return {"accepted": len(db_objs)}


# Convenience: single-score endpoint (no wrapper object needed)
@router.post(
    "/score",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a single accuracy score",
    include_in_schema=True,
)
async def ingest_single_score(
    payload: ScorePayload,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_api_key),
):
    db.add(AIScore(
        trace_id=payload.trace_id,
        score=round(payload.score, 6),
        label=payload.label,
        metadata_=payload.metadata,
        env=payload.env,
    ))
    await db.commit()
    return {"accepted": 1}
