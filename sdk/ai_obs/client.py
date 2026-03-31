"""
HTTP client with background batching queue + exporter pipeline.

Events flow:
    enqueue() → in-memory queue → flush thread → POST to collector
                                              → registry.export_all() (plugins)
"""
from __future__ import annotations

import atexit
import json
import logging
import queue
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

import urllib.request
import urllib.error

from ai_obs.config import config

logger = logging.getLogger("ai_obs")


class ObsClient:
    """
    Thread-safe batching client.

    A single global instance is created at import time and shared across the
    entire process. Use :func:`get_client` to access it.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._lock = threading.Lock()
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="ai-obs-flusher"
        )
        self._flush_thread.start()
        atexit.register(self._drain_and_flush)

    # ── Public API ─────────────────────────────────────────────────────────────

    def enqueue(self, event: dict[str, Any]) -> None:
        """Add a single event to the outbound queue. Non-blocking."""
        if config.disabled:
            return

        # Sampling: skip this event if sample_rate < 1.0
        if config.sample_rate < 1.0 and random.random() > config.sample_rate:
            return

        # Always stamp with UTC time at enqueue
        event.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("ai-obs: event queue full — dropping event (increase AI_OBS_BATCH_SIZE or AI_OBS_FLUSH_INTERVAL)")

    def flush(self) -> None:
        """Flush pending events synchronously. Useful in tests and scripts."""
        events = self._drain_queue()
        if events:
            self._send(events)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        while True:
            time.sleep(config.flush_interval)
            events = self._drain_queue()
            if events:
                self._send(events)

    def _drain_queue(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            while len(events) < config.batch_size:
                events.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        return events

    def _drain_and_flush(self) -> None:
        """Called by atexit — drain everything remaining."""
        events = self._drain_queue()
        if events:
            self._send(events)

    def _send(self, events: list[dict[str, Any]]) -> None:
        # ── 1. Forward to the collector ───────────────────────────────────────
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["X-API-Key"] = config.api_key

        trace_events = [e for e in events if e.get("type", "trace") != "score"]
        score_events = [e for e in events if e.get("type") == "score"]

        if trace_events:
            self._post_json(
                f"{config.endpoint.rstrip('/')}/v1/events",
                {"events": trace_events},
                headers,
            )

        if score_events:
            scores_payload = {
                "scores": [
                    {
                        "trace_id": e["trace_id"],
                        "score": e["score"],
                        "label": e.get("label"),
                        "metadata": e.get("metadata", {}),
                        "env": e.get("env", config.env),
                    }
                    for e in score_events
                ]
            }
            self._post_json(
                f"{config.endpoint.rstrip('/')}/v1/scores",
                scores_payload,
                headers,
            )

        # ── 2. Forward to all registered plugin exporters ─────────────────────
        # Import here to avoid circular imports at module load time
        from ai_obs.registry import registry
        if len(registry) > 0:
            registry.export_all(events)

    def _post_json(self, url: str, payload_obj: dict[str, Any], headers: dict[str, str]) -> None:
        payload = json.dumps(payload_obj).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=config.timeout):
                pass
        except (urllib.error.URLError, OSError) as exc:
            logger.debug("ai-obs: collector unreachable (%s) — events still forwarded to exporters", exc)


# ── Global singleton ───────────────────────────────────────────────────────────

_client: ObsClient | None = None
_client_lock = threading.Lock()


def get_client() -> ObsClient:
    """Return the global ObsClient, creating it on first call."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ObsClient()
    return _client
