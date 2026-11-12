# PRD: Service resilience (T13b)

- **Slug:** `service-resilience`
- **Capability:** **T13 Hardened deployment** — **second slice: service resilience**
- **Milestone:** next phase after T12; T13a (deployable service) shipped 2026-11-12
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

The T13a service is deployable but still one worker, one attempt, no cancel and no metrics; a run
stranded by a restart stays `running`, and SQLite uses the default journal. A provider cannot operate
it at any real queue depth.

T13b adds **service resilience**:
- bounded **parallel workers** (`--workers N`, default 1) sharing the atomic store claim;
- **retries** (`--retries N`, default 0) for runs that could not complete (timeout/exit 2/exception/
  invalid report), with an attempt count;
- **cancel** for a queued or running run (the running CLI subprocess is terminated);
- a bearer-guarded Prometheus **`/metrics`** endpoint (run counts by status, queue depth, workers);
- **startup recovery** of runs stranded `running` by a restart (re-queue, or cancel if a cancel was
  requested);
- **SQLite hardening**: WAL, a busy timeout, `synchronous=NORMAL`, `foreign_keys=ON`.

A run that produced a report (exit 0/1) is terminal: retries never re-run a completed fan-out, so an
already-opened PR is not duplicated or refused by a retry. A cancelled run is terminal and never
retried.

The hard rules do not change: one code path (the shipped CLI), no merge/default branch, secrets never
logged/stored, no new proof/locator behavior, no Postgres/cloud infrastructure.

**For whom:** the operator running the service, the provider watching queue depth and failures, and
the customer whose PRs are never duplicated by a retry.

## Goals & Success Metrics

1. **N workers.** `--workers N` runs N threads; each run is claimed once; the default is 1.
2. **Safe retries.** Only a run with no report is re-queued; attempts are visible; a report-bearing
   run is never retried.
3. **Cancel.** A queued run becomes `cancelled`; a running run gets a cancel request, the CLI process
   group is terminated and the run finishes `cancelled`.
4. **Metrics.** `GET /metrics` (bearer) returns Prometheus text with run counts by status and the
   worker count.
5. **Recovery.** After a restart, stranded `running` runs are re-queued (or cancelled if requested).
6. **Durable SQLite.** WAL/busy timeout/synchronous/foreign keys are set on open; tests assert them.
7. **Offline tests.** Store/worker/runner/API/CLI tests with fakes and a short local subprocess; no
   network.

## Requirements

### Must have

- **M1 — Store.** `runs` gains `attempts INTEGER NOT NULL DEFAULT 0` and
  `cancel_requested INTEGER NOT NULL DEFAULT 0`; status adds `cancelled`; `Run.to_dict()` exposes
  both. `claim_next` increments `attempts` and sets running; `requeue` (queued, clears
  started/finished/exit/report/error, keeps attempts); `finish` accepts `cancelled`;
  `request_cancel` (queued -> cancelled + finished_at; running -> cancel_requested=1; terminal ->
  a terminal marker); `cancel_requested(id)`; `counts()` (status -> count);
  `recover()` (running -> queued or cancelled-with-finished_at when cancel_requested); the pragmas on
  open. All under the existing lock.
- **M2 — Runner cancel.** `CommandRunner` uses `subprocess.Popen` with a new session/process group;
  a cancel predicate is polled while waiting; a cancel or timeout terminates/kills the group and
  returns `Outcome(..., cancelled=True)` or a timeout error; the CLI's JSON/report parsing is
  unchanged; the command is injectable.
- **M3 — Worker.** `Worker(store, execute, *, poll, retries=0)`:
  - `run_once`: claim; execute; if cancelled -> finish `cancelled`; if a report exists (exit 0/1) ->
    succeeded/failed; if no report and `run.attempts <= retries` -> `requeue`; else finish failed.
  - A retry re-claims with attempts+1; a report-bearing run is never retried.
  - `start()/stop()` per worker; N instances share the store.
- **M4 — API.**
  - `POST /runs/{id}/cancel` (bearer): 202 `{"id","status":"cancelled"|"cancelling"}`; 404 unknown;
    409 with the terminal status for a finished run.
  - `GET /metrics` (bearer): Prometheus text `tenon_runs{status="queued|running|succeeded|failed|cancelled"} N`
    and `tenon_workers N`; `Content-Type: text/plain; version=0.0.4; charset=utf-8`.
  - `/ready` and `/health` unchanged.
- **M5 — CLI.** `--workers` (1..16, default 1) and `--retries` (0..10, default 0), validated with
  named usage errors; `_serve` calls `store.recover()`, builds N workers, starts/stops all and passes
  the worker count to the API.
