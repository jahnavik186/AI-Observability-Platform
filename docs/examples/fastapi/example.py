"""
FastAPI middleware example — auto-instrument every route.

Install: pip install ai-obs-sdk fastapi uvicorn openai
Run:     uvicorn example:app --reload
"""
from fastapi import FastAPI
from openai import OpenAI
from ai_obs import observe
from ai_obs.middleware import AIObsMiddleware

app = FastAPI()
client = OpenAI()

# ── Add middleware — instruments ALL routes automatically ─────────────────────
app.add_middleware(
    AIObsMiddleware,
    provider="openai",
    model="gpt-4o-mini",
    skip_paths=["/health", "/docs", "/redoc"],
)


# ── Routes — no changes needed, middleware handles observability ──────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(prompt: str):
    # The @observe decorator adds model-level telemetry on top of the middleware
    @observe(model="gpt-4o-mini", provider="openai")
    def _call(p):
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": p}],
        )
        return resp.choices[0].message.content

    return {"reply": _call(prompt)}


@app.post("/summarise")
def summarise(text: str):
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Summarise in one sentence."},
            {"role": "user",   "content": text},
        ],
    )
    return {"summary": resp.choices[0].message.content}


# ─────────────────────────────────────────────────────────────────────────────
"""
LangChain callback handler example.

Install: pip install ai-obs-sdk langchain-openai
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from ai_obs.middleware import AIObsCallbackHandler

handler = AIObsCallbackHandler(
    provider="openai",
    tags={"framework": "langchain", "version": "0.2"},
)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    callbacks=[handler],      # <── just add the handler
)


def ask_langchain(question: str) -> str:
    response = llm.invoke([HumanMessage(content=question)])
    return response.content


if __name__ == "__main__":
    print(ask_langchain("What is LangChain?"))
