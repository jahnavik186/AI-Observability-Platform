"""
Provider-specific token usage and cost extraction.

Each LLM provider returns a different response shape.
This module normalises them into::

    {
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int,
        "cost_usd": float | None,
        "model": str,
    }

Adding a new provider
---------------------
1. Write a handler function: ``def _myprovider_handler(result) -> dict``
2. Add it to ``_HANDLERS`` at the bottom of this file.
3. Add cost-table entries if applicable.

That's it — the rest of the SDK picks it up automatically.
"""
from __future__ import annotations

from typing import Any


# ── Cost table (USD per 1,000 tokens: input price, output price) ──────────────
# These are approximate public figures. Override by subclassing or editing here.
# Keys are matched via ``pattern in model_name.lower()`` — more specific first.
_COST_TABLE: list[tuple[str, float, float]] = [
    # ── OpenAI ──────────────────────────────────────────────────────────────
    ("gpt-4o-mini",             0.000150, 0.000600),
    ("gpt-4o",                  0.005000, 0.015000),
    ("gpt-4-turbo",             0.010000, 0.030000),
    ("gpt-4",                   0.030000, 0.060000),
    ("gpt-3.5-turbo",           0.000500, 0.001500),
    ("o1-mini",                 0.003000, 0.012000),
    ("o1",                      0.015000, 0.060000),
    ("o3-mini",                 0.001100, 0.004400),
    ("o3",                      0.010000, 0.040000),
    # ── Anthropic ───────────────────────────────────────────────────────────
    ("claude-opus-4",           0.015000, 0.075000),
    ("claude-sonnet-4",         0.003000, 0.015000),
    ("claude-haiku-4",          0.000250, 0.001250),
    ("claude-3-opus",           0.015000, 0.075000),
    ("claude-3-5-sonnet",       0.003000, 0.015000),
    ("claude-3-haiku",          0.000250, 0.001250),
    # ── Google Gemini ────────────────────────────────────────────────────────
    ("gemini-2.0-flash",        0.000100, 0.000400),
    ("gemini-1.5-pro",          0.001250, 0.005000),
    ("gemini-1.5-flash",        0.000075, 0.000300),
    ("gemini-1.0-pro",          0.000500, 0.001500),
    # ── Mistral AI ───────────────────────────────────────────────────────────
    ("mistral-large",           0.002000, 0.006000),
    ("mistral-small",           0.000200, 0.000600),
    ("mistral-nemo",            0.000150, 0.000150),
    ("codestral",               0.000200, 0.000600),
    # ── Cohere ───────────────────────────────────────────────────────────────
    ("command-r-plus",          0.002500, 0.010000),
    ("command-r",               0.000150, 0.000600),
    ("command",                 0.001500, 0.002000),
    # ── DeepSeek (widely used in Asia) ───────────────────────────────────────
    ("deepseek-chat",           0.000140, 0.000280),
    ("deepseek-reasoner",       0.000550, 0.002190),
    # ── Qwen / Alibaba Cloud (dominant in China/Asia-Pacific) ────────────────
    ("qwen-max",                0.002400, 0.009600),
    ("qwen-plus",               0.000800, 0.002400),
    ("qwen-turbo",              0.000200, 0.000600),
    # ── Baidu ERNIE (China market) ───────────────────────────────────────────
    ("ernie-4.0",               0.010000, 0.030000),
    ("ernie-3.5",               0.001200, 0.001200),
    # ── AWS Bedrock ─────────────────────────────────────────────────────────
    ("amazon.titan-text-express", 0.000800, 0.001600),
    ("amazon.titan-text-lite",    0.000300, 0.000400),
    ("meta.llama3-70b",           0.002650, 0.003500),
    ("meta.llama3-8b",            0.000300, 0.000600),
    ("mistral.mistral-7b",        0.000150, 0.000200),
    ("mistral.mixtral-8x7b",      0.000450, 0.000700),
    # ── Azure OpenAI (enterprise globally) ───────────────────────────────────
    ("azure/gpt-4o",            0.005000, 0.015000),
    ("azure/gpt-4",             0.030000, 0.060000),
    ("azure/gpt-35-turbo",      0.000500, 0.001500),
    # ── HuggingFace / open-source (estimated) ───────────────────────────────
    ("llama-3-70b",               0.000900, 0.000900),
    ("llama-3-8b",                0.000200, 0.000200),
    ("mistral-7b",                0.000150, 0.000200),
    ("gemma-7b",                  0.000100, 0.000100),
]


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    key = model.lower()
    for pattern, in_price, out_price in _COST_TABLE:
        if pattern in key:
            return round(
                (prompt_tokens  / 1000) * in_price +
                (completion_tokens / 1000) * out_price,
                8,
            )
    return None   # unknown model — no cost estimate