- **M6 — Docs/tests.** Store transitions/pragmas/recovery; the runner cancel/timeout with a short
  local process and a fake Popen; the worker retry/cancel/N-worker cases; the API cancel/metrics;
  the CLI flags; an end-to-end retry and cancel. README/DEPLOYMENT/ARCHITECTURE document the flags,
  metrics scrape, cancel semantics and retry safety. Offline.

### Should have

- **S1 — No duplicate PRs.** A report-bearing run is terminal; retries only cover infrastructure
  failures.
- **S2 — Visible attempts.** The run record shows attempts and cancel_requested.
- **S3 — Clean shutdown.** Stopping the service stops the workers; a running child is killed by the
  process group.

### Nice to have

- **N1 — Exponential backoff**; a later card.
- **N2 — Per-run retries**; a later card.
- **N3 — Rate limiting**; the proxy owns it.

## Data Model

```
Run adds
  attempts: int = 0             # started attempts; 1 after the first claim
  cancel_requested: bool = False

Status: queued|running|succeeded|failed|cancelled
```

`request_cancel` on a queued run sets `cancelled`/`finished_at`; on a running run sets
`cancel_requested`; the worker finishes it `cancelled`.

## API Contract

```http
POST /runs/ab12.../cancel
Authorization: Bearer <token>
-> 202 {"id":"ab12...","status":"cancelling"}

GET /metrics
Authorization: Bearer <token>
-> 200 text/plain
tenon_runs{status="queued"} 1
tenon_runs{status="running"} 2
...
tenon_workers 2
```

## Technical Considerations

- **Why retries only without a report.** A completed fan-out has opened branches/PRs; re-running it
  would refuse existing branches and confuse the report. A timeout/exit 2/exception produced nothing
  to duplicate.
- **Why Popen + a process group.** A blocking `subprocess.run` cannot be cancelled; a new session
  lets a cancel/timeout kill the CLI and its git children.
- **Why N Worker instances.** The store's lock/atomic claim already serializes; N threads share it
  without a new pool abstraction.
- **Why recovery on start.** A kill left a `running` row; without recovery it is stuck forever.
- **Why WAL/busy timeout.** Multiple worker threads and request threads share SQLite; WAL + a busy
  timeout avoids lock errors.

## Risks & Open Questions

- **Retry semantics.** A run that failed after opening some PRs (exit 1) is not retried; the operator
  re-posts it knowingly. Retries only cover infrastructure failures.
- **Cancel cleanup.** A SIGTERM can skip the CLI's temp-dir cleanup; the container `/tmp` is a
  tmpfs, and a later pass can clean stale dirs. The DB/report is unaffected.
- **Process groups are POSIX.** Windows is not a target.
- **Parallel token/rate limits.** N workers clone/push concurrently; the app token/API rate limits are
  the operator's concern. The default stays 1.
- **Metrics cardinality.** One gauge per status plus workers; no per-provider labels.
- **Open question — should a cancelled run be retried?** No; cancel is terminal.
- **Open question — should `/metrics` be public?** No; it is bearer-guarded; Prometheus sends the
  token.

## Out of Scope

- Postgres, Kubernetes/cloud IaC, a web UI, multi-tenant auth, webhook-triggered runs, rate limiting.
- Per-run retries, backoff schedules, dead-letter queues.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `resilience-store` | Schema/status/attempts/cancel/recovery/counts/pragmas and the store tests. No HTTP/worker. |
| `resilience-service` | Runner Popen/cancel, worker retries/cancel/N workers, API cancel/metrics, CLI flags, docs/tests. No store internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | One worker, no retries/cancel/metrics/recovery is not operable. |
| User understanding | 🟢 | Operator/provider/customer; retry safety is explicit. |
| Success metrics | 🟢 | N workers, safe retries, cancel, metrics, recovery, pragmas, offline tests. |
| Scope clarity | 🟢 | Service resilience only; Postgres/deployment IaC excluded. |
| Edge cases & risks | 🟡 | Retry duplicate-PR risk, cancel cleanup and POSIX kill are real; documented. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Stdlib threading/Popen/sqlite; no new dependency. |
| Go-to-market | 🟢 | The service becomes operable at a real queue depth. |

**Areas to strengthen before sharing:** retries are deliberately narrow; an operator wanting to
re-run a completed fan-out does so explicitly. The cancel path is POSIX-only and may leave temp
dirs; the container tmpfs bounds it.

**The question I would want answered before greenlighting this:** *If a run times out after opening
10 PRs, does a retry open 10 more?* The answer this card records: a timeout has no report; a retry
re-runs the bundle, but the already-opened branches are per-repo `BRANCH_EXISTS` refusals in the new
report. The service never force-pushes or deletes. A report-bearing exit 1 is not retried at all.
