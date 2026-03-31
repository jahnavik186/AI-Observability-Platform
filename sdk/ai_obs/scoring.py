"""
Accuracy scoring — manual and LLM-as-judge.

Manual::

    from ai_obs import score
    score(trace_id="abc-123", value=1.0, label="correct")
    score(trace_id="abc-124", value=0.0, label="hallucination")

LLM-as-judge (fires async, zero blocking latency)::

    from ai_obs import autoscore
    autoscore(
        trace_id="abc-125",
        question="What year did WW2 end?",
        answer="1944",
        reference="1945",
    )
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

from ai_obs.client import get_client
from ai_obs.config import config

logger = logging.getLogger("ai_obs")

_JUDGE_SYSTEM = (
    "You are a strict, objective AI quality evaluator. "
    "You receive a question, a reference answer, and a model answer. "
    "Your job is to score how correct the model answer is."
)

_JUDGE_PROMPT = """\
Question: {question}

Reference answer: {reference}

Model answer: {answer}

Score the model answer from 0.0 (completely wrong or hallucinated) to 1.0 (perfect match with the reference).
Consider partial credit for partially correct answers.

Respond ONLY with valid JSON — no prose, no markdown:
{{"score": <float 0.0-1.0>, "reasoning": "<one concise sentence explaining your score>"}}
"""


def score(
    *,
    trace_id: str,
    value: float,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Submit a manual accuracy score for a completed trace.

    The score is queued and sent to the collector on the next flush cycle.

    Args:
        trace_id: The trace ID from the ``@observe`` decorator.
        value:    Float 0.0 (wrong) to 1.0 (perfect). Clamped automatically.
        label:    Optional string tag. Use it consistently for filtering in
                  Grafana, e.g. ``"correct"``, ``"partial"``, ``"hallucination"``,
                  ``"off-topic"``.
        metadata: Arbitrary extra data stored with the score (e.g. annotator name).
    """
    if config.disabled:
        return

    event = {
        "type": "score",
        "trace_id": trace_id,
        "score": round(max(0.0, min(1.0, float(value))), 6),
        "label": label,
        "metadata": metadata or {},
        "env": config.env,
    }
    get_client().enqueue(event)


def autoscore(
    *,
    trace_id: str,
    question: str,
    answer: str,
    reference: str,
    judge_model: str = "gpt-4o-mini",
    judge_provider: str = "openai",
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Automatically score a model answer using a second LLM as judge.

    Fires asynchronously — no latency impact on your application.
    The score appears in Grafana within seconds.

    Requires the judge provider SDK to be installed:
    - OpenAI judge: ``pip install openai``
    - Anthropic judge: ``pip install anthropic``

    Args:
        trace_id:       Trace to attach the score to.
        question:       The original question posed to the model.
        answer:         The model's answer to evaluate.
        reference:      A known-good reference answer.
        judge_model:    LLM to use as judge. Defaults to ``gpt-4o-mini``
                        (cheap + accurate for evaluation).
        judge_provider: ``"openai"`` or ``"anthropic"``.
        metadata:       Extra fields stored with the score.
    """
    if config.disabled:
        return

    def _run() -> None:
        try:
            result = _call_judge(
                question=question,
                answer=answer,
                reference=reference,
                model=judge_model,
                provider=judge_provider,
            )
            score(
                trace_id=trace_id,
                value=result["score"],
                label="autoscore",
                metadata={
                    "reasoning": result.get("reasoning", ""),
                    "judge_model": judge_model,
                    **(metadata or {}),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("ai-obs autoscore failed for trace %s: %s", trace_id, exc)

    threading.Thread(target=_run, daemon=True, name="ai-obs-autoscore").start()


def _call_judge(
    *, question: str, answer: str, reference: str, model: str, provider: str
) -> dict[str, Any]:
    prompt = _JUDGE_PROMPT.format(question=question, answer=answer, reference=reference)

    if provider == "openai":
        from openai import OpenAI  # type: ignore
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0,
            max_tokens=256,
        )
        raw = resp.choices[0].message.content or "{}"

    elif provider == "anthropic":
        import anthropic  # type: ignore
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model,
            system=_JUDGE_SYSTEM,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text

    else:
        raise ValueError(f"autoscore: unsupported judge provider '{provider}'. Use 'openai' or 'anthropic'.")

    return _parse_judge_response(raw)


def _parse_judge_response(raw: str) -> dict[str, Any]:
    """Robustly extract JSON from LLM judge output."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try to extract the first {...} block
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    # Last resort: return a neutral score with an error note
    logger.debug("ai-obs: could not parse judge response: %s", raw[:200])
    return {"score": 0.5, "reasoning": "judge response parse error"}
