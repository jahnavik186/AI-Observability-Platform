"""
ai-obs SDK test suite.

All tests run without a network connection — no collector, no external APIs needed.
Run with: pytest tests/ -v
"""
from __future__ import annotations

import json
import time
import threading
from unittest.mock import MagicMock, patch, call

import pytest

from ai_obs import observe, score, autoscore
from ai_obs.client import ObsClient
from ai_obs.config import Config
from ai_obs.providers import extract_usage, _compute_cost, register_provider
from ai_obs.exporters import StdoutExporter, FileExporter, WebhookExporter, DatadogExporter
from ai_obs.registry import ExporterRegistry
from ai_obs.middleware import AIObsCallbackHandler


# ══════════════════════════════════════════════════════════════════════════════
# Provider extraction
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenAIExtraction:
    def _response(self, pt=10, ct=20, model="gpt-4o"):
        u = MagicMock(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt+ct)
        return MagicMock(usage=u, model=model)

    def test_tokens(self):
        u = extract_usage(provider="openai", result=self._response())
        assert u["prompt_tokens"] == 10
        assert u["completion_tokens"] == 20
        assert u["total_tokens"] == 30

    def test_cost_calculated(self):
        u = extract_usage(provider="openai", result=self._response())
        assert u["cost_usd"] is not None
        assert u["cost_usd"] > 0

    def test_dict_response(self):
        result = {"model": "gpt-4o", "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}}
        u = extract_usage(provider="openai", result=result)
        assert u["prompt_tokens"] == 5

    def test_alias_works(self):
        # "openai" and "OPENAI" should both work
        u = extract_usage(provider="OPENAI", result=self._response())
        assert "prompt_tokens" in u


class TestAnthropicExtraction:
    def _response(self, inp=15, out=25, model="claude-sonnet-4-6"):
        u = MagicMock(input_tokens=inp, output_tokens=out)
        return MagicMock(usage=u, model=model)

    def test_tokens(self):
        u = extract_usage(provider="anthropic", result=self._response())
        assert u["prompt_tokens"] == 15
        assert u["completion_tokens"] == 25
        assert u["total_tokens"] == 40

    def test_cost_calculated(self):
        u = extract_usage(provider="anthropic", result=self._response())
        assert u["cost_usd"] is not None


class TestBedrockExtraction:
    def test_titan_format(self):
        result = {"inputTextTokenCount": 8, "results": [{"tokenCount": 12}]}
        u = extract_usage(provider="bedrock", result=result)
        assert u["prompt_tokens"] == 8
        assert u["completion_tokens"] == 12

    def test_claude_on_bedrock(self):
        result = {"usage": {"inputTokens": 20, "outputTokens": 40}}
        u = extract_usage(provider="bedrock", result=result)
        assert u["prompt_tokens"] == 20
        assert u["completion_tokens"] == 40

    def test_llama_on_bedrock(self):
        result = {"prompt_token_count": 30, "generation_token_count": 60}
        u = extract_usage(provider="bedrock", result=result)
        assert u["prompt_tokens"] == 30
        assert u["completion_tokens"] == 60

    def test_aws_alias(self):
        result = {"inputTextTokenCount": 5, "results": [{"tokenCount": 10}]}
        u = extract_usage(provider="aws", result=result)
        assert u["prompt_tokens"] == 5


class TestHuggingFaceExtraction:
    def test_string_result(self):
        u = extract_usage(provider="huggingface", result="A" * 400)
        assert u["completion_tokens"] == 100

    def test_list_result(self):
        u = extract_usage(provider="huggingface", result=[{"generated_text": "X" * 200}])
        assert u["completion_tokens"] == 50


class TestGenericExtraction:
    def test_openai_compatible(self):
        result = {"usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}}
        u = extract_usage(provider="generic", result=result)
        assert u["prompt_tokens"] == 5

    def test_ollama_format(self):
        result = {"model": "llama3", "prompt_eval_count": 7, "eval_count": 14}
        u = extract_usage(provider="ollama", result=result)
        assert u["prompt_tokens"] == 7
        assert u["completion_tokens"] == 14

    def test_none_result(self):
        assert extract_usage(provider="openai", result=None) == {}

    def test_exception_swallowed(self):
        bad_result = object()  # will raise AttributeError on any getattr
        assert extract_usage(provider="openai", result=bad_result) == {}


class TestCustomProvider:
    def test_register_and_use(self):
        def my_handler(result):
            return {"prompt_tokens": result["in"], "completion_tokens": result["out"]}

        register_provider("myco", my_handler)
        u = extract_usage(provider="myco", result={"in": 3, "out": 7})
        assert u["prompt_tokens"] == 3
        assert u["completion_tokens"] == 7
        assert u["total_tokens"] == 10


class TestCostTable:
    def test_known_model(self):
        cost = _compute_cost("gpt-4o", 1000, 1000)
        assert cost == pytest.approx(0.02, rel=0.01)

    def test_unknown_model(self):
        assert _compute_cost("nonexistent-model-xyz", 100, 100) is None

    def test_partial_match(self):
        # "gpt-4o-mini" should match even inside a longer model string
        cost = _compute_cost("openai/gpt-4o-mini-2024", 1000, 1000)
        assert cost is not None


# ══════════════════════════════════════════════════════════════════════════════
# @observe decorator
# ══════════════════════════════════════════════════════════════════════════════

class TestObserveDecorator:
    def _mock_client(self):
        client = MagicMock()
        return client

    def test_passes_return_value(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            mock_get.return_value = self._mock_client()

            @observe(model="gpt-4o", provider="openai")
            def fn(x):
                return x * 3

            assert fn(7) == 21

    def test_enqueues_event(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client

            @observe(model="gpt-4o", provider="openai")
            def fn():
                return "ok"

            fn()
            assert client.enqueue.called
            event = client.enqueue.call_args[0][0]
            assert event["model"] == "gpt-4o"
            assert event["provider"] == "openai"

    def test_captures_latency(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client

            @observe(model="gpt-4o", provider="openai")
            def slow():
                time.sleep(0.05)
                return "done"

            slow()
            event = client.enqueue.call_args[0][0]
            assert event["latency_ms"] >= 50

    def test_captures_error(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client

            @observe(model="gpt-4o", provider="openai")
            def bad():
                raise ValueError("test error")

            with pytest.raises(ValueError):
                bad()

            event = client.enqueue.call_args[0][0]
            assert "ValueError" in event["error"]
            assert "test error" in event["error"]

    def test_tags_attached(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client

            @observe(model="gpt-4o", provider="openai", tags={"feature": "search", "version": "2"})
            def fn():
                return "ok"

            fn()
            event = client.enqueue.call_args[0][0]
            assert event["tags"]["feature"] == "search"

    def test_inject_trace_id(self):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            received_ids = []

            @observe(model="gpt-4o", provider="openai", capture_trace_id=True)
            def fn(prompt, *, _trace_id=""):
                received_ids.append(_trace_id)
                return "ok"

            fn("hello")
            assert len(received_ids) == 1
            assert len(received_ids[0]) == 36  # UUID format

    def test_disabled_config(self, monkeypatch):
        with patch("ai_obs.decorator.get_client") as mock_get:
            client = self._mock_client()
            mock_get.return_value = client
            cfg_module.disabled = True

            @observe(model="gpt-4o", provider="openai")
            def fn():
                return "ok"

            fn()
            assert not client.enqueue.called

    def test_metadata_on_wrapper(self):
        @observe(model="claude-sonnet-4-6", provider="anthropic", endpoint="my-endpoint")
        def fn():
            return "ok"

        assert fn._obs_model == "claude-sonnet-4-6"
        assert fn._obs_provider == "anthropic"
        assert fn._obs_endpoint == "my-endpoint"
        assert fn.__name__ == "fn"  # functools.wraps preserved


# ══════════════════════════════════════════════════════════════════════════════
# Client / queue
# ══════════════════════════════════════════════════════════════════════════════

class TestObsClient:
    def test_enqueue_and_drain(self):
        c = ObsClient()
        for i in range(5):
            c.enqueue({"id": i})
        events = c._drain_queue()
        assert len(events) == 5

    def test_timestamps_added(self):
        c = ObsClient()
        c.enqueue({"model": "gpt-4o"})
        events = c._drain_queue()
        assert "timestamp_utc" in events[0]

    def test_queue_full_warning(self, caplog):
        import logging
        c = ObsClient()
        c._queue.maxsize = 2
        c.enqueue({"id": 1})
        c.enqueue({"id": 2})
        with caplog.at_level(logging.WARNING, logger="ai_obs"):
            c.enqueue({"id": 3})  # should warn, not raise

    def test_sampling(self, monkeypatch):
        cfg_module.sample_rate = 0.0
        c = ObsClient()
        for _ in range(100):
            c.enqueue({"id": 1})
        events = c._drain_queue()
        assert len(events) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Exporters
# ══════════════════════════════════════════════════════════════════════════════

class TestExporters:
    EVENTS = [{"trace_id": "t1", "model": "gpt-4o", "latency_ms": 200, "env": "test"}]

    def test_stdout_exporter(self, capsys):
        e = StdoutExporter(pretty=False)
        e.export(self.EVENTS)
        captured = capsys.readouterr()
        assert "gpt-4o" in captured.out

    def test_file_exporter(self, tmp_path):
        path = str(tmp_path / "events.ndjson")
        e = FileExporter(path=path)
        e.export(self.EVENTS)
        e.export(self.EVENTS)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert "gpt-4o" in lines[0]

    def test_webhook_exporter_posts(self):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            e = WebhookExporter(url="https://example.com/hook")
            e.export(self.EVENTS)
            assert mock_open.called
            req = mock_open.call_args[0][0]
            body = json.loads(req.data.decode())
            assert body["count"] == 1
            assert body["events"][0]["model"] == "gpt-4o"

    def test_webhook_exporter_handles_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            e = WebhookExporter(url="https://example.com/hook")
            e.export(self.EVENTS)  # should not raise


class TestExporterRegistry:
    def test_register_and_export(self):
        reg = ExporterRegistry()
        exported = []

        class Collector(StdoutExporter):
            def export(self, events):
                exported.extend(events)

        reg.register(Collector())
        reg.export_all([{"id": 1}, {"id": 2}])
        assert len(exported) == 2

    def test_multiple_exporters(self):
        reg = ExporterRegistry()
        results = {"a": [], "b": []}

        class A(StdoutExporter):
            def export(self, events): results["a"].extend(events)

        class B(StdoutExporter):
            def export(self, events): results["b"].extend(events)

        reg.register(A())
        reg.register(B())
        reg.export_all([{"id": 1}])
        assert len(results["a"]) == 1
        assert len(results["b"]) == 1

    def test_exporter_error_isolated(self):
        reg = ExporterRegistry()
        working = []

        class BadExporter(StdoutExporter):
            def export(self, events): raise RuntimeError("broken")

        class GoodExporter(StdoutExporter):
            def export(self, events): working.extend(events)

        reg.register(BadExporter())
        reg.register(GoodExporter())
        reg.export_all([{"id": 1}])  # should not raise
        assert len(working) == 1     # good exporter still ran


# ══════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestScoring:
    def test_score_enqueues(self):
        with patch("ai_obs.scoring.get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client
            score(trace_id="abc", value=0.9, label="correct")
            assert client.enqueue.called
            event = client.enqueue.call_args[0][0]
            assert event["score"] == 0.9
            assert event["label"] == "correct"

    def test_score_clamped(self):
        with patch("ai_obs.scoring.get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client
            score(trace_id="abc", value=1.5)  # over 1.0
            event = client.enqueue.call_args[0][0]
            assert event["score"] == 1.0

    def test_autoscore_fires_thread(self):
        with patch("ai_obs.scoring._call_judge") as mock_judge, \
             patch("ai_obs.scoring.score") as mock_score:
            mock_judge.return_value = {"score": 0.8, "reasoning": "good"}
            autoscore(trace_id="t1", question="q", answer="a", reference="r")
            time.sleep(0.1)  # let the thread complete
            assert mock_score.called
            call_kwargs = mock_score.call_args[1]
            assert call_kwargs["value"] == 0.8
