"""
The @observe decorator — the core SDK primitive.

Wraps any function that calls an LLM and automatically captures:
- Latency (wall-clock time of the function call)
- Token usage and estimated cost (via provider extractors)
- Error details if the call raises
- Optional: prompt and completion text (opt-in via config)

The trace_id is a UUID generated per call. You can retrieve it by passing
``capture_trace_id=True`` — the decorator injects it as a ``_trace_id``
keyword argument so you can use it with ``score()`` and ``autoscore()``.

Usage::

    @observe(model="gpt-4o", provider="openai")
    def ask(prompt: str) -> str:
        ...

    # Capture the trace_id for later scoring:
    @observe(model="gpt-4o", provider="openai", capture_trace_id=True)
    def ask(prompt: str, *, _trace_id: str = "") -> str:
        result = call_openai(prompt)
        # _trace_id is injected — store it or pass to score()
        return result
"""
from __future__ import annotations

import functools
import time
import traceback
import uuid
from typing import Any, Callable, TypeVar

from ai_obs.client import get_client
from ai_obs.config import config
from ai_obs.providers import extract_usage

F = TypeVar("F", bound=Callable[..., Any])


def observe(
    *,
    model: str,
    provider: str = "generic",
    endpoint: str | None = None,
    tags: dict[str, str] | None = None,
    capture_trace_id: bool = False,
) -> Callable[[F], F]:
    """
    Decorator that wraps an AI call and emits observability telemetry.

    Args:
        model:             Model identifier, e.g. ``"gpt-4o"``, ``"claude-sonnet-4-6"``.
        provider:          One of ``openai``, ``anthropic``, ``bedrock``,
                           ``huggingface``, ``generic``.
        endpoint:          Logical name for this operation. Defaults to function name.
                           Use this to group multiple functions under one metric.
        tags:              Arbitrary string key/value labels. Stored with every event.
                           Useful for feature flags, experiment IDs, user segments.
        capture_trace_id:  If ``True``, injects ``_trace_id`` as a keyword argument
                           into the wrapped function so you can call ``score()`` with it.

    Returns:
        Decorated function with identical signature.
    """

    def decorator(fn: F) -> F:
        op_name = endpoint or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if config.disabled:
                return fn(*args, **kwargs)

            trace_id = str(uuid.uuid4())
            t0 = time.perf_counter()
            error: str | None = None
            result: Any = None

            # Inject trace_id into kwargs if the caller asked for it
            if capture_trace_id:
                kwargs["_trace_id"] = trace_id

            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                raise
            finally:
                latency_ms = (time.perf_counter() - t0) * 1000
                usage = extract_usage(provider=provider, result=result)

                event: dict[str, Any] = {
                    "trace_id": trace_id,
                    "model": model,
                    "provider": provider,
                    "endpoint": op_name,
                    "env": config.env,
                    "latency_ms": round(latency_ms, 2),
                    "prompt_tokens":     usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens":      usage.get("total_tokens"),
                    "cost_usd":          usage.get("cost_usd"),
                    "error": error,
                    "tags": tags or {},
                }

                # Optional prompt/completion capture (privacy opt-in)
                if config.capture_prompts and args:
                    event["prompt"] = str(args[0])[:4096]  # first positional arg, truncated
                if config.capture_completions and result is not None:
                    event["completion"] = str(result)[:4096]

                get_client().enqueue(event)

        # Expose metadata for introspection (useful for testing + framework integrations)
        wrapper._obs_model = model          # type: ignore[attr-defined]
        wrapper._obs_provider = provider    # type: ignore[attr-defined]
        wrapper._obs_endpoint = op_name     # type: ignore[attr-defined]
        wrapper.__wrapped__ = fn            # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator
