"""
Plugin exporter registry.

Any number of exporters can be registered. Every flushed batch of events
is forwarded to all registered exporters *in addition* to the collector.

Usage::

    from ai_obs import registry
    from ai_obs.exporters import WebhookExporter, S3Exporter

    registry.register(WebhookExporter(url="https://hooks.slack.com/..."))
    registry.register(S3Exporter(bucket="my-ai-logs"))

Writing a custom exporter::

    from ai_obs.exporters import BaseExporter

    class MyExporter(BaseExporter):
        def export(self, events: list[dict]) -> None:
            for e in events:
                my_system.ingest(e)

    registry.register(MyExporter())
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_obs.exporters.base import BaseExporter

logger = logging.getLogger("ai_obs.registry")


class ExporterRegistry:
    """Thread-safe registry of BaseExporter instances."""

    def __init__(self) -> None:
        self._exporters: list["BaseExporter"] = []

    def register(self, exporter: "BaseExporter") -> None:
        """Add an exporter. Can be called at any time, including after startup."""
        self._exporters.append(exporter)
        logger.info("ai-obs: registered exporter %s", type(exporter).__name__)

    def unregister(self, exporter: "BaseExporter") -> None:
        self._exporters = [e for e in self._exporters if e is not exporter]

    def export_all(self, events: list[dict[str, Any]]) -> None:
        """Forward events to every registered exporter. Errors are isolated."""
        for exporter in self._exporters:
            try:
                exporter.export(events)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "ai-obs: exporter %s failed: %s", type(exporter).__name__, exc
                )

    def __len__(self) -> int:
        return len(self._exporters)

    def __repr__(self) -> str:
        names = [type(e).__name__ for e in self._exporters]
        return f"ExporterRegistry({names})"


#: Global singleton registry. Import and use directly.
registry = ExporterRegistry()
