# PRD: Webhook-triggered runs (T10f)

- **Slug:** `webhook-runs`
- **Capability:** **T10 Provider layer** — follow-up slice: **webhook-triggered runs**
- **Milestone:** after v0.1.0; the last T10e follow-up
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

The T10e service verifies `POST /webhooks/github` with the HMAC and records the delivery, but it
never queues a run. A provider still posts every migration to `POST /runs` by hand, even when a
GitHub event is exactly the moment to run it (a new customer repo, an installation change, a push).

T10f adds **webhook-triggered runs**: the operator maps a GitHub event (and optional action) to a
registered bundle with `--trigger EVENT[.ACTION]=BUNDLE`; on a verified, matching delivery the service
queues a normal installed-fan-out run through the existing store/worker, deduped by the delivery id,
and the 202 response names the run. A non-matching event is still recorded only.

The mapping is operator CLI config, not bundle content, so a bundle cannot auto-run itself. A trigger
requires the webhook secret; bundle names stay confined to `--bundles`; the run is an ordinary run
with the same worker, report, retries/cancel and no merge path.

**For whom:** a provider automating a migration on a GitHub event, the operator configuring the
mapping, and the customer whose PRs the triggered run opens.

## Goals & Success Metrics

1. **One mapping.** `--trigger EVENT[.ACTION]=BUNDLE`, repeatable, validated at startup with named
   usage errors; an exact action wins over an actionless trigger.
2. **One run per delivery.** A verified, matching delivery queues one installed-fan-out run; the
   delivery id is the idempotency key, so a retry/duplicate never queues twice.
3. **A visible result.** The 202 names the run id/status/bundle when a trigger matched; a
   non-matching event is recorded only.
4. **The same rails.** The run uses the existing worker/report/retries/cancel; no new pipeline,
   proof/PR behavior, merge path or secret handling.
5. **Offline tests.** Trigger parsing/validation, signed webhook→queue, action matching, duplicate
   delivery, non-match, a deleted bundle, the CLI flags. No network/GitHub.

## Requirements

### Must have

- **M1 — Trigger config.** `src/tenon/service/triggers.py`: a frozen `Trigger(event, action, bundle)`
  and `parse_trigger(value, bundles)`/`parse_triggers(values, bundles)`.
  - `EVENT[.ACTION]=BUNDLE`, split on the first `=` and the first `.`; event/action/bundle non-empty
    strings with no whitespace; `BUNDLE` is a `.json` file confined to `--bundles` (the existing
    `resolve_bundle`); a duplicate `(event, action)` key or a malformed value is a named `ValueError`.
  - `--trigger` is a repeatable flag on `provider serve`; a trigger without `--webhook-secret` is a
    named usage error (the webhook route is 404 without a secret).
- **M2 — Webhook queue.** `Api(..., triggers=...)`: after the existing HMAC/record path, match the
  delivery's event and payload action (exact action first, then actionless) and
  `store.create_run(bundle, idempotency_key=f"webhook:{delivery}")`. The response is 202
  `{"status":"recorded","run":{"id","status","bundle"}}` on a match, `{"status":"recorded"}` without
  one; a duplicate delivery returns the existing run, not a second.
  - The event/action match is exact on `X-GitHub-Event` and the payload `action` (an absent action
    only matches an actionless trigger).
  - The trigger bundle is validated at startup; a file deleted later yields a queued run that the
    worker reports as failed (the existing missing-bundle path), never a service crash.
  - No new route/auth: the webhook stays HMAC-only; `/runs*` stays bearer.
- **M3 — CLI/docs.** `provider serve --trigger ...`; `--help`; README/DEPLOYMENT examples
  (`installation_repositories.added=demo.json`, `push=demo.json`), the security note (operator
  mapping, secret required), and a `CHANGELOG.md` `Unreleased` entry. Version stays 0.1.0.
- **M4 — Tests.** Parsing/validation (event/action/bundle, traversal/absolute/missing/non-json,
  duplicate, no secret); the API queues on a match, records only otherwise, exact-action precedence,
  duplicate delivery dedupe, a deleted bundle; the CLI flag/validation; the run is visible via
  `GET /runs/{id}` and processed by a fake worker. Offline.

### Should have

- **S1 — One code path.** A triggered run is a normal `create_run`; no special worker/status.
- **S2 — Named errors.** A bad trigger/mapping is a usage error (exit 2), never a traceback.
- **S3 — No secret leak.** The webhook secret/token never appears in a response, the DB or logs.

