# ai-obs - Open AI Observability Platform

> One decorator. Any LLM. Full visibility.
> Self-hosted, provider-agnostic, and reusable in your own apps.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](https://docker.com)
[![CI](https://github.com/your-org/ai-obs/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/ai-obs/actions)
[![PyPI](https://img.shields.io/pypi/v/ai-obs-sdk)](https://pypi.org/project/ai-obs-sdk/)

[![Docker Pulls](https://img.shields.io/docker/pulls/jahnavik186/ai-observability-platform?style=for-the-badge&logo=docker)](https://hub.docker.com/r/jahnavik186/ai-observability-platform)

`ai-obs` is an open-source, self-hosted observability stack for AI applications.
It helps developers and teams answer a few practical questions:

- Which model calls are slow?
- How many tokens are we using and what are they costing?
- Which requests are failing?
- Is answer quality improving or drifting over time?
- How do we inspect all of this without sending telemetry to a third-party SaaS?

This repo gives you a reusable starting point:

- a Python SDK for instrumentation
- a collector API for ingesting telemetry
- PostgreSQL for traces and scores
- Redis for near-real-time counters
- Grafana dashboards for visibility

---

## Why This Repo Exists

Most AI teams end up rebuilding the same observability pieces:

- SDK instrumentation around model calls
- an API to receive events
- storage for traces and scores
- queries for cost, latency, and errors
- dashboards for operators and developers

Commercial tools can solve some of this, but they often add vendor lock-in,
cost, and privacy concerns around prompts and completions.

`ai-obs` is for teams that want a local-first, self-hosted, forkable alternative.

---

## Who This Helps

This repo is useful for:

- solo developers shipping AI features
- teams building chatbots, agents, RAG apps, and internal AI tools
- platform engineers who want a reusable observability foundation
- companies that need telemetry to stay inside their own infrastructure

---

## What You Get

| Capability | What it gives you |
|---|---|
| Latency tracking | p50, p95, p99, and average latency by model, endpoint, and environment |
| Cost tracking | Token usage and estimated USD spend by provider and model |
| Error tracking | Error counts, error rates, and failure details |
| Accuracy scoring | Manual scoring plus LLM-as-judge workflows |
| Throughput monitoring | Request volume and live counters |
| Drift visibility | Trends in latency and scoring over time |
| Provider flexibility | OpenAI, Anthropic, Bedrock, Hugging Face, local HTTP endpoints, and more |
| Extensibility | Exporters and custom integrations |
| Self-hosting | Your telemetry stays in your infrastructure |
| Reusable dashboards | Grafana is provisioned automatically |

---

## How It Works

At a high level, your app emits telemetry through the SDK, the collector stores it,
and Grafana reads the resulting metrics.

```text
Your AI app
  |
  |  @observe / score()
  v
ai-obs SDK
  |
  |  batched HTTP events
  v
Collector API (:8080)
  | \
  |  \-- Redis for live counters
  |
  \---- PostgreSQL for traces and scores

Grafana (:3000)
  |
  \-- dashboards backed by the collector and stored telemetry
```

---

## Reuse Workflow

Another developer can reuse this repo with a simple flow:

1. Start the local stack with Docker Compose.
2. Point an app at the collector with `AI_OBS_ENDPOINT=http://localhost:8080`.
3. Install or import the SDK.
4. Add `@observe(...)` to one or more LLM call functions.
5. Optionally call `score(...)` or `autoscore(...)` to track quality.
6. Open Grafana to inspect latency, cost, errors, and accuracy.
7. Fork and customize exporters, dashboards, schema, or provider integrations if needed.

---

## Impact For Other Developers

Publishing this repo helps other teams because it removes a lot of setup and design work.
Instead of separately building instrumentation, ingestion, storage, queries, and dashboards,
they can start from a working baseline and adapt it to their own product.

That means faster:

- debugging of slow or failing LLM calls
- visibility into token spend
- comparison across models and providers
- rollout of AI features with better operational confidence

---

## 60-Second Quick Start

```bash
git clone https://github.com/your-org/ai-obs.git
cd ai-obs
cp .env.example .env
docker compose up -d
```

Open:

- `http://localhost:3000` for Grafana (`admin` / `admin`)
- `http://localhost:8080/docs` for collector API docs

Install the SDK:

```bash
pip install ai-obs-sdk
```

Wrap an existing model call:

```python
from ai_obs import observe

@observe(model="gpt-4o", provider="openai", endpoint="chat")
def ask(prompt: str) -> str:
    return call_your_llm(prompt)
```

After that, telemetry starts flowing into the collector and Grafana can visualize it.

---

## Minimal Example

```python
from ai_obs import observe, score

@observe(model="gpt-4o-mini", provider="openai", endpoint="support-chat", capture_trace_id=True)
def reply(prompt: str, *, _trace_id: str = "") -> tuple[str, str]:
    answer = call_openai(prompt)
    return answer, _trace_id

answer, trace_id = reply("How do I reset my password?")
score(trace_id=trace_id, value=1.0, label="correct")
```

What happens next:

1. The decorator measures latency and extracts usage data.
2. The SDK batches and sends the trace to the collector.
3. The score is attached to the same `trace_id`.
4. The collector stores both.
5. Grafana can now show operational and quality metrics for that interaction.

---

## Local Stack

The Docker Compose stack starts these core services:

- `collector` on `:8080`
- `grafana` on `:3000`
- `postgres` for event and score storage
- `redis` for near-real-time counters
- `minio` for optional object storage workflows

Collector endpoints:

- `POST /v1/events` to ingest trace batches
- `POST /v1/scores` and `POST /v1/score` to ingest quality scores
- `GET /v1/metrics/*` for dashboards and programmatic queries
- `GET /v1/health` and `GET /v1/health/ready` for health checks
- `GET /docs` for interactive API documentation

---

## SDK Usage

The SDK is designed to be low-friction. You add a decorator around the function
that already calls your model provider.

### OpenAI

```python
from ai_obs import observe
from openai import OpenAI

client = OpenAI()

@observe(model="gpt-4o", provider="openai", endpoint="chat")
def chat(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content
```

### Anthropic

```python
from ai_obs import observe
import anthropic

client = anthropic.Anthropic()

@observe(model="claude-sonnet-4-6", provider="anthropic")
def ask(prompt: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text
```

### Generic HTTP or local model endpoint

```python
from ai_obs import observe
import requests

@observe(model="llama3:8b", provider="generic", endpoint="ollama-local")
def ask_local(prompt: str) -> str:
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3", "prompt": prompt, "stream": False},
        timeout=30,
    )
    return resp.json()["response"]
```

---

## Accuracy Scoring

You can attach quality signals to a trace after the model call finishes.

### Manual scoring

```python
from ai_obs import score

score(trace_id="abc-123", value=1.0, label="correct")
score(trace_id="abc-124", value=0.0, label="hallucination")
```

### Automatic scoring with an LLM judge

```python
from ai_obs import autoscore

autoscore(
    trace_id="abc-125",
    question="What is the capital of France?",
    answer="Lyon",
    reference="Paris",
)
```

---

## Configuration

All config is environment-driven.

| Variable | Default | Description |
|---|---|---|
| `AI_OBS_ENDPOINT` | `http://localhost:8080` | Collector URL |
| `AI_OBS_API_KEY` | *(none)* | Optional auth key |
| `AI_OBS_ENV` | `production` | Environment tag |
| `AI_OBS_BATCH_SIZE` | `50` | Events per HTTP flush |
| `AI_OBS_FLUSH_INTERVAL` | `5` | Seconds between flushes |
| `AI_OBS_DISABLE` | `false` | Disable SDK emission |
| `AI_OBS_SAMPLE_RATE` | `1.0` | Fraction of events to keep |
| `AI_OBS_CAPTURE_PROMPTS` | `false` | Capture prompt text |
| `AI_OBS_CAPTURE_COMPLETIONS` | `false` | Capture completion text |
| `AI_OBS_TIMEOUT` | `5` | Collector HTTP timeout in seconds |

---

## Architecture Notes

The repo is split into a few clear pieces:

- `sdk/` contains the Python SDK
- `collector/` contains the FastAPI ingestion service
- `dashboard/` contains Grafana provisioning
- `storage/` contains database initialization and migrations
- `docs/examples/` contains copyable examples

This makes it easy to reuse the whole stack or just one part of it.

---

## Ways To Reuse This Repo

You can reuse this project in a few ways:

### 1. Use it as-is

Run the Docker stack locally or in your environment and point your app to it.

### 2. Fork it for internal tooling

Keep the SDK and collector, but customize:

- dashboard panels
- data retention
- auth
- schema
- exporters

### 3. Reuse only the SDK

Keep `sdk/` and point it at your own ingestion service.

### 4. Reuse only the collector and dashboards

If you already have your own instrumentation layer, send events directly to the collector API.

---

## Example Workflow For A Team

```text
Developer adds @observe(...) to model call
        |
        v
App sends telemetry to local or hosted collector
        |
        v
Collector stores traces and scores
        |
        v
Grafana shows latency, cost, errors, and accuracy
        |
        v
Team uses that data to debug, compare models, and improve quality
```

---

## Roadmap Ideas

- JavaScript and TypeScript SDK
- better prompt and completion redaction
- built-in alerting rules
- Kubernetes deployment support
- more provider integrations
- more exporters and storage backends

---

## License

MIT - use it, fork it, and adapt it.
