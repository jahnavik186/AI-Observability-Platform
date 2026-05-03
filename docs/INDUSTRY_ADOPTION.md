# Industry Adoption Guide

`ai-obs` is most useful when a team already has LLM calls in production or
pre-production and needs operational confidence.

## Universal Questions

- Which model calls are slow?
- Which endpoints are failing?
- How much are prompts and completions costing?
- Are quality scores improving or drifting?
- Can the team inspect telemetry without sending it to a hosted vendor?

## Healthcare

Start with metadata-only telemetry. Track latency, errors, model usage, and
quality scores. Keep prompt and completion capture disabled unless your team has
approved storage, redaction, retention, and access controls.

## Finance

Use environment, endpoint, provider, model, latency, token, and cost dimensions
to monitor internal workflows. Add strict API key handling and database access
controls before production use.

## Legal

Use trace IDs and quality scores to audit answer quality without storing raw
matter details by default. Keep data retention short unless your organization
requires longer audit windows.

## Education

Track tutoring assistant quality by course, endpoint, or model. Use scoring to
compare changes before rolling them out to students.

## Retail and Customer Support

Monitor support bots by latency, failure rate, token spend, endpoint, and model.
Use quality scores to detect when model or prompt changes hurt answer quality.

## SaaS Platforms

Use `ai-obs` to compare providers, models, and prompts before exposing AI
features to customers. Keep telemetry inside your own infrastructure when
customer data policies require it.
