# Spec: `resilience-store` (T13b)

- **Feature:** `service-resilience`
- **PRD:** `docs/planning/service-resilience/prd.md` (§ M1)
- **Boundary:** the SQLite schema/status/attempts/cancel/recovery/counts/pragmas. No HTTP/worker.

## In-scope requirements

- `runs` gains `attempts INTEGER NOT NULL DEFAULT 0` and `cancel_requested INTEGER NOT NULL DEFAULT 0`;
  status adds `cancelled`; `Run` gains `attempts: int = 0`, `cancel_requested: bool = False` and
  `to_dict` exposes them.
- A fresh DB creates the columns; an existing T13a DB is migrated with `ALTER TABLE ... ADD COLUMN`
  when `PRAGMA table_info(runs)` lacks them.
- `claim_next`: sets running/started_at and `attempts = attempts + 1`, atomically under the lock.
- `requeue(id)`: only a running run -> queued, clears started/finished/exit/report/error, keeps
  attempts; a non-running run is a `ValueError`.
- `finish` accepts `succeeded|failed|cancelled`.
- `request_cancel(id) -> Run | None`: queued -> `cancelled` + finished_at; running ->
  `cancel_requested=1` (status stays running); a terminal run is returned unchanged; unknown -> None.
- `cancel_requested(id) -> bool`.
- `counts() -> dict[str,int]` with all five statuses (zeros included).
- `recover() -> int`: running + cancel_requested -> `cancelled` + finished_at; other running ->
  queued (clear started); return the number recovered.
- On open: `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, `foreign_keys=ON`.

## Out-of-scope

- The runner/worker/API/CLI.
- A Postgres store, retention, migrations beyond the additive columns.

## Acceptance criteria

- **AC1 — Schema.** A fresh DB has the new columns/status; an old-schema DB gains the columns on open;
  `to_dict` round-trips attempts/cancel_requested.
- **AC2 — Attempts.** A claim increments attempts exactly once; a requeue keeps the count; a finish
  keeps it.
- **AC3 — Cancel.** Queued -> cancelled/finished_at; running -> flag only; terminal unchanged; unknown
  None; `cancel_requested` reads the flag.
- **AC4 — Recovery.** Running rows return to queued (clear started) or cancelled when requested; the
  count is right; queued/terminal rows are untouched.
- **AC5 — Counts.** Five statuses, zeros included, updates on transitions.
- **AC6 — Pragmas.** WAL/busy_timeout/synchronous/foreign_keys are set on open.
- **AC7 — Regression.** All prior store tests green; the lock serializes.

## Dependencies and sequencing

- First; `resilience-service` consumes it.
- Stdlib only; the additive migration keeps T13a DBs usable.
