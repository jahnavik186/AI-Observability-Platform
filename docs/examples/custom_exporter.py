"""
Custom exporter example.

Shows how to write your own exporter and register it with ai-obs.
This pattern lets you forward events to ANY system: ClickHouse, BigQuery,
Splunk, PagerDuty, your own database, etc.

Install: pip install ai-obs-sdk
"""
from __future__ import annotations

import json
from typing import Any

from ai_obs import observe, registry
from ai_obs.exporters import BaseExporter


# ── Example 1: Print exporter (debug / development) ──────────────────────────

class PrettyPrintExporter(BaseExporter):
    """Prints every event as formatted JSON — great for debugging."""

    def export(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            print(f"\n[ai-obs event] {event.get('model')} / {event.get('provider')}")
            print(f"  latency: {event.get('latency_ms')} ms")
            print(f"  tokens:  {event.get('total_tokens')}")
            print(f"  cost:    ${event.get('cost_usd')}")
            if event.get("error"):
                print(f"  ERROR:   {event.get('error')[:100]}")


# ── Example 2: ClickHouse exporter ───────────────────────────────────────────

class ClickHouseExporter(BaseExporter):
    """
    Writes events to ClickHouse via the HTTP interface.
    Install clickhouse-driver: pip install clickhouse-driver
    """

    def __init__(self, host: str, database: str = "ai_obs", table: str = "events") -> None:
        self.host = host
        self.database = database
        self.table = table

    def export(self, events: list[dict[str, Any]]) -> None:
        try:
            from clickhouse_driver import Client  # type: ignore
            client = Client(self.host)
            client.execute(
                f"INSERT INTO {self.database}.{self.table} VALUES",
                [
                    {
                        "trace_id":          e.get("trace_id", ""),
                        "model":             e.get("model", ""),
                        "provider":          e.get("provider", ""),
                        "latency_ms":        e.get("latency_ms") or 0.0,
                        "total_tokens":      e.get("total_tokens") or 0,
                        "cost_usd":          e.get("cost_usd") or 0.0,
                        "error":             e.get("error") or "",
                        "env":               e.get("env", "production"),
                        "timestamp":         e.get("timestamp_utc", ""),
                    }
                    for e in events
                ],
            )
        except Exception as exc:
            print(f"ClickHouseExporter error: {exc}")


# ── Example 3: Slack alert exporter (only on errors) ─────────────────────────

class SlackErrorExporter(BaseExporter):
    """
    Posts a Slack message whenever an error is detected.
    Only fires on events with a non-null error field.
    """

    def __init__(self, webhook_url: str, threshold_errors: int = 3) -> None:
        self.webhook_url = webhook_url
        self.threshold = threshold_errors
        self._error_count = 0

    def export(self, events: list[dict[str, Any]]) -> None:
        import urllib.request
        errors = [e for e in events if e.get("error")]
        if not errors:
            return

        self._error_count += len(errors)
        if self._error_count < self.threshold:
            return
        self._error_count = 0

        text = (
            f":rotating_light: *ai-obs: {len(errors)} errors detected*\n"
            + "\n".join(
                f"• `{e.get('model')}` — {e.get('error', '')[:80]}"
                for e in errors[:5]
            )
        )
        payload = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass


# ── Register and use ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Register exporters at startup — they receive every event batch
    registry.register(PrettyPrintExporter())

    # Uncomment to enable ClickHouse:
    # registry.register(ClickHouseExporter(host="localhost"))

    # Uncomment to enable Slack error alerts:
    # registry.register(SlackErrorExporter(webhook_url="https://hooks.slack.com/..."))

    print(f"Registered exporters: {registry}")

    # Now every @observe call flows through all registered exporters
    @observe(model="gpt-4o-mini", provider="openai")
    def demo_fn(prompt: str) -> str:
        return f"Simulated response to: {prompt}"

    demo_fn("Hello, world!")
    # Import the client and flush so the demo exits cleanly
    from ai_obs import get_client
    get_client().flush()
