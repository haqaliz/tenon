# Spec: `service-readiness` (T13a)

- **Feature:** `service-deploy`
- **PRD:** `docs/planning/service-deploy/prd.md` (§ M4)
- **Boundary:** `RunStore.ping` and the unauthenticated `/ready` route. No deployment files.

## In-scope requirements

- `RunStore.ping() -> bool`: a cheap read (`SELECT 1`) through the existing connection/lock; `True`
  on success, `False` on a closed/corrupt/unavailable database (never raises).
- `Api.handle`: `GET /ready` (no auth) -> 200 `{"status":"ready"}` when `store.ping()` is true,
  503 `{"status":"unavailable"}` otherwise; another method 405; canonical JSON.
- `/health` stays the liveness-only 200.
- No other API/store behavior changes.

## Out-of-scope

- Deployment artifacts, worker state, metrics, WAL.
- A readiness that checks GitHub/the app identity (the service can be ready before a run).

## Acceptance criteria

- **AC1 — Ping.** A fresh/open store pings true; a closed store pings false; a broken DB path does
  not raise.
- **AC2 — Ready.** `GET /ready` is 200/ready on a good store, 503/unavailable on a closed store, no
  auth, canonical JSON; a non-GET is 405.
- **AC3 — Regression.** `/health` and all prior service tests stay green.
