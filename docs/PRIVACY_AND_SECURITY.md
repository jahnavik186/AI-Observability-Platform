# Privacy and Security

`ai-obs` is privacy-first, not privacy-magic. It gives teams defaults and knobs
that make safer deployments easier, but production users still need clear data
handling rules.

## Defaults

Prompt and completion capture are disabled by default:

```bash
AI_OBS_CAPTURE_PROMPTS=false
AI_OBS_CAPTURE_COMPLETIONS=false
```

With those defaults, teams can still monitor latency, token usage, estimated
cost, errors, model names, providers, endpoints, environments, and quality
scores.

## When To Enable Text Capture

Only enable prompt or completion capture when you have:

- approval to store the data
- a retention policy
- access controls around the database and dashboards
- redaction for secrets and personal data
- a clear reason that metadata-only telemetry is not enough

## Industry Notes

Healthcare, finance, legal, education, and enterprise SaaS deployments should
start with metadata-only telemetry. Add text capture only after reviewing local
privacy, compliance, and customer requirements.

## Recommended Production Controls

- Set `AI_OBS_API_KEY` and require it from SDK clients.
- Run the collector behind TLS.
- Restrict Grafana and database access.
- Store secrets in a secret manager, not in committed `.env` files.
- Define retention for traces, scores, and dashboard data.
- Add redaction before events leave the application process.

## What This Project Does Not Claim

This project is not a compliance certification and does not make a deployment
HIPAA, SOC 2, GDPR, or PCI compliant by itself. It is a self-hosted foundation
that teams can adapt to their own controls.
