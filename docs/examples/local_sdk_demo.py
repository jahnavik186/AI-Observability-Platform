r"""
Local SDK demo for the ai-obs stack running on localhost.

Run from the repo root with:

    $env:PYTHONPATH="c:\Users\shahj\Documents\GitHub\GitHub\TelemetryAI\sdk"
    $env:AI_OBS_ENDPOINT="http://localhost:8080"
    $env:AI_OBS_ENV="development"
    & "c:\Users\shahj\Documents\GitHub\.venv\Scripts\python.exe" `
      "c:\Users\shahj\Documents\GitHub\GitHub\TelemetryAI\docs\examples\local_sdk_demo.py"
"""

from __future__ import annotations

from ai_obs import get_client, observe, score


@observe(
    model="demo-local-model",
    provider="generic",
    endpoint="demo-local-script",
    capture_trace_id=True,
    tags={"app": "local-sdk-demo", "feature": "hello-world"},
)
def ask(prompt: str, *, _trace_id: str = "") -> tuple[str, str]:
    answer = f"Echo: {prompt}"
    return answer, _trace_id


def main() -> None:
    answer, trace_id = ask("TelemetryAI local SDK demo")
    print("answer:", answer)
    print("trace_id:", trace_id)

    score(
        trace_id=trace_id,
        value=1.0,
        label="correct",
        metadata={"source": "local_sdk_demo.py"},
    )

    # Force a synchronous flush so the event and score are visible immediately.
    get_client().flush()
    print("flushed trace and score to the collector")


if __name__ == "__main__":
    main()
