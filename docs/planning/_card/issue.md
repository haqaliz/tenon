# Card: feat/service-deploy

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T13 Hardened deployment** — the operational follow-up to the T10e service MVP
- **Milestone:** next phase after T12; the original roadmap ends at T11
- **Branch:** `feat/service-deploy/aliz`
- **Worktree:** `.claude/worktrees/feat-service-deploy`

## Brief

`tenon provider serve` is a local-first MVP: one process, one worker, SQLite, a bearer token and a
webhook HMAC, with no TLS, container, readiness, retries/cancel or metrics. A provider cannot deploy
it as-is.

T13 makes the service deployable and resilient, in two slices:
- **T13a — deployable service:** a non-root Docker image, a Compose stack with the service plus a
  TLS-terminating proxy, volumes for the DB/bundles, env/secret wiring, health/readiness, and a
  deployment/backup/rotation guide. No secrets baked into the image.
- **T13b — service resilience:** bounded parallel workers, run retries, a cancel endpoint, a
  Prometheus `/metrics` endpoint and SQLite WAL/busy-timeout hardening (or Postgres, if chosen).

The hard rules do not change: the service never merges or pushes the default branch; the app identity
and T5 gates stay; secrets never appear in images, logs, the DB or responses; no cloud-specific IaC or
SaaS control plane.

## Constraints carried in from the repo

- The T10e `RunStore`/`Worker`/`Api`/`http.serve` seams are the base; extend, do not fork the policy.
- Stdlib only unless a chosen slice needs an optional dependency (e.g. a Postgres driver).
- Offline tests; Docker/Compose artifacts are deployment files, not run in the test suite.
- `CLAUDE.md` §1–5: no egress by default, honest levels, no merge/default branch.

## Scope fence

Not this card: a SaaS control plane, multi-tenant auth, a web UI, Kubernetes unless chosen, cloud
IaC, new locators/provider capabilities.
