# Card: feat/service-resilience

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T13 Hardened deployment** — second slice: **service resilience** (T13b)
- **Milestone:** next phase after T12; T13a (deployable service) shipped
- **Branch:** `feat/service-resilience/aliz`
- **Worktree:** `.claude/worktrees/feat-service-resilience`

## Brief

The T13a service is deployable but still one worker, one attempt, no cancel and no metrics; SQLite
runs with the default journal.

T13b adds **service resilience**:
- bounded **parallel workers** (`--workers N`, default 1) that claim runs atomically;
- **run retries** (`--retries N`, default 0): a failed/timed-out run is re-queued with an attempt
  count until the budget is exhausted, then failed;
- a **cancel endpoint** for a queued or running run (the running CLI subprocess is terminated);
- a Prometheus **`/metrics`** endpoint (run counts by status, queue depth), bearer-guarded;
- **SQLite hardening**: WAL, a busy timeout, `synchronous=NORMAL` and `foreign_keys=ON`;
- the store/API/worker/CLI tests and docs.

The hard rules do not change: one code path (the shipped CLI), no merge/default branch, secrets never
logged/stored, no new proof/locator behavior, no Postgres or cloud-specific infrastructure.

## Constraints carried in from the repo

- T10e/T13a's `RunStore`/`Worker`/`Api`/`CommandRunner` and the Compose deployment are the base.
- Stdlib only (`sqlite3`, `threading`, `subprocess`, `time`); no new dependency.
- Offline tests; no Docker/network; a cancel test may use a short-lived local subprocess or a fake.
- `CLAUDE.md` §1–5: execution decides, honest levels, no merge/default branch.

## Scope fence

Not this card: Postgres, Kubernetes/cloud IaC, a web UI, multi-tenant auth, webhook-triggered runs,
new locators/provider features, rate limiting (the proxy owns it).
