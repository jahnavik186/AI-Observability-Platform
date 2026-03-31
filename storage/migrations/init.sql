-- ═══════════════════════════════════════════════════════════════════════════
-- ai-obs database schema
-- Runs automatically on first docker compose up
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Events ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_events (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id          VARCHAR(64)  NOT NULL,
    model             VARCHAR(128) NOT NULL,
    provider          VARCHAR(64)  NOT NULL,
    endpoint          VARCHAR(256),
    env               VARCHAR(64)  DEFAULT 'production',
    latency_ms        DOUBLE PRECISION,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    cost_usd          DOUBLE PRECISION,
    error             VARCHAR(2048),
    prompt            VARCHAR(4096),        -- optional, privacy opt-in
    completion        VARCHAR(4096),        -- optional, privacy opt-in
    tags              JSONB        DEFAULT '{}',
    timestamp_utc     VARCHAR(32),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Indexes for common Grafana time-range query patterns
CREATE INDEX IF NOT EXISTS ix_events_trace       ON ai_events (trace_id);
CREATE INDEX IF NOT EXISTS ix_events_model       ON ai_events (model);
CREATE INDEX IF NOT EXISTS ix_events_provider    ON ai_events (provider);
CREATE INDEX IF NOT EXISTS ix_events_env         ON ai_events (env);
CREATE INDEX IF NOT EXISTS ix_events_created     ON ai_events (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_created_model    ON ai_events (created_at, model);
CREATE INDEX IF NOT EXISTS ix_events_model_provider   ON ai_events (model, provider);
-- BRIN index for very fast time-range scans on large tables
CREATE INDEX IF NOT EXISTS ix_events_created_brin ON ai_events USING BRIN (created_at);

-- ── Scores ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_scores (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id   VARCHAR(64)  NOT NULL,
    score      DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    label      VARCHAR(128),
    metadata   JSONB        DEFAULT '{}',
    env        VARCHAR(64)  DEFAULT 'production',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_scores_trace   ON ai_scores (trace_id);
CREATE INDEX IF NOT EXISTS ix_scores_created ON ai_scores (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_scores_label   ON ai_scores (label);

-- ── Seed demo data ────────────────────────────────────────────────────────────
-- Generates realistic-looking telemetry so dashboards look populated on first boot.
-- Safe to delete: this data is for demo purposes only.

DO $$
DECLARE
    i        INTEGER;
    providers TEXT[] := ARRAY['openai','anthropic','bedrock','huggingface','generic'];
    models    TEXT[] := ARRAY[
        'gpt-4o',
        'gpt-4o-mini',
        'claude-sonnet-4-6',
        'claude-haiku-4-5-20251001',
        'amazon.titan-text-express-v1',
        'meta-llama/Llama-3-8B-Instruct',
        'llama3:8b'
    ];
    model_provider_map JSONB := '{
        "gpt-4o":                           "openai",
        "gpt-4o-mini":                      "openai",
        "claude-sonnet-4-6":                "anthropic",
        "claude-haiku-4-5-20251001":        "anthropic",
        "amazon.titan-text-express-v1":     "bedrock",
        "meta-llama/Llama-3-8B-Instruct":   "huggingface",
        "llama3:8b":                        "generic"
    }';
    endpoints TEXT[] := ARRAY['chat','summarise','classify','extract','translate','embed'];
    envs      TEXT[] := ARRAY['production','staging','development'];
    m TEXT; p TEXT; e TEXT; ep TEXT;
    lat DOUBLE PRECISION; pt INTEGER; ct INTEGER; cost DOUBLE PRECISION;
    has_error BOOLEAN; err_msg TEXT;
BEGIN
    -- 1 000 events spread over the past 14 days
    FOR i IN 1..1000 LOOP
        m  := models[1 + floor(random() * array_length(models, 1))::int];
        p  := model_provider_map ->> m;
        e  := envs[1 + floor(random() * 3)::int];
        ep := endpoints[1 + floor(random() * array_length(endpoints, 1))::int];

        -- Realistic latency: fast models fast, slow models slow
        lat := CASE p
            WHEN 'openai'      THEN 150 + random() * 2000
            WHEN 'anthropic'   THEN 200 + random() * 3000
            WHEN 'bedrock'     THEN 300 + random() * 4000
            WHEN 'huggingface' THEN 500 + random() * 5000
            ELSE                    100 + random() * 1500
        END;

        pt   := 30  + floor(random() * 900)::int;
        ct   := 20  + floor(random() * 500)::int;
        cost := CASE p
            WHEN 'openai'    THEN ROUND((pt * 0.000005 + ct * 0.000015)::numeric, 8)
            WHEN 'anthropic' THEN ROUND((pt * 0.000003 + ct * 0.000015)::numeric, 8)
            ELSE                  ROUND((pt * 0.000001 + ct * 0.000002)::numeric, 8)
        END;

        has_error := random() > 0.97;
        err_msg   := CASE WHEN has_error THEN
            (ARRAY[
                'RateLimitError: quota exceeded',
                'TimeoutError: model did not respond within 30s',
                'InvalidRequestError: maximum context length exceeded',
                'ServiceUnavailableError: upstream model unavailable'
            ])[1 + floor(random() * 4)::int]
        ELSE NULL END;

        INSERT INTO ai_events (
            trace_id, model, provider, endpoint, env,
            latency_ms, prompt_tokens, completion_tokens, total_tokens,
            cost_usd, error, tags, created_at
        ) VALUES (
            gen_random_uuid()::text,
            m, p, ep, e,
            ROUND(lat::numeric, 2), pt, ct, pt + ct,
            CASE WHEN has_error THEN NULL ELSE cost END,
            err_msg,
            jsonb_build_object('seed', 'true'),
            now() - (random() * INTERVAL '14 days')
        );
    END LOOP;

    -- 200 accuracy scores linked to random events
    FOR i IN 1..200 LOOP
        INSERT INTO ai_scores (trace_id, score, label, env, created_at)
        SELECT
            e.trace_id,
            -- Scores slightly better over time (simulates model improvement)
            ROUND(LEAST(1.0,
                (0.55 + random() * 0.45) +
                (EXTRACT(EPOCH FROM (e.created_at - (now() - INTERVAL '14 days')))
                 / EXTRACT(EPOCH FROM INTERVAL '14 days')) * 0.1
            )::numeric, 4),
            (ARRAY['correct','partial','hallucination','off-topic','autoscore'])[
                1 + floor(random() * 5)::int
            ],
            e.env,
            e.created_at + INTERVAL '2 seconds'
        FROM ai_events e
        WHERE (e.tags->>'seed') = 'true'
        ORDER BY random()
        LIMIT 1;
    END LOOP;

    RAISE NOTICE 'ai-obs: seed data inserted (1000 events, 200 scores)';
END $$;
