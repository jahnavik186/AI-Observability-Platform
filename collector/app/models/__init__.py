from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class AIEvent(Base):
    """One instrumented LLM call, captured by the SDK decorator."""
    __tablename__ = "ai_events"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id          = Column(String(64),  nullable=False, index=True)
    model             = Column(String(128), nullable=False, index=True)
    provider          = Column(String(64),  nullable=False, index=True)
    endpoint          = Column(String(256))
    env               = Column(String(64),  default="production")
    latency_ms        = Column(Float)
    prompt_tokens     = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens      = Column(Integer)
    cost_usd          = Column(Float)
    error             = Column(String(2048))
    # Optional (privacy opt-in)
    prompt            = Column(String(4096))
    completion        = Column(String(4096))
    tags              = Column(JSON, default=dict)
    timestamp_utc     = Column(String(32))
    created_at        = Column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("ix_ai_events_created_model",   "created_at", "model"),
        Index("ix_ai_events_provider_env",    "provider", "env"),
        Index("ix_ai_events_model_provider",  "model", "provider"),
    )


class AIScore(Base):
    """Accuracy / quality score attached to a trace."""
    __tablename__ = "ai_scores"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id   = Column(String(64), nullable=False, index=True)
    score      = Column(Float, nullable=False)   # 0.0 – 1.0
    label      = Column(String(128), index=True)
    metadata_  = Column("metadata", JSON, default=dict)
    env        = Column(String(64), default="production")
    created_at = Column(DateTime(timezone=True), default=_now, index=True)
