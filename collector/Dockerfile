# ── Stage 1: build deps ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ai-obs-collector"
LABEL org.opencontainers.image.description="Telemetry collector for the ai-obs AI observability platform"
LABEL org.opencontainers.image.source="https://github.com/your-org/ai-obs"
LABEL org.opencontainers.image.licenses="MIT"

# Non-root user for security
RUN useradd --create-home --shell /bin/bash aiobs
WORKDIR /app

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --chown=aiobs:aiobs . .

USER aiobs

EXPOSE 8080

# Healthcheck for Docker / compose
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/v1/health')"

# 2 workers by default; override with WORKERS env var for horizontal scale
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers ${WORKERS:-2}"]
