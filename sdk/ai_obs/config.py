"""
Configuration — all values are read from environment variables.
No YAML, no config files, no boilerplate.

Set once in your environment or .env file and every SDK call inherits them.
"""
from __future__ import annotations

import os


class Config:
    # ── Transport ──────────────────────────────────────────────────────────────
    endpoint: str        = os.getenv("AI_OBS_ENDPOINT", "http://localhost:8080")
    api_key: str | None  = os.getenv("AI_OBS_API_KEY")
    timeout: float       = float(os.getenv("AI_OBS_TIMEOUT", "5"))

    # ── Batching ───────────────────────────────────────────────────────────────
    batch_size: int      = int(os.getenv("AI_OBS_BATCH_SIZE", "50"))
    flush_interval: float = float(os.getenv("AI_OBS_FLUSH_INTERVAL", "5"))

    # ── Behaviour ──────────────────────────────────────────────────────────────
    env: str             = os.getenv("AI_OBS_ENV", "production")
    disabled: bool       = os.getenv("AI_OBS_DISABLE", "false").lower() == "true"

    # ── Sampling — 1.0 = capture everything, 0.1 = capture 10% ───────────────
    sample_rate: float   = float(os.getenv("AI_OBS_SAMPLE_RATE", "1.0"))

    # ── Privacy — off by default, opt-in ──────────────────────────────────────
    # WARNING: enabling these stores raw prompts/completions in your database.
    # Make sure your database is secured before enabling.
    capture_prompts: bool      = os.getenv("AI_OBS_CAPTURE_PROMPTS", "false").lower() == "true"
    capture_completions: bool  = os.getenv("AI_OBS_CAPTURE_COMPLETIONS", "false").lower() == "true"

    def __repr__(self) -> str:
        return (
            f"Config(endpoint={self.endpoint!r}, env={self.env!r}, "
            f"disabled={self.disabled}, sample_rate={self.sample_rate})"
        )


#: Global singleton — import and use directly, or override in tests via monkeypatch.
config = Config()
