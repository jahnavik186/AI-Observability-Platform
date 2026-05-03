# Security Policy

`ai-obs` is designed for teams that want LLM observability without sending
telemetry to a third-party SaaS by default.

## Supported Versions

Security fixes are currently applied to the `main` branch. Tagged releases will
be listed here after the first public release.

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

Report security issues by emailing the repository maintainer or by using GitHub
private vulnerability reporting if it is enabled for this repository.

Include:

- a short description of the issue
- affected component: SDK, collector, Docker stack, dashboard, or docs
- reproduction steps
- expected and actual behavior
- any logs or request samples with secrets removed

## Data Handling Defaults

- Prompt capture is disabled unless `AI_OBS_CAPTURE_PROMPTS=true`.
- Completion capture is disabled unless `AI_OBS_CAPTURE_COMPLETIONS=true`.
- API key authentication is supported through `AI_OBS_API_KEY`.
- Operators should redact secrets, credentials, health data, financial data, and
  personal data before enabling text capture in production.

## Production Checklist

- Set a collector API key.
- Keep prompt and completion capture disabled unless there is a clear policy.
- Put the collector behind TLS and network access controls.
- Configure database backups and retention.
- Rotate provider keys and collector keys on a regular schedule.
- Review dashboard access before sharing Grafana externally.