def extract_usage(*, provider: str, result: Any) -> dict[str, Any]:
    """
    Return a normalised usage dict from a provider response object.

    Safe to call with ``result=None`` (returns empty dict).
    Never raises — exceptions are swallowed.
    """
    if result is None:
        return {}

    try:
        handler = _HANDLERS.get(provider.lower(), _generic_handler)
        usage = handler(result)
    except Exception:  # noqa: BLE001
        return {}

    pt = usage.get("prompt_tokens") or 0
    ct = usage.get("completion_tokens") or 0
    if pt or ct:
        usage.setdefault("total_tokens", pt + ct)
        if usage.get("cost_usd") is None:
            model = usage.get("model", "")
            usage["cost_usd"] = _compute_cost(model, pt, ct)
    return usage


# ── Provider handlers ─────────────────────────────────────────────────────────

def _openai_handler(result: Any) -> dict[str, Any]:
    """
    Handles ``openai.types.chat.ChatCompletion``,
    ``openai.types.Completion``, and dict equivalents.
    """
    # Object-style (official openai SDK)
    u = getattr(result, "usage", None)
    if u is not None:
        return {
            "model":              getattr(result, "model", ""),
            "prompt_tokens":      getattr(u, "prompt_tokens", 0),
            "completion_tokens":  getattr(u, "completion_tokens", 0),
            "total_tokens":       getattr(u, "total_tokens", 0),
        }
    # Dict-style (raw API response or mocked)
    if isinstance(result, dict):
        u = result.get("usage", {})
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     u.get("prompt_tokens", 0),
            "completion_tokens": u.get("completion_tokens", 0),
            "total_tokens":      u.get("total_tokens", 0),
        }
    return {}


def _anthropic_handler(result: Any) -> dict[str, Any]:
    """Handles ``anthropic.types.Message``."""
    u = getattr(result, "usage", None)
    if u is not None:
        return {
            "model":             getattr(result, "model", ""),
            "prompt_tokens":     getattr(u, "input_tokens", 0),
            "completion_tokens": getattr(u, "output_tokens", 0),
        }
    if isinstance(result, dict):
        u = result.get("usage", {})
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     u.get("input_tokens", 0),
            "completion_tokens": u.get("output_tokens", 0),
        }
    return {}


def _bedrock_handler(result: Any) -> dict[str, Any]:
    """
    Handles raw ``dict`` from boto3 ``bedrock-runtime.invoke_model()``.

    The caller must decode the streaming body before passing. We support:
    - Titan: ``inputTextTokenCount`` / ``results[0].tokenCount``
    - Claude via Bedrock: ``usage.inputTokens`` / ``usage.outputTokens``
    - Llama via Bedrock: ``prompt_token_count`` / ``generation_token_count``
    """
    if not isinstance(result, dict):
        return {}

    # Claude on Bedrock
    if "usage" in result:
        u = result["usage"]
        return {
            "prompt_tokens":     u.get("inputTokens") or u.get("input_tokens", 0),
            "completion_tokens": u.get("outputTokens") or u.get("output_tokens", 0),
        }
    # Llama on Bedrock
    if "prompt_token_count" in result:
        return {
            "prompt_tokens":     result.get("prompt_token_count", 0),
            "completion_tokens": result.get("generation_token_count", 0),
        }
    # Titan on Bedrock
    if "inputTextTokenCount" in result:
        ct = 0
        results = result.get("results", [])
        if results and isinstance(results[0], dict):
            ct = results[0].get("tokenCount", 0)
        return {
            "prompt_tokens":     result.get("inputTextTokenCount", 0),
            "completion_tokens": ct,
        }
    return {}


