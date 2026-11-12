# Spec: `resilience-service` (T13b)

- **Feature:** `service-resilience`
- **PRD:** `docs/planning/service-resilience/prd.md` (§ M2–M6)
- **Boundary:** runner cancel, worker retries/cancel, N workers, API cancel/metrics, CLI flags,
  docs/tests. No store internals.

## In-scope requirements

- **Runner.** `CommandRunner` uses `subprocess.Popen` (new session/process group) with an injectable
  `popen`; `run(bundle, cancel=None)` polls `communicate(timeout=poll)`:
  - cancel predicate true -> terminate/kill the group, `Outcome(..., cancelled=True)`.
  - the total timeout -> terminate/kill, the existing timeout error.
  - completion -> the existing exit/JSON/stderr parsing.
  - `Outcome` gains `cancelled: bool = False`.
- **Worker.** `Worker(store, execute, *, poll=1.0, retries=0)`:
  - claim; execute; `cancelled`/cancel_requested -> finish `cancelled`.
  - a report (exit 0/1) -> succeeded/failed (never retried).
  - no report and `run.attempts <= retries` -> `store.requeue`; else finish failed.
  - an exception -> the same no-report path.
  - N instances share the store; `start/stop` per instance.
- **API.** `Api(..., workers=1)`:
  - `POST /runs/{id}/cancel` (bearer): 202 `{"id","status":"cancelled"|"cancelling"}`; 404 unknown;
    409 with the terminal status.
  - `GET /metrics` (bearer): Prometheus text with `tenon_runs{status=...}` for all five statuses and
    `tenon_workers N`; `Content-Type: text/plain; version=0.0.4; charset=utf-8`.
- **CLI.** `--workers` (1..16, default 1) and `--retries` (0..10, default 0), named usage errors;
  `_serve` calls `store.recover()`, builds N workers, starts/stops all, passes the count to the API.
- **Docs.** README/DEPLOYMENT/ARCHITECTURE: the flags, cancel semantics, retry safety, the metrics
  scrape config, recovery, and the POSIX process-group caveat.
- **Tests.** Runner cancel/timeout (fake Popen), worker retry/no-retry-report/cancel, N workers
  processing N runs exactly once, API cancel/metrics/auth/404/409, CLI flags, an end-to-end retry and
  cancel. Offline.

## Out-of-scope

- Store internals; Postgres; rate limiting; per-run retries/backoff; webhook triggers.

## Acceptance criteria

- **AC1 — Worker retries.** A no-report failure retries up to `--retries` then fails; a report-bearing
  failure is never retried; attempts are visible; a cancelled outcome is terminal.
- **AC2 — Cancel.** The API marks a queued run cancelled and a running run cancelling; the runner
  terminates the process group; the worker finishes cancelled; terminal/unknown are 409/404.
- **AC3 — Workers.** N workers process N queued runs once each; the default is 1; the CLI validates
  the bounds.
- **AC4 — Metrics.** The endpoint is bearer-guarded, returns Prometheus text with the five status
  gauges and the worker count.
- **AC5 — Recovery/CLI.** `_serve` recovers stranded runs and starts N workers.
- **AC6 — Docs/regression.** Docs updated; all prior tests green.
