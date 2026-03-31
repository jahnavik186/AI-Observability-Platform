"""
Built-in exporters — ready to use, easy to extend.

Available exporters
-------------------
- ``StdoutExporter``        — prints events as JSON (great for debugging)
- ``WebhookExporter``       — POSTs events to any HTTP endpoint (Slack, Teams, etc.)
- ``S3Exporter``            — writes NDJSON batches to S3-compatible storage
- ``DatadogExporter``       — ships custom metrics to Datadog via their HTTP API
- ``FileExporter``          — appends NDJSON to a local file (simple audit log)
- ``PrometheusExporter``    — exposes a /metrics endpoint for Prometheus scraping
- ``OpenTelemetryExporter`` — emits OTLP spans/metrics (works with Jaeger, Tempo, etc.)
- ``GrafanaLokiExporter``   — ships structured log lines to Grafana Loki
- ``MLflowExporter``        — logs metrics and tags to an MLflow tracking server
- ``ClickHouseExporter``    — bulk-inserts events into ClickHouse (high-volume)
- ``ElasticsearchExporter`` — indexes events into Elasticsearch / OpenSearch
- ``NewRelicExporter``      — ships events to New Relic via their Telemetry API
- ``SigNozExporter``        — forwards to SigNoz (open-source Datadog alternative)
- ``OpenObserveExporter``   — sends to OpenObserve (lightweight Elastic alternative)

Usage::

    from ai_obs import registry
    from ai_obs.exporters import StdoutExporter, WebhookExporter

    registry.register(StdoutExporter())
    registry.register(WebhookExporter(url="https://hooks.example.com/ai"))
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

from ai_obs.exporters.base import BaseExporter

logger = logging.getLogger("ai_obs.exporters")

__all__ = [
    "BaseExporter",
    "StdoutExporter",
    "WebhookExporter",
    "FileExporter",
    "S3Exporter",
    "DatadogExporter",
    "PrometheusExporter",
    "OpenTelemetryExporter",
    "GrafanaLokiExporter",
    "MLflowExporter",
    "ClickHouseExporter",
    "ElasticsearchExporter",
    "NewRelicExporter",
    "SigNozExporter",
    "OpenObserveExporter",
]


# ── StdoutExporter ─────────────────────────────────────────────────────────────

class StdoutExporter(BaseExporter):
    """
    Prints every event as a JSON line to stdout.
    Ideal for local development and CI debugging.

    Example::

        from ai_obs import registry
        from ai_obs.exporters import StdoutExporter
        registry.register(StdoutExporter(pretty=True))
    """

    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty

    def export(self, events: list[dict[str, Any]]) -> None:
        indent = 2 if self.pretty else None
        for event in events:
            print(json.dumps(event, indent=indent, default=str))


# ── FileExporter ───────────────────────────────────────────────────────────────

class FileExporter(BaseExporter):
    """
    Appends events as NDJSON lines to a local file.
    Simple audit log — no dependencies required.

    Example::

        registry.register(FileExporter(path="/var/log/ai-obs/events.ndjson"))
    """

    def __init__(self, path: str = "ai_obs_events.ndjson") -> None:
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def export(self, events: list[dict[str, Any]]) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, default=str) + "\n")


# ── WebhookExporter ────────────────────────────────────────────────────────────

class WebhookExporter(BaseExporter):
    """
    POSTs events as a JSON batch to any HTTP endpoint.
    Works with Slack incoming webhooks, custom APIs, n8n, Zapier, etc.

    Example::

        registry.register(WebhookExporter(
            url="https://hooks.slack.com/services/...",
            headers={"Authorization": "Bearer token"},
            timeout=3,
        ))
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.url = url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout = timeout

    def export(self, events: list[dict[str, Any]]) -> None:
        payload = json.dumps({"events": events, "count": len(events)}, default=str).encode()
        req = urllib.request.Request(self.url, data=payload, headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("WebhookExporter: POST failed: %s", exc)


# ── S3Exporter ─────────────────────────────────────────────────────────────────

class S3Exporter(BaseExporter):
    """
    Writes event batches as NDJSON files to S3 or any S3-compatible store
    (MinIO, Cloudflare R2, Backblaze B2, etc.).

    Requires ``boto3``: ``pip install ai-obs-sdk[s3]``

    Files are written to::

        s3://<bucket>/<prefix>/<env>/YYYY/MM/DD/HH/<uuid>.ndjson

    Example::

        registry.register(S3Exporter(
            bucket="my-ai-logs",
            region="us-east-1",
            prefix="ai-obs",
        ))
        # For MinIO / custom endpoint:
        registry.register(S3Exporter(
            bucket="ai-obs-logs",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
        ))
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        prefix: str = "ai-obs",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self._region = region
        self._endpoint_url = endpoint_url
        self._key_id = aws_access_key_id
        self._secret = aws_secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3  # lazy import
            kwargs: dict[str, Any] = {"region_name": self._region}
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            if self._key_id:
                kwargs["aws_access_key_id"] = self._key_id
                kwargs["aws_secret_access_key"] = self._secret
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def export(self, events: list[dict[str, Any]]) -> None:
        import uuid
        now = datetime.now(timezone.utc)
        env = events[0].get("env", "production") if events else "production"
        key = (
            f"{self.prefix}/{env}/"
            f"{now.strftime('%Y/%m/%d/%H')}/"
            f"{uuid.uuid4()}.ndjson"
        )
        body = "\n".join(json.dumps(e, default=str) for e in events)
        try:
            self._get_client().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body.encode(),
                ContentType="application/x-ndjson",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("S3Exporter: upload failed: %s", exc)


# ── DatadogExporter ────────────────────────────────────────────────────────────

class DatadogExporter(BaseExporter):
    """
    Ships custom metrics to Datadog via their v2 metrics API.

    Sends per-event series for: latency, token count, cost, error count.
    Each metric is tagged with model, provider, and environment.

    Requires a Datadog API key.

    Example::

        registry.register(DatadogExporter(
            api_key="dd-xxxxxxxxxxxxxxxx",
            site="datadoghq.com",   # or datadoghq.eu for EU region
        ))
    """

    _ENDPOINT = "https://api.{site}/api/v2/series"

    def __init__(self, api_key: str, site: str = "datadoghq.com") -> None:
        self.api_key = api_key
        self.url = self._ENDPOINT.format(site=site)

    def export(self, events: list[dict[str, Any]]) -> None:
        series = []
        now_epoch = int(datetime.now(timezone.utc).timestamp())

        for e in events:
            tags = [
                f"model:{e.get('model', 'unknown')}",
                f"provider:{e.get('provider', 'unknown')}",
                f"env:{e.get('env', 'production')}",
            ]
            if e.get("latency_ms") is not None:
                series.append(self._point("ai_obs.latency_ms", e["latency_ms"], now_epoch, tags))
            if e.get("total_tokens"):
                series.append(self._point("ai_obs.total_tokens", e["total_tokens"], now_epoch, tags))
            if e.get("cost_usd") is not None:
                series.append(self._point("ai_obs.cost_usd", e["cost_usd"], now_epoch, tags))
            if e.get("error"):
                series.append(self._point("ai_obs.errors", 1, now_epoch, tags, type_="count"))

        if not series:
            return

        payload = json.dumps({"series": series}).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "DD-API-KEY": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.URLError as exc:
            logger.debug("DatadogExporter: request failed: %s", exc)

    @staticmethod
    def _point(name: str, value: float, ts: int, tags: list[str], type_: str = "gauge") -> dict:
        return {
            "metric": name,
            "type": 0 if type_ == "gauge" else 1,
            "points": [{"timestamp": ts, "value": value}],
            "tags": tags,
        }


# ── PrometheusExporter ─────────────────────────────────────────────────────────

class PrometheusExporter(BaseExporter):
    """
    Exposes ai-obs metrics in Prometheus text format via a built-in HTTP server.

    Tracks latency (histogram), token counts (counter), cost (counter), and
    error rate (counter) — all labelled by model, provider, and environment.

    Requires ``prometheus-client``: ``pip install ai-obs-sdk[prometheus]``

    Example::

        registry.register(PrometheusExporter(port=9090))
        # Then add a scrape target in prometheus.yml:
        #   - job_name: ai-obs
        #     static_configs:
        #       - targets: ['localhost:9090']
    """

    def __init__(self, port: int = 9090, addr: str = "") -> None:
        self.port = port
        self.addr = addr
        self._setup()

    def _setup(self) -> None:
        try:
            from prometheus_client import Counter, Histogram, start_http_server
            self._latency = Histogram(
                "ai_obs_latency_ms",
                "LLM call latency in milliseconds",
                ["model", "provider", "env"],
                buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000],
            )
            self._tokens = Counter(
                "ai_obs_tokens_total",
                "Total tokens consumed",
                ["model", "provider", "env", "type"],
            )
            self._cost = Counter(
                "ai_obs_cost_usd_total",
                "Total estimated USD cost",
                ["model", "provider", "env"],
            )
            self._errors = Counter(
                "ai_obs_errors_total",
                "Total LLM call errors",
                ["model", "provider", "env"],
            )
            start_http_server(self.port, addr=self.addr)
            logger.info("PrometheusExporter: scrape endpoint at :%d/metrics", self.port)
        except ImportError:
            logger.warning("PrometheusExporter: install prometheus-client — pip install ai-obs-sdk[prometheus]")
            self._latency = self._tokens = self._cost = self._errors = None

    def export(self, events: list[dict[str, Any]]) -> None:
        if self._latency is None:
            return
        for e in events:
            labels = [e.get("model", "unknown"), e.get("provider", "unknown"), e.get("env", "production")]
            if e.get("latency_ms") is not None:
                self._latency.labels(*labels).observe(e["latency_ms"])
            if e.get("prompt_tokens"):
                self._tokens.labels(*labels, "prompt").inc(e["prompt_tokens"])
            if e.get("completion_tokens"):
                self._tokens.labels(*labels, "completion").inc(e["completion_tokens"])
            if e.get("cost_usd"):
                self._cost.labels(*labels).inc(e["cost_usd"])
            if e.get("error"):
                self._errors.labels(*labels).inc()


# ── OpenTelemetryExporter ──────────────────────────────────────────────────────

class OpenTelemetryExporter(BaseExporter):
    """
    Emits ai-obs events as OpenTelemetry spans and metrics via OTLP.

    Compatible with any OTLP-capable backend: Jaeger, Grafana Tempo,
    Honeycomb, Lightstep, SigNoz, Dynatrace, and more.

    Requires ``opentelemetry-sdk`` + ``opentelemetry-exporter-otlp``:
    ``pip install ai-obs-sdk[otel]``

    Example::

        # Jaeger / Grafana Tempo
        registry.register(OpenTelemetryExporter(
            endpoint="http://localhost:4317",
            service_name="my-ai-app",
        ))
        # Honeycomb
        registry.register(OpenTelemetryExporter(
            endpoint="https://api.honeycomb.io:443",
            headers={"x-honeycomb-team": "YOUR_API_KEY"},
        ))
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        service_name: str = "ai-obs",
        headers: dict[str, str] | None = None,
        insecure: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.service_name = service_name
        self.headers = headers or {}
        self.insecure = insecure
        self._tracer = None
        self._setup()

    def _setup(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            resource = Resource.create({"service.name": self.service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(
                endpoint=self.endpoint,
                headers=self.headers,
                insecure=self.insecure,
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer("ai-obs")
            logger.info("OpenTelemetryExporter: shipping spans to %s", self.endpoint)
        except ImportError:
            logger.warning(
                "OpenTelemetryExporter: install opentelemetry packages — "
                "pip install ai-obs-sdk[otel]"
            )

    def export(self, events: list[dict[str, Any]]) -> None:
        if self._tracer is None:
            return
        from opentelemetry.trace import StatusCode
        for e in events:
            with self._tracer.start_as_current_span(f"llm.{e.get('provider', 'unknown')}") as span:
                span.set_attribute("ai.model", e.get("model", ""))
                span.set_attribute("ai.provider", e.get("provider", ""))
                span.set_attribute("ai.env", e.get("env", ""))
                span.set_attribute("ai.latency_ms", e.get("latency_ms") or 0)
                span.set_attribute("ai.prompt_tokens", e.get("prompt_tokens") or 0)
                span.set_attribute("ai.completion_tokens", e.get("completion_tokens") or 0)
                span.set_attribute("ai.cost_usd", e.get("cost_usd") or 0.0)
                if e.get("error"):
                    span.set_status(StatusCode.ERROR, e["error"])
                    span.set_attribute("ai.error", e["error"])


# ── GrafanaLokiExporter ────────────────────────────────────────────────────────

class GrafanaLokiExporter(BaseExporter):
    """
    Pushes ai-obs events as structured log lines to Grafana Loki.

    Each event becomes a JSON log line with Loki labels for model,
    provider, and environment — queryable with LogQL.

    No extra dependencies — uses the stdlib HTTP client.

    Example::

        # Local Loki
        registry.register(GrafanaLokiExporter(url="http://localhost:3100"))
        # Grafana Cloud
        registry.register(GrafanaLokiExporter(
            url="https://logs-prod-XXX.grafana.net",
            username="123456",
            password="glc_xxx",
        ))
    """

    def __init__(
        self,
        url: str = "http://localhost:3100",
        username: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.push_url = url.rstrip("/") + "/loki/api/v1/push"
        self.timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if username and password:
            import base64
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._headers["Authorization"] = f"Basic {token}"

    def export(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        # Group by label set {model, provider, env}
        groups: dict[tuple, list] = {}
        for e in events:
            key = (e.get("model", "unknown"), e.get("provider", "unknown"), e.get("env", "production"))
            groups.setdefault(key, []).append(e)

        streams = []
        for (model, provider, env), evts in groups.items():
            values = []
            for e in evts:
                ts_ns = str(int(datetime.now(timezone.utc).timestamp() * 1e9))
                values.append([ts_ns, json.dumps(e, default=str)])
            streams.append({
                "stream": {"model": model, "provider": provider, "env": env, "app": "ai-obs"},
                "values": values,
            })

        payload = json.dumps({"streams": streams}).encode()
        req = urllib.request.Request(self.push_url, data=payload, headers=self._headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("GrafanaLokiExporter: push failed: %s", exc)


# ── MLflowExporter ─────────────────────────────────────────────────────────────

class MLflowExporter(BaseExporter):
    """
    Logs ai-obs metrics and metadata to an MLflow tracking server.

    Each flush creates (or continues) an MLflow run under the configured
    experiment, logging latency, tokens, cost, and error count as metrics.

    Requires ``mlflow``: ``pip install ai-obs-sdk[mlflow]``

    Example::

        registry.register(MLflowExporter(
            tracking_uri="http://localhost:5000",
            experiment_name="production-llm-metrics",
        ))
    """

    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        experiment_name: str = "ai-obs",
        run_name: str = "production",
    ) -> None:
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        self.run_name = run_name
        self._run_id: str | None = None
        self._client = None

    def _get_client(self):
        if self._client is None:
            import mlflow
            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            run = mlflow.start_run(run_name=self.run_name)
            self._run_id = run.info.run_id
            self._client = mlflow.tracking.MlflowClient()
        return self._client

    def export(self, events: list[dict[str, Any]]) -> None:
        try:
            client = self._get_client()
            import mlflow
            step = int(datetime.now(timezone.utc).timestamp())
            for e in events:
                prefix = f"{e.get('provider','unknown')}.{e.get('model','unknown')}".replace("/", "_")
                metrics = {}
                if e.get("latency_ms") is not None:
                    metrics[f"{prefix}.latency_ms"] = e["latency_ms"]
                if e.get("total_tokens"):
                    metrics[f"{prefix}.total_tokens"] = e["total_tokens"]
                if e.get("cost_usd") is not None:
                    metrics[f"{prefix}.cost_usd"] = e["cost_usd"]
                if e.get("error"):
                    metrics[f"{prefix}.errors"] = 1
                for key, val in metrics.items():
                    client.log_metric(self._run_id, key, val, step=step)
        except Exception as exc:
            logger.debug("MLflowExporter: logging failed: %s", exc)

    def close(self) -> None:
        if self._run_id:
            try:
                import mlflow
                mlflow.end_run()
            except Exception:
                pass


# ── ClickHouseExporter ─────────────────────────────────────────────────────────

class ClickHouseExporter(BaseExporter):
    """
    Bulk-inserts ai-obs events into a ClickHouse table.

    ClickHouse is widely used for high-volume analytics in Asia and Europe.
    This exporter targets the HTTP interface so no native driver is needed,
    but also works with ``clickhouse-connect`` if installed.

    Table DDL (run once)::

        CREATE TABLE ai_obs_events (
            trace_id      String,
            timestamp_utc DateTime64(3, 'UTC'),
            model         LowCardinality(String),
            provider      LowCardinality(String),
            env           LowCardinality(String),
            latency_ms    Float64,
            prompt_tokens UInt32,
            completion_tokens UInt32,
            total_tokens  UInt32,
            cost_usd      Float64,
            error         String
        ) ENGINE = MergeTree()
        ORDER BY (provider, model, timestamp_utc);

    Example::

        registry.register(ClickHouseExporter(
            host="localhost",
            database="analytics",
            user="default",
            password="",
        ))
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        database: str = "default",
        user: str = "default",
        password: str = "",
        table: str = "ai_obs_events",
        timeout: float = 10.0,
    ) -> None:
        self.url = f"http://{host}:{port}/"
        self.database = database
        self.user = user
        self.password = password
        self.table = table
        self.timeout = timeout

    def export(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        rows = []
        for e in events:
            rows.append("\t".join([
                str(e.get("trace_id", "")),
                str(e.get("timestamp_utc", datetime.now(timezone.utc).isoformat())),
                str(e.get("model", "")),
                str(e.get("provider", "")),
                str(e.get("env", "production")),
                str(e.get("latency_ms") or 0),
                str(e.get("prompt_tokens") or 0),
                str(e.get("completion_tokens") or 0),
                str(e.get("total_tokens") or 0),
                str(e.get("cost_usd") or 0),
                str(e.get("error") or ""),
            ]))
        body = "\n".join(rows).encode()
        query = f"INSERT INTO {self.database}.{self.table} FORMAT TabSeparated"
        req = urllib.request.Request(
            f"{self.url}?query={urllib.request.quote(query)}&user={self.user}&password={self.password}",
            data=body,
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("ClickHouseExporter: insert failed: %s", exc)


# ── ElasticsearchExporter ──────────────────────────────────────────────────────

class ElasticsearchExporter(BaseExporter):
    """
    Indexes ai-obs events into Elasticsearch or OpenSearch via the Bulk API.

    Works with self-hosted Elasticsearch, OpenSearch (AWS, Aiven),
    and Elastic Cloud. Compatible with the ELK/EFK stack.

    No extra dependencies — uses stdlib HTTP client.

    Example::

        # Local Elasticsearch
        registry.register(ElasticsearchExporter(url="http://localhost:9200"))
        # Elastic Cloud
        registry.register(ElasticsearchExporter(
            url="https://my-cluster.es.io:443",
            api_key="base64-encoded-api-key",
            index="ai-obs-events",
        ))
        # AWS OpenSearch
        registry.register(ElasticsearchExporter(
            url="https://search-xxx.eu-west-1.es.amazonaws.com",
            username="admin",
            password="secret",
        ))
    """

    def __init__(
        self,
        url: str = "http://localhost:9200",
        index: str = "ai-obs-events",
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.bulk_url = url.rstrip("/") + "/_bulk"
        self.index = index
        self.timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/x-ndjson"}
        if api_key:
            self._headers["Authorization"] = f"ApiKey {api_key}"
        elif username and password:
            import base64
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._headers["Authorization"] = f"Basic {token}"

    def export(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        lines = []
        for e in events:
            meta = json.dumps({"index": {"_index": self.index}})
            doc = json.dumps(e, default=str)
            lines.extend([meta, doc])
        body = ("\n".join(lines) + "\n").encode()
        req = urllib.request.Request(self.bulk_url, data=body, headers=self._headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("ElasticsearchExporter: bulk failed: %s", exc)


# ── NewRelicExporter ───────────────────────────────────────────────────────────

class NewRelicExporter(BaseExporter):
    """
    Ships ai-obs events to New Relic via their Event API.

    Events appear in New Relic under the ``AiObsEvent`` custom event type
    and can be queried with NRQL::

        SELECT average(latency_ms) FROM AiObsEvent
        WHERE provider = 'openai' FACET model TIMESERIES

    Requires a New Relic Ingest License Key.

    Example::

        registry.register(NewRelicExporter(
            api_key="NRAK-XXXXXXXXXXXXXXXX",
            account_id="1234567",
            region="US",  # or "EU"
        ))
    """

    _ENDPOINTS = {
        "US": "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events",
        "EU": "https://insights-collector.eu01.nr-data.net/v1/accounts/{account_id}/events",
    }

    def __init__(self, api_key: str, account_id: str, region: str = "US", timeout: float = 5.0) -> None:
        self.url = self._ENDPOINTS[region.upper()].format(account_id=account_id)
        self.api_key = api_key
        self.timeout = timeout

    def export(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        nr_events = []
        for e in events:
            nr_events.append({
                "eventType": "AiObsEvent",
                "model": e.get("model", ""),
                "provider": e.get("provider", ""),
                "env": e.get("env", "production"),
                "latency_ms": e.get("latency_ms") or 0,
                "prompt_tokens": e.get("prompt_tokens") or 0,
                "completion_tokens": e.get("completion_tokens") or 0,
                "cost_usd": e.get("cost_usd") or 0,
                "error": int(bool(e.get("error"))),
                "trace_id": e.get("trace_id", ""),
            })
        payload = json.dumps(nr_events).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "Api-Key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("NewRelicExporter: request failed: %s", exc)


# ── SigNozExporter ─────────────────────────────────────────────────────────────

class SigNozExporter(BaseExporter):
    """
    Forwards ai-obs events to SigNoz — the open-source Datadog alternative
    widely adopted in India, Southeast Asia, and cost-sensitive teams globally.

    SigNoz accepts OTLP, so this exporter wraps ``OpenTelemetryExporter``
    with SigNoz-specific defaults. It can also ship logs directly via HTTP.

    Requires ``opentelemetry-sdk`` + ``opentelemetry-exporter-otlp``:
    ``pip install ai-obs-sdk[otel]``

    Example::

        # Self-hosted SigNoz
        registry.register(SigNozExporter(endpoint="http://localhost:4317"))
        # SigNoz Cloud
        registry.register(SigNozExporter(
            endpoint="ingest.signoz.io:443",
            api_key="YOUR_SIGNOZ_INGESTION_KEY",
            insecure=False,
        ))
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        api_key: str | None = None,
        service_name: str = "ai-obs",
        insecure: bool = True,
    ) -> None:
        headers = {"signoz-ingestion-key": api_key} if api_key else {}
        self._otel = OpenTelemetryExporter(
            endpoint=endpoint,
            service_name=service_name,
            headers=headers,
            insecure=insecure,
        )

    def export(self, events: list[dict[str, Any]]) -> None:
        self._otel.export(events)


# ── OpenObserveExporter ────────────────────────────────────────────────────────

class OpenObserveExporter(BaseExporter):
    """
    Sends ai-obs events to OpenObserve (formerly ZincObserve) —
    a lightweight, Rust-based observability backend with ~140× lower
    storage cost than Elasticsearch. Popular in Asia, Latin America,
    and teams replacing the ELK stack.

    No extra dependencies — uses stdlib HTTP client.

    Example::

        # Local OpenObserve
        registry.register(OpenObserveExporter(
            url="http://localhost:5080",
            org="default",
            stream="ai_obs",
            username="root@example.com",
            password="Complexpass#123",
        ))
        # OpenObserve Cloud
        registry.register(OpenObserveExporter(
            url="https://api.openobserve.ai",
            org="my-org",
            stream="ai_obs_prod",
            username="user@example.com",
            password="cloud-password",
        ))
    """

    def __init__(
        self,
        url: str = "http://localhost:5080",
        org: str = "default",
        stream: str = "ai_obs",
        username: str = "root@example.com",
        password: str = "Complexpass#123",
        timeout: float = 5.0,
    ) -> None:
        import base64
        self.ingest_url = f"{url.rstrip('/')}/api/{org}/{stream}/_json"
        self.timeout = timeout
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        }

    def export(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        payload = json.dumps(events, default=str).encode()
        req = urllib.request.Request(self.ingest_url, data=payload, headers=self._headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as exc:
            logger.debug("OpenObserveExporter: ingest failed: %s", exc)