def _huggingface_handler(result: Any) -> dict[str, Any]:
    """
    HuggingFace InferenceClient responses don't expose token counts.
    We estimate from output length (~4 chars/token) — better than nothing.
    """
    text = ""
    if isinstance(result, str):
        text = result
    elif isinstance(result, list) and result:
        item = result[0]
        text = item.get("generated_text", "") if isinstance(item, dict) else str(item)
    elif isinstance(result, dict):
        text = result.get("generated_text", "") or result.get("text", "")

    estimated_tokens = max(1, len(text) // 4)
    return {"completion_tokens": estimated_tokens}


def _generic_handler(result: Any) -> dict[str, Any]:
    """
    Best-effort extraction for unknown/custom providers.
    Tries common field names used by Ollama, vLLM, LM Studio, etc.
    """
    if isinstance(result, dict):
        # OpenAI-compatible (Ollama, LM Studio, vLLM)
        u = result.get("usage") or {}
        if u:
            return {
                "model":             result.get("model", ""),
                "prompt_tokens":     u.get("prompt_tokens") or u.get("input_tokens", 0),
                "completion_tokens": u.get("completion_tokens") or u.get("output_tokens", 0),
                "total_tokens":      u.get("total_tokens", 0),
            }
        # Ollama native format
        if "eval_count" in result:
            return {
                "model":             result.get("model", ""),
                "prompt_tokens":     result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
            }
    return {}


def _gemini_handler(result: Any) -> dict[str, Any]:
    """
    Handles Google Gemini SDK responses (``google-generativeai`` and ``google-genai``).
    Supports both object-style and dict-style responses.
    """
    # google-generativeai: GenerateContentResponse
    u = getattr(result, "usage_metadata", None)
    if u is not None:
        return {
            "model":             getattr(result, "model", ""),
            "prompt_tokens":     getattr(u, "prompt_token_count", 0) or 0,
            "completion_tokens": getattr(u, "candidates_token_count", 0) or 0,
            "total_tokens":      getattr(u, "total_token_count", 0) or 0,
        }
    if isinstance(result, dict):
        u = result.get("usageMetadata", {})
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     u.get("promptTokenCount", 0),
            "completion_tokens": u.get("candidatesTokenCount", 0),
            "total_tokens":      u.get("totalTokenCount", 0),
        }
    return {}


def _mistral_handler(result: Any) -> dict[str, Any]:
    """
    Handles Mistral AI SDK responses (``mistralai`` package).
    Mistral follows the OpenAI response shape closely.
    """
    u = getattr(result, "usage", None)
    if u is not None:
        return {
            "model":             getattr(result, "model", ""),
            "prompt_tokens":     getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens":      getattr(u, "total_tokens", 0),
        }
    if isinstance(result, dict):
        u = result.get("usage", {})
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     u.get("prompt_tokens", 0),
            "completion_tokens": u.get("completion_tokens", 0),
            "total_tokens":      u.get("total_tokens", 0),
        }
    return {}


def _cohere_handler(result: Any) -> dict[str, Any]:
    """
    Handles Cohere SDK responses (``cohere`` package, v2 Chat API).
    """
    # v2 Chat: result.usage.tokens
    u = getattr(result, "usage", None)
    if u is not None:
        tokens = getattr(u, "tokens", None) or getattr(u, "billed_units", None)
        if tokens is not None:
            return {
                "model":             getattr(result, "model", ""),
                "prompt_tokens":     getattr(tokens, "input_tokens", 0) or 0,
                "completion_tokens": getattr(tokens, "output_tokens", 0) or 0,
            }
    if isinstance(result, dict):
        u = result.get("usage", {})
        bt = u.get("tokens", u.get("billed_units", {}))
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     bt.get("input_tokens", 0),
            "completion_tokens": bt.get("output_tokens", 0),
        }
    return {}


