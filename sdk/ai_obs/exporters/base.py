"""
Base class for all ai-obs exporters.

Implement ``export()`` to forward events to any backend.
The method is called synchronously inside the flush thread — keep it fast
or spawn your own thread inside ``export()`` for slow I/O.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseExporter(ABC):
    """
    Abstract base for all exporters.

    Subclass this and implement :meth:`export` to forward ai-obs events
    to any external system — Datadog, ClickHouse, Slack, S3, etc.

    Example::

        class PrintExporter(BaseExporter):
            def export(self, events: list[dict]) -> None:
                for event in events:
                    print(event)
    """

    @abstractmethod
    def export(self, events: list[dict[str, Any]]) -> None:
        """
        Receive a batch of event dicts and forward them somewhere.

        Each event dict contains:
            trace_id, model, provider, endpoint, env,
            latency_ms, prompt_tokens, completion_tokens, total_tokens,
            cost_usd, error, tags, timestamp_utc

        Args:
            events: List of event dicts (may be 1 to ``batch_size`` items).
        """

    def close(self) -> None:
        """Called on process exit. Override to flush buffers or close connections."""
