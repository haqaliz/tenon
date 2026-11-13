# Spec: `webhook-trigger-api` (T10f)

- **Feature:** `webhook-runs`
- **PRD:** `docs/planning/webhook-runs/prd.md` (§ M2–M4)
- **Boundary:** the webhook match/queue/response, the end-to-end tests and the docs. No trigger
  parsing/CLI.

## In-scope requirements

- `Api(..., triggers: Mapping[tuple[str, str | None], str] | None = None)`:
  - After the existing HMAC/record path, match the delivery's event (the header) and payload action
    (exact `(event, action)` first, then `(event, None)`).
  - On a match, `store.create_run(bundle, idempotency_key=f"webhook:{delivery}")`; the run is a
    normal queued run.
  - Response 202 `{"status":"recorded","run":{"id","status","bundle"}}` on a match;
    `{"status":"recorded"}` without one; a duplicate delivery returns the existing run (same id),
    never a second.
  - A bundle deleted after startup still queues; the worker reports the existing missing-bundle
    failure; the webhook does not 500.
  - No route/auth change: HMAC-only webhook; `/runs*` bearer.
- Docs: README service section, DEPLOYMENT examples/security note, a `CHANGELOG.md` `Unreleased`
  entry. Version stays 0.1.0.
- Tests: a signed matching event queues one run and returns it; a non-match records only; exact vs
  actionless; a duplicate delivery; a deleted bundle; the run visible via `GET /runs/{id}` and
  processed by a fake worker; the trigger map reaches the Api from the CLI. Offline.

## Out-of-scope

- Trigger parsing/validation; new events/semantics; per-repo filters; auto-merge.

## Acceptance criteria

- **AC1 — Match.** A signed matching event queues one run; the 202 names its id/status/bundle.
- **AC2 — No match.** A non-matching event records only, no run.
- **AC3 — Precedence.** An exact action wins over an actionless trigger.
- **AC4 — Dedupe.** A duplicate delivery returns the same run and leaves one row.
- **AC5 — Deleted bundle.** The webhook queues; the worker fails the run with the existing
  missing-bundle message; the webhook stays 202.
- **AC6 — Lifecycle/docs.** `GET /runs/{id}` shows the queued/processed run; the docs/changelog
  describe the feature; all prior tests green.
