# Contributing to ai-obs

ai-obs is built to be forked, extended, and improved by the community.
Here's how to get started.

---

## Development setup

```bash
git clone https://github.com/your-org/ai-obs.git
cd ai-obs

# Full stack
cp .env.example .env
docker compose up -d

# SDK development
cd sdk
pip install -e ".[dev]"
pytest tests/ -v

# Collector development (hot reload)
cd collector
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

---

## Project structure

```
ai-obs/
├── sdk/                        Python SDK  →  pip install ai-obs-sdk
│   ├── ai_obs/
│   │   ├── __init__.py         Public API: observe, score, autoscore, registry
│   │   ├── decorator.py        @observe implementation
│   │   ├── client.py           Batching HTTP transport
│   │   ├── config.py           Env-var configuration
│   │   ├── registry.py         Plugin exporter registry
│   │   ├── scoring.py          Manual + LLM-as-judge scoring
│   │   ├── providers/          Per-provider token/cost extraction
│   │   ├── exporters/          Built-in exporters (Webhook, S3, Datadog, File)
│   │   └── middleware/         FastAPI middleware + LangChain callback handler
│   └── tests/
│
├── collector/                  FastAPI telemetry collector
│   └── app/
│       ├── main.py
│       ├── database.py
│       ├── models/             SQLAlchemy ORM models
│       └── routers/            events, scores, metrics, health
│
├── storage/migrations/         init.sql — schema + demo seed data
│
├── dashboard/provisioning/     Grafana auto-provisioning
│   ├── datasources/            PostgreSQL datasource
│   └── dashboards/             Overview, Accuracy, Model Detail JSON
│
├── docs/examples/              Working code examples per provider/framework
│
└── .github/workflows/ci.yml   CI: test → lint → Docker build → integration → publish
```

---

## Key extension points

| What to add | Where to add it | Effort |
|---|---|---|
| New LLM provider | `sdk/ai_obs/providers/__init__.py` — add handler + cost entries | ~15 min |
| New built-in exporter | `sdk/ai_obs/exporters/__init__.py` — subclass `BaseExporter` | ~20 min |
| New framework integration | `sdk/ai_obs/middleware/__init__.py` | ~30 min |
| New API metric endpoint | `collector/app/routers/metrics.py` | ~20 min |
| New Grafana dashboard | Drop JSON in `dashboard/provisioning/dashboards/` | ~30 min |
| Schema change | `storage/migrations/` + `collector/app/models/` | ~15 min |

---

## Adding a new LLM provider (step-by-step)

1. **Add a handler** in `sdk/ai_obs/providers/__init__.py`:

```python
def _myprovider_handler(result: Any) -> dict[str, Any]:
    # Extract token counts from the provider's response object
    return {
        "model":             result.model_name,
        "prompt_tokens":     result.usage.input,
        "completion_tokens": result.usage.output,
    }
```

2. **Register it** in `_HANDLERS`:

```python
_HANDLERS["myprovider"] = _myprovider_handler
```

3. **Add cost entries** in `_COST_TABLE` if you have pricing:

```python
("my-model-v1", 0.001, 0.002),   # USD per 1k tokens: input, output
```

4. **Write a test** in `sdk/tests/test_sdk.py`:

```python
def test_myprovider_extraction():
    result = MockResult(...)
    u = extract_usage(provider="myprovider", result=result)
    assert u["prompt_tokens"] == expected
```

5. **Add an example** in `docs/examples/myprovider/example.py`.

---

## Writing a custom exporter

```python
from ai_obs.exporters import BaseExporter

class MyExporter(BaseExporter):
    def export(self, events: list[dict]) -> None:
        for event in events:
            # Forward to your system
            my_system.ingest(event)

    def close(self) -> None:
        # Called on process exit — flush buffers, close connections
        my_system.flush()
```

Register it:

```python
from ai_obs import registry
registry.register(MyExporter())
```

---

## PR guidelines

- One feature or fix per PR — keeps reviews manageable
- All tests must pass: `pytest sdk/tests/`
- No new hard dependencies in the SDK (stdlib only in `ai_obs/`)
- Update the README if you add a user-facing feature
- Add an example in `docs/examples/` for new providers or integrations

---

## Reporting bugs

Please include:
- Provider name and model
- SDK version: `pip show ai-obs-sdk`
- Python version: `python --version`
- Minimal reproduction snippet
- Expected vs actual behaviour