def _deepseek_handler(result: Any) -> dict[str, Any]:
    """
    Handles DeepSeek API responses.
    DeepSeek uses an OpenAI-compatible response shape.
    """
    # DeepSeek is OpenAI-compatible, delegate to openai handler
    usage = _openai_handler(result)
    if not usage.get("model") and isinstance(result, dict):
        usage["model"] = result.get("model", "")
    return usage


def _azure_openai_handler(result: Any) -> dict[str, Any]:
    """
    Handles Azure OpenAI responses via the ``openai`` SDK with Azure backend.
    Azure responses are structurally identical to OpenAI — we delegate and
    normalise the model name to include the 'azure/' prefix for cost lookup.
    """
    usage = _openai_handler(result)
    model = usage.get("model", "")
    if model and not model.startswith("azure/"):
        usage["model"] = f"azure/{model}"
    return usage


def _qwen_handler(result: Any) -> dict[str, Any]:
    """
    Handles Alibaba Cloud Qwen (通义千问) API responses.
    Supports the DashScope SDK (``dashscope`` package) and the
    OpenAI-compatible Qwen endpoint.
    """
    # DashScope SDK response
    output = getattr(result, "output", None)
    usage = getattr(result, "usage", None)
    if usage is not None:
        return {
            "model":             getattr(result, "model", ""),
            "prompt_tokens":     getattr(usage, "input_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "output_tokens", 0) or 0,
            "total_tokens":      getattr(usage, "total_tokens", 0) or 0,
        }
    if isinstance(result, dict):
        u = result.get("usage", {})
        return {
            "model":             result.get("model", ""),
            "prompt_tokens":     u.get("input_tokens", 0),
            "completion_tokens": u.get("output_tokens", 0),
            "total_tokens":      u.get("total_tokens", 0),
        }
    return {}


def _baidu_handler(result: Any) -> dict[str, Any]:
    """
    Handles Baidu ERNIE (文心一言) API responses.
    ERNIE Bot API returns usage in ``usage`` dict with
    ``prompt_tokens`` and ``completion_tokens`` fields.
    """
    if isinstance(result, dict):
        u = result.get("usage", {})
        return {
            "model":             result.get("model", "ernie"),
            "prompt_tokens":     u.get("prompt_tokens", 0),
            "completion_tokens": u.get("completion_tokens", 0),
            "total_tokens":      u.get("total_tokens", 0),
        }
    u = getattr(result, "usage", None)
    if u is not None:
        return {
            "prompt_tokens":     getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
        }
    return {}


# ── Handler registry — add new providers here ─────────────────────────────────
_HANDLERS: dict[str, Any] = {
    "openai":      _openai_handler,
    "anthropic":   _anthropic_handler,
    "bedrock":     _bedrock_handler,
    "huggingface": _huggingface_handler,
    "generic":     _generic_handler,
    # Aliases
    "aws":         _bedrock_handler,
    "hf":          _huggingface_handler,
    "ollama":      _generic_handler,
    "vllm":        _generic_handler,
    "lmstudio":    _generic_handler,
    # New global providers
    "gemini":      _gemini_handler,
    "google":      _gemini_handler,
    "mistral":     _mistral_handler,
    "mistralai":   _mistral_handler,
    "cohere":      _cohere_handler,
    "deepseek":    _deepseek_handler,
    "azure":       _azure_openai_handler,
    "azureopenai": _azure_openai_handler,
    "qwen":        _qwen_handler,
    "alibaba":     _qwen_handler,
    "baidu":       _baidu_handler,
    "ernie":       _baidu_handler,
}


def register_provider(name: str, handler) -> None:
    """
    Register a custom provider handler at runtime.

    Args:
        name:    Provider name string used in ``@observe(provider=...)``.
        handler: Callable ``(result: Any) -> dict`` returning normalised usage.

    Example::

        from ai_obs.providers import register_provider

        def my_provider_handler(result):
            return {"prompt_tokens": result["in"], "completion_tokens": result["out"]}

        register_provider("myprovider", my_provider_handler)
    """
    _HANDLERS[name.lower()] = handler
