"""
OpenAI example — chat completion with full observability.

Install: pip install ai-obs-sdk openai
Run:     AI_OBS_ENDPOINT=http://localhost:8080 python example.py
"""
import os
from openai import OpenAI
from ai_obs import observe, score, autoscore

client = OpenAI()   # reads OPENAI_API_KEY from env


# ── Basic usage ───────────────────────────────────────────────────────────────

@observe(model="gpt-4o-mini", provider="openai", endpoint="chat")
def chat(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


# ── Capture trace_id for scoring ──────────────────────────────────────────────

@observe(model="gpt-4o-mini", provider="openai", endpoint="qa", capture_trace_id=True)
def answer_question(question: str, *, _trace_id: str = "") -> tuple[str, str]:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    )
    answer = resp.choices[0].message.content
    return answer, _trace_id


# ── With tags (for filtering in Grafana) ─────────────────────────────────────

@observe(
    model="gpt-4o",
    provider="openai",
    endpoint="summarise",
    tags={"feature": "document-summary", "team": "product"},
)
def summarise(text: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Summarise the following in 2 sentences."},
            {"role": "user",   "content": text},
        ],
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    # 1. Simple chat
    reply = chat("What is the Pythagorean theorem?")
    print("Chat reply:", reply[:100])

    # 2. QA with scoring
    question = "What year did the Berlin Wall fall?"
    reference = "1989"
    answer, trace_id = answer_question(question)
    print(f"Answer: {answer[:80]}  (trace: {trace_id})")

    # Manual score
    is_correct = "1989" in answer
    score(trace_id=trace_id, value=1.0 if is_correct else 0.0, label="correct" if is_correct else "wrong")
    print(f"Scored {'correct' if is_correct else 'wrong'}")

    # Auto-score (fires async — check Grafana Accuracy dashboard)
    autoscore(trace_id=trace_id, question=question, answer=answer, reference=reference)
    print("Autoscore dispatched (check Grafana)")
