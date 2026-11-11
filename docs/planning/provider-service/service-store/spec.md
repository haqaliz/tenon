# Spec: `service-store` (T10e)

- **Feature:** `provider-service`
- **PRD:** `docs/planning/provider-service/prd.md` (§ M2)
- **Boundary:** the SQLite schema and `RunStore`. No HTTP, worker or CLI.

## Problem slice

A service needs a durable, ordered run queue and a status/report record that survives a restart,
plus a deduplicated webhook-event log. This aspect defines the schema, the transitions and the CRUD
API.

## In-scope requirements

- `src/tenon/service/store.py`:
  - `Run` and `Event` frozen/slots values with `to_dict()`.
  - `RunStore(path, *, now=None, new_id=None)`: opens/creates the SQLite file, applies the schema,
    exposes `create_run`, `claim_next`, `finish`, `get`, `list`, `record_event`, `close`.
- Schema:
  - `runs(id TEXT PK, bundle TEXT, status TEXT, created_at TEXT, started_at TEXT, finished_at TEXT,
    exit INTEGER, report TEXT, error TEXT, idempotency_key TEXT UNIQUE)`.
  - `events(id INTEGER PK AUTOINCREMENT, delivery TEXT UNIQUE, event TEXT, action TEXT,
    installation TEXT, received_at TEXT, payload TEXT)`.
- Semantics:
  - Status is `queued|running|succeeded|failed`; only `queued -> running -> succeeded|failed`.
  - `create_run(bundle, idempotency_key=None)`: a duplicate key returns the existing run (no new
    row); otherwise a queued run with a uuid4 hex id and a UTC ISO-8601 `created_at`.
  - `claim_next()`: the oldest queued run (`created_at`, then insertion order) becomes `running`
    with `started_at`, atomically; `None` when the queue is empty.
  - `finish(id, *, status, exit, report, error=None)`: only `succeeded|failed`; sets
    `finished_at`, the integer exit, the canonical JSON report (or NULL) and the capped error.
  - `get(id)` returns the run or `None`; `list(limit=50)` returns newest-first, bounded 1..200.
  - `record_event(delivery, event, action, installation, payload)` inserts or returns False on a
    duplicate delivery; the payload is stored as canonical JSON.
- Thread safety: one connection with `check_same_thread=False` and a `threading.Lock`; every method
  is serialized. A new database is created and migrated on open; reopening preserves rows.
- `src/tenon/service/__init__.py`: export `Run`, `Event`, `RunStore`.

## Out-of-scope

- HTTP, auth, webhooks, the worker, the CLI.
- Postgres/Redis, migrations beyond `CREATE TABLE IF NOT EXISTS`, retention/cleanup.

## Acceptance criteria

- **AC1 — Create/get.** A created run is `queued`, has a uuid4 hex id and a UTC timestamp; `get`
  returns it; an unknown id is `None`.
- **AC2 — Idempotency.** The same key returns the same run and leaves one row.
- **AC3 — Claim.** `claim_next` is FIFO, marks `running`/`started_at`, and returns `None` when empty;
  a second claim does not return the same run.
- **AC4 — Finish.** A run finishes `succeeded` or `failed` with exit/report/error and
  `finished_at`; an invalid status/transition is a `ValueError`.
- **AC5 — List.** Newest-first, limit-bounded; the default is 50.
- **AC6 — Events.** A delivery is stored once; a duplicate returns False; the payload round-trips;
  the timestamp is UTC.
- **AC7 — Persistence.** Reopening the file preserves runs/events; a corrupt/unwritable path is a
  named error.
- **AC8 — Determinism.** Injected `now`/`new_id` make ids/timestamps fixed; no network.

## Dependencies and sequencing

- First; `service-api` consumes it.
- Stdlib only (`sqlite3`, `json`, `threading`, `uuid`, `datetime`).

## Open questions / risks

- One writer + request threads is enough for the MVP; a Postgres store is a later card.
- No retention policy; the operator owns the database file.
