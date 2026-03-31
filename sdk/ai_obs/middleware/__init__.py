"""
Framework integrations — middleware and callback handlers.

FastAPI middleware::

    from fastapi import FastAPI
    from ai_obs.middleware import AIObsMiddleware

    app = FastAPI()
    app.add_middleware(
        AIObsMiddleware,
        provider="openai",
        model="gpt-4o",
        skip_paths=["/health", "/metrics"],
    )

LangChain callback handler::

    from langchain_openai import ChatOpenAI
    from ai_obs.middleware import AIObsCallbackHandler

    llm = ChatOpenAI(
        model="gpt-4o",
        callbacks=[AIObsCallbackHandler(provider="openai")],
    )
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from ai_obs.client import get_client
from ai_obs.config import config

__all__ = ["AIObsMiddleware", "AIObsCallbackHandler"]


# ── FastAPI / Starlette ASGI middleware ────────────────────────────────────────

class AIObsMiddleware:
    """
    ASGI middleware that records request latency and errors for every route.

    Attach to a FastAPI app::

        app.add_middleware(
            AIObsMiddleware,
            provider="openai",
            model="gpt-4o",
            skip_paths=["/health", "/v1/metrics"],
        )

    Each HTTP request gets a trace_id.  You can still call ``score()`` on it
    by reading the ``X-AI-Obs-Trace-Id`` response header.
    """

    def __init__(
        self,
        app,
        *,
        provider: str = "generic",
        model: str = "unknown",
        skip_paths: list[str] | None = None,
    ) -> None:
        self.app = app
        self.provider = provider
        self.model = model
        self.skip_paths = set(skip_paths or ["/health", "/healthz", "/metrics", "/docs", "/redoc"])

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.skip_paths:
            await self.app(scope, receive, send)
            return

        trace_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        status_code = 500
        error = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Inject trace ID into response headers for client-side correlation
                headers = list(message.get("headers", []))
                headers.append((b"x-ai-obs-trace-id", trace_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if not config.disabled:
                latency_ms = (time.perf_counter() - t0) * 1000
                get_client().enqueue({
                    "trace_id":   trace_id,
                    "model":      self.model,
                    "provider":   self.provider,
                    "endpoint":   path,
                    "env":        config.env,
                    "latency_ms": round(latency_ms, 2),
                    "error":      error if (error or status_code >= 500) else None,
                    "tags":       {"http_status": str(status_code), "method": scope.get("method", "")},
                })


# ── LangChain callback handler ────────────────────────────────────────────────

class AIObsCallbackHandler:
    """
    LangChain callback handler that instruments any LangChain LLM or chain.

    Pass as a callback to any LangChain component::

        from langchain_openai import ChatOpenAI
        from ai_obs.middleware import AIObsCallbackHandler

        llm = ChatOpenAI(
            model="gpt-4o",
            callbacks=[AIObsCallbackHandler(provider="openai")],
        )

    Requires ``langchain-core``: ``pip install langchain-core``
    """

    def __init__(self, provider: str = "openai", tags: dict[str, str] | None = None) -> None:
        self.provider = provider
        self.tags = tags or {}
        self._t0: dict[str, float] = {}
        self._trace_ids: dict[str, str] = {}

    # LangChain callback protocol — only the methods we need

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs) -> None:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        self._t0[run_id] = time.perf_counter()
        self._trace_ids[run_id] = str(uuid.uuid4())

    def on_llm_end(self, response: Any, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        t0 = self._t0.pop(run_id, time.perf_counter())
        trace_id = self._trace_ids.pop(run_id, str(uuid.uuid4()))
        latency_ms = (time.perf_counter() - t0) * 1000

        # Extract token usage from LangChain LLMResult
        pt = ct = 0
        model = "unknown"
        try:
            for gen_list in response.generations:
                for gen in gen_list:
                    info = getattr(gen, "generation_info", {}) or {}
                    pt += info.get("prompt_tokens", 0)
                    ct += info.get("completion_tokens", 0)
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                pt = pt or usage.get("prompt_tokens", 0)
                ct = ct or usage.get("completion_tokens", 0)
                model = response.llm_output.get("model_name", "unknown")
        except Exception:  # noqa: BLE001
            pass

        if not config.disabled:
            get_client().enqueue({
                "trace_id":          trace_id,
                "model":             model,
                "provider":          self.provider,
                "endpoint":          "langchain",
                "env":               config.env,
                "latency_ms":        round(latency_ms, 2),
                "prompt_tokens":     pt,
                "completion_tokens": ct,
                "total_tokens":      pt + ct,
                "tags":              self.tags,
            })

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        run_id = str(kwargs.get("run_id", ""))
        t0 = self._t0.pop(run_id, time.perf_counter())
        trace_id = self._trace_ids.pop(run_id, str(uuid.uuid4()))

        if not config.disabled:
            get_client().enqueue({
                "trace_id":  trace_id,
                "model":     "unknown",
                "provider":  self.provider,
                "endpoint":  "langchain",
                "env":       config.env,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error":     f"{type(error).__name__}: {error}",
                "tags":      self.tags,
            })

    # No-ops — required by LangChain callback protocol
    def on_chain_start(self, *args, **kwargs): pass
    def on_chain_end(self, *args, **kwargs): pass
    def on_chain_error(self, *args, **kwargs): pass
    def on_tool_start(self, *args, **kwargs): pass
    def on_tool_end(self, *args, **kwargs): pass
    def on_tool_error(self, *args, **kwargs): pass
    def on_text(self, *args, **kwargs): pass
    def on_agent_action(self, *args, **kwargs): pass
    def on_agent_finish(self, *args, **kwargs): pass
