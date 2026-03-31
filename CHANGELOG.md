# Changelog

## [0.3.0] — 2026-03-29

### Added — Exporters (global tool coverage)
- **`PrometheusExporter`** — Prometheus scrape endpoint with latency histogram, token/cost counters; pairs with existing Grafana stack
- **`OpenTelemetryExporter`** — OTLP span+metric export; works with Jaeger, Grafana Tempo, Honeycomb, Lightstep, Dynatrace, SigNoz
- **`GrafanaLokiExporter`** — structured log lines pushed to Loki with model/provider/env labels; queryable with LogQL
- **`MLflowExporter`** — logs per-model metrics to MLflow tracking server; compatible with Databricks
- **`ClickHouseExporter`** — high-volume bulk insert via HTTP interface; no driver dependency required
- **`ElasticsearchExporter`** — Bulk API indexing for Elasticsearch and AWS/Aiven OpenSearch
- **`NewRelicExporter`** — custom `AiObsEvent` type via New Relic Event API; NRQL-queryable
- **`SigNozExporter`** — wraps OTLP exporter with SigNoz defaults; supports SigNoz Cloud ingestion key
- **`OpenObserveExporter`** — lightweight Rust-based log/metric backend; popular ELK alternative in Asia & Latin America

### Added — Providers (world coverage)
- **Google Gemini** (`gemini`) — `google-generativeai` SDK + `usageMetadata` token extraction; cost table for Gemini 2.0 Flash, 1.5 Pro/Flash
- **Mistral AI** (`mistral`) — `mistralai` SDK; cost table for Large, Small, Nemo, Codestral
- **Cohere** (`cohere`) — v2 Chat API `tokens` usage extraction; cost table for Command R+, Command R, Command
- **DeepSeek** (`deepseek`) — OpenAI-compatible; cost table for deepseek-chat and deepseek-reasoner
- **Azure OpenAI** (`azure`) — delegates to OpenAI handler, prefixes model with `azure/` for correct cost lookup
- **Alibaba Qwen / DashScope** (`qwen`) — DashScope SDK + OpenAI-compatible endpoint; cost table for Qwen-Max/Plus/Turbo
- **Baidu ERNIE** (`baidu`, `ernie`) — ERNIE Bot API usage extraction; cost table for ERNIE 4.0 and 3.5

### Changed
- `pyproject.toml` version bumped to `0.3.0`
- Added `pip install ai-obs-sdk[prometheus]`, `[otel]`, `[mlflow]`, `[gemini]`, `[mistral]`, `[cohere]`, `[azure]`, `[qwen]` extras
- Updated `[all]` extra to include all new providers and exporters
- Cost table expanded from 20 → 54 model entries


All notable changes to ai-obs are documented here.

## [0.2.0] — 2025-06-01

### Added
- **Plugin exporter system** — register any number of custom exporters via `registry.register()`
- **Built-in exporters** — `StdoutExporter`, `FileExporter`, `WebhookExporter`, `S3Exporter`, `DatadogExporter`
- **FastAPI middleware** — `AIObsMiddleware` auto-instruments every route
- **LangChain callback handler** — `AIObsCallbackHandler` instruments any LangChain LLM
- **Sampling** — `AI_OBS_SAMPLE_RATE` controls what fraction of events are captured
- **Privacy controls** — `AI_OBS_CAPTURE_PROMPTS` / `AI_OBS_CAPTURE_COMPLETIONS` opt-in
- **`capture_trace_id=True`** — decorator injects `_trace_id` kwarg for easy manual scoring
- Provider aliases: `aws` → bedrock, `hf` → huggingface, `ollama`/`vllm`/`lmstudio` → generic
- `register_provider()` — register custom provider handlers at runtime
- Ollama native response format support in generic handler
- Llama-on-Bedrock token extraction
- Cost table expanded to cover gpt-o1, Llama 3, Mistral, Gemma
- Multi-stage Docker build (smaller image, non-root user, built-in healthcheck)
- `WORKERS` env var to configure uvicorn worker count
- `/v1/score` single-score convenience endpoint
- `/v1/metrics/cost` cost breakdown endpoint
- `/v1/metrics/providers` and `/v1/metrics/models` listing endpoints
- Query filters (`env`, `provider`, `model`) on all metric endpoints
- Richer seed data (1 000 events + 200 scores, realistic latency distribution)
- Full CI pipeline including PyPI publish and Docker Hub push on release

### Changed
- `score()` parameter renamed `score` → `value` for clarity
- Events now include `timestamp_utc` field (set at enqueue time)
- Collector now includes `prompt` and `completion` columns (null by default)
- PostgreSQL tuned with write-optimised settings in docker-compose

### Fixed
- `atexit` drain now runs reliably on SIGTERM
- Global client singleton is thread-safe (double-checked locking)
- Exporter errors are isolated — one failing exporter doesn't block others

## [0.1.0] — 2025-04-01

### Added
- Initial release
- `@observe` decorator for OpenAI, Anthropic, Bedrock, HuggingFace, Generic HTTP
- Manual `score()` and async `autoscore()` (LLM-as-judge)
- FastAPI collector with PostgreSQL + Redis + MinIO
- Grafana Overview and Accuracy dashboards
- Docker Compose stack
- GitHub Actions CI