### Nice to have

- **N1 — Per-repo filters**; a later card; the installed fan-out covers the installation.
- **N2 — Bundle-level triggers**; rejected for now (a bundle cannot auto-run itself).
- **N3 — A trigger admin API**; not needed; the CLI is the operator surface.

## Data Model

```
Trigger
  event: str            # X-GitHub-Event
  action: str | None    # payload action; None = any
  bundle: str           # confined name under --bundles

Mapping: dict[(event, action|None), bundle]
Run idempotency_key: "webhook:<X-GitHub-Delivery>"
```

No schema change; the existing unique idempotency key and the events table provide the dedupe.

## API Contract

```sh
tenon provider serve --bundles ./bundles --db ./tenon.db --api-token "$TOKEN" \
  --webhook-secret "$SECRET" \
  --trigger "installation_repositories.added=demo.json" \
  --trigger "push=demo.json"
```

```http
POST /webhooks/github
X-Hub-Signature-256: sha256=...
X-GitHub-Event: installation_repositories
X-GitHub-Delivery: d-123
{"action":"added", ...}
-> 202 {"status":"recorded","run":{"id":"ab12...","status":"queued","bundle":"demo.json"}}
```

A repeat delivery `d-123` returns the same run; a non-matching event is
`202 {"status":"recorded"}`.

## Technical Considerations

- **Why operator config.** A bundle that declares its own auto-run is a supply-chain footgun; the
  operator maps events to bundles explicitly.
- **Why the delivery id as the idempotency key.** The store already dedupes keys; a webhook retry or
  a duplicate delivery cannot double-queue a migration.
- **Why full installed fan-out.** The T10d run is the unit; a per-repo trigger filter needs a new
  installed `--match` path. The event decides *when*, not *which* (the installation is the scope).
- **Why no new route.** The verified webhook is the trigger; the existing `/runs` API reads the
  queued run.
- **Why a deleted bundle is a failed run.** Startup validation catches operator mistakes; a later
  deletion is a run-level error, not a webhook 500.

## Risks & Open Questions

- **Event-to-bundle policy.** The operator can map any event; a noisy event (e.g. `push`) can queue
  many runs. The idempotency key is per delivery, not per repo/branch; the operator chooses.
- **Webhook retries.** GitHub redelivers on non-2xx; a duplicate is idempotent. A service restart
  keeps the run history and the key.
- **No repo filter.** A triggered run covers the whole installation; per-repo targeting is a later
  card.
- **A deleted bundle.** Queued then failed; the operator sees a named run error.
- **Open question — should `--trigger` require the webhook secret?** Yes; without the secret the
  route is 404 and a trigger would be dead config.
- **Open question — should an actionless trigger match an event whose payload has an action?** Yes,
  it is the fallback after an exact-action match.

## Out of Scope

- Per-repo filters, bundle-level triggers, a trigger admin API/UI.
- New event semantics, auto-merge, a web UI, multi-tenant triggers.
- Per-delivery retries/backoff (the normal service retries/cancel apply to the run).

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `webhook-trigger-config` | `Trigger`, parsing/validation, `--trigger`, startup wiring, tests. No API webhook path. |
| `webhook-trigger-api` | The webhook match/queue/response, the end-to-end tests, docs. No config parsing. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The webhook records but never queues; the operator posts by hand. |
| User understanding | 🟢 | Provider/operator/customer; the mapping and response are concrete. |
| Success metrics | 🟢 | Mapping, one run/delivery, visible result, same rails, offline tests. |
| Scope clarity | 🟢 | No filters/bundle triggers/UI; the event decides when, the installation which. |
| Edge cases & risks | 🟡 | Noisy events, deleted bundles and webhook retries are real; documented/deduped. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses the store's idempotency, `resolve_bundle` and the existing webhook. |
| Go-to-market | 🟢 | The last provider automation piece; no new infrastructure. |

**Areas to strengthen before sharing:** a noisy event can queue many full-installation runs; the
operator should map a specific action. The delivery idempotency prevents retries, not policy.

**The question I would want answered before greenlighting this:** *If a bundle is deleted after the
service starts, does a webhook 500?* The answer this card records: no; the run is queued and the
worker reports the missing bundle as a failed run. Startup validation catches the typo earlier.
