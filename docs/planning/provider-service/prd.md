# PRD: Hosted service MVP (T10e)

- **Slug:** `provider-service`
- **Capability:** T10 in `docs/technical/CAPABILITY_ROADMAP.md` — **fifth slice, hosted service MVP**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, final T10 slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T10a–T10d give a provider an app identity, a portable bundle, local fan-out and installed fan-out.
The provider still runs the CLI by hand for each migration and has no durable record of what ran or
what each customer repo did.

T10e adds **`tenon provider serve`**: a self-hosted HTTP service that queues a named bundle, runs the
shipped T10d installed fan-out in one background worker, stores the per-repo report in SQLite, and
exposes the run's status. A bearer token guards the API; a GitHub webhook endpoint verifies
`X-Hub-Signature-256` and records installation events. There is no cloud deployment, database
server, queue service or parallel worker.

The dangerous shortcuts are rejected here: an unauthenticated API, arbitrary server bundle paths,
storing secrets in the run record, auto-merging or pushing a default branch, trusting an unverified
webhook, and reporting a queued run as succeeded.

**For whom:** a provider running migrations for many customers, a self-hoster, the customer
reviewing the PRs, and an operator watching the run history.

## Goals & Success Metrics

1. **One command.** `tenon provider serve --bundles DIR --db PATH --api-token TOKEN ...` starts a
   local HTTP service and one worker.
2. **One run request.** `POST /runs {"bundle": "<name>"}` queues a run; names are confined to the
   bundle directory; the response is the run id/status.
3. **One durable record.** SQLite stores queued/running/succeeded/failed with timestamps, the exit,
   the fan-out report JSON and a named error.
4. **One worker.** Sequential FIFO execution of the shipped installed fan-out; no parallel runs.
5. **One guarded API.** Bearer auth on `/runs*`, constant-time compare, JSON errors, no secret in
   any response or log.
6. **Verified webhooks.** `POST /webhooks/github` verifies the HMAC and records
   installation/repository events; no auto-run.
7. **Offline tests.** Pure request handler, temp SQLite, fake runner; no network or live GitHub.

## User Personas & Scenarios

- **Provider.** Registers `stripe-v2500-v2596.json` in the bundle directory, starts the service,
  `POST /runs`, polls `GET /runs/{id}`, sees 48 passed/2 failed and the per-repo report.
- **Self-hoster.** Runs `--dry-run` (no PRs) to preview a migration across the installation.
- **Operator.** Watches `GET /runs` and the webhook events; restarts the service and the run history
  survives.
- **Customer/reviewer.** Gets the normal T5 PR per repo; the service never merges.

Scenario: a run is queued; the worker invokes the shipped installed fan-out; repo 3 fails to clone;
the run finishes with exit 1, status `failed`, the report naming all repos and the per-repo error;
`GET /runs/{id}` returns the same envelope the CLI printed.

## Requirements

### Must have

- **M1 — CLI.** `tenon provider serve --bundles DIR --db PATH --api-token TOKEN [--webhook-secret
  SECRET] [--host 127.0.0.1] [--port 8080] [--run-timeout 3600] [--poll 1.0] [--dry-run]
  [--app-id ID] [--app-installation-id ID] [--app-private-key PATH] [--api-url URL]`.
  - `--api-token`/`TENON_API_TOKEN` is required and non-empty; `--bundles` is an existing directory;
    `--db` is a writable path; a bad value is a named usage error (exit 2).
  - `--webhook-secret`/`TENON_WEBHOOK_SECRET` is optional; without it the webhook path is 404.
  - The app identity is the T10a one; `--dry-run` omits `--open-pr` for every run.
  - The service prints the listening URL, runs until SIGINT/SIGTERM, and stops the worker cleanly.
- **M2 — Run store.** `src/tenon/service/store.py`: SQLite schema and `RunStore`:
  - `runs(id, bundle, status, created_at, started_at, finished_at, exit, report, error,
    idempotency_key UNIQUE)`; `events(id, delivery UNIQUE, event, action, installation,
    received_at, payload)`.
  - `create_run(bundle, idempotency_key=None)`, `claim_next()`, `finish(id, status, exit, report,
    error)`, `get(id)`, `list(limit)`, `record_event(...)`.
  - Status is one of `queued|running|succeeded|failed`; `succeeded` iff exit 0; a status transition
    is monotonic; a duplicate idempotency key returns the existing run.
  - Ids are UUID hex; timestamps are UTC ISO-8601; the store is safe for one worker + request threads
    (a lock or per-call connections); a new database is created and migrated on open.
- **M3 — Runner.** `src/tenon/service/runner.py`: a command runner that invokes the shipped CLI for
  one bundle:
  - `[sys.executable, "-c", "from tenon.cli import main; raise SystemExit(main())", "provider",
    "migrate", "--installed", "--bundle", <bundle path>, "--json", "--remote", "app",
    "--app-id", ..., "--app-installation-id", ..., "--app-private-key", ..., "--api-url", ...]`
    plus `--open-pr` unless dry-run.
  - Parse the JSON fan-out envelope from stdout; exit 0/1 with JSON is a completed run; exit 2 or
    non-JSON is a run error using the capped stderr; a timeout kills the process and is a named
    error; the command is injectable for tests.
- **M4 — Worker.** `src/tenon/service/worker.py`: one background thread with `run_once() -> bool`
  (claim the oldest queued run, mark running, execute, finish) and `start()/stop()`; a runner
  exception is a `failed` run with a capped, secret-free error; results are stored as the JSON
  envelope.
- **M5 — API.** `src/tenon/service/api.py`: a pure `Api.handle(method, path, headers, body) ->
  Response` (status, headers, JSON body), wrapped by a stdlib HTTP server:
  - `POST /runs` (bearer auth): body `{"bundle": "<relative name>"}` (max 64 KiB); resolve under
    `--bundles`, reject absolute/`..`/symlink escapes/missing/non-file/non-JSON names; queue and
    return 201 `{"id","status":"queued","bundle"}`; an `Idempotency-Key` header returns the existing
    run (200) instead of creating a second.
  - `GET /runs/{id}` and `GET /runs?limit=N` (bearer auth): the run record(s), including `report`
    when finished; 404 for an unknown id.
  - `GET /health`: 200 `{"status":"ok"}` (no auth, no secrets).
  - `POST /webhooks/github`: verify `X-Hub-Signature-256: sha256=<hex>` with the configured secret
    in constant time; parse the JSON; record `X-GitHub-Delivery`/`X-GitHub-Event`/action/
    installation/payload; 202; a bad signature is 401, malformed JSON 400, a missing secret 404, a
    duplicate delivery 202 without a second row.
  - All responses are JSON with the shipped canonical encoding; unknown paths 404; a wrong method
    405; a body over the limit 413; auth failures 401 with `WWW-Authenticate: Bearer`.
- **M6 — Secrets/trust.** The API token and webhook secret are compared with
  `hmac.compare_digest`; the token is never logged or stored; the webhook secret is never stored;
  bundle names are confined to the bundle directory; the app private key is read by the CLI child
  (the service passes the path, never the key); the run report is the CLI's token-free envelope.
- **M7 — Tests/docs.** Store CRUD/claim/idempotency/events, worker transitions (success/exit 1/
  exception/timeout), API auth/validation/traversal/idempotency/GET/webhook HMAC/health/limits, the
  parser/config errors and an end-to-end `Api` + real store + worker + fake runner. README/
  ARCHITECTURE document the command, endpoints, config, security model and the no-deployment limit.
  Offline.
- **M8 — No deployment.** No Dockerfile, cloud deploy, Postgres/Redis, parallel workers, web UI,
  webhook auto-run, retries, cancellation, metrics or multi-tenant auth.

### Should have

- **S1 — FIFO determinism.** The oldest queued run is claimed first; `GET /runs` is newest-first.
- **S2 — Cap everything.** Request bodies, error text and stored payloads are bounded.
- **S3 — One code path.** The worker runs the shipped CLI; no duplicated pipeline.

### Nice to have

- **N1 — `--parallel N`**; a later card.
- **N2 — Webhook-triggered runs**; a later card.
- **N3 — Docker/deploy manifests**; a later card.

## Data Model

```
Run
  id: str                 # uuid4 hex
  bundle: str             # relative name under --bundles
  status: queued|running|succeeded|failed
  created_at/started_at/finished_at: ISO-8601 UTC
  exit: int | None        # 0/1/2 from the CLI
  report: dict | None     # the T10c/T10d fan-out envelope
  error: str | None       # capped, token-free
  idempotency_key: str | None  # unique

Event
  delivery: str           # X-GitHub-Delivery, unique
  event: str              # X-GitHub-Event
  action: str | None
  installation: str | None
  received_at: str
  payload: dict           # bounded JSON
```

## API Contract

```sh
tenon provider serve --bundles ./bundles --db ./tenon.db --api-token "$TENON_API_TOKEN" \
  --app-id 123 --app-installation-id 456 --app-private-key app.pem
```

```http
POST /runs
Authorization: Bearer <token>
{"bundle": "stripe-v2500-v2596.json"}
-> 201 {"id":"ab12...","status":"queued","bundle":"stripe-v2500-v2596.json"}

GET /runs/ab12...
-> 200 {"id":"ab12...","status":"failed","exit":1,"bundle":"...","report":{...},"error":null,...}

GET /runs?limit=20
-> 200 {"runs":[{...}, ...]}

POST /webhooks/github
X-Hub-Signature-256: sha256=...
X-GitHub-Event: installation_repositories
-> 202 {"status":"recorded"}
```

## Technical Considerations

- **Why a subprocess runner.** The CLI already contains the installed fan-out, the app identity and
  the report; invoking it keeps one code path and isolates a run's failures. The alternative (an
  in-process refactor) duplicates config plumbing and couples the worker to `argparse`.
- **Why SQLite.** Stdlib, durable, one writer, enough for one worker; a Postgres/queue service is a
  deployment decision, not an MVP one.
- **Why one worker.** Deterministic, one token per run, no concurrent clone/push pressure; a
  `--parallel` flag is a later card with rate-limit semantics.
- **Why the API token.** A self-hosted service is still a network listener; a bearer token is the
  smallest real guard. Loopback-only without auth is a footgun behind a proxy.
- **Why webhooks only record.** A migration trigger is a policy decision (which bundle for which
  event?); the MVP records the installation facts and keeps runs explicit.
- **Why confined bundle names.** An HTTP client must never select an arbitrary server path; the
  bundle directory is the operator's trust boundary.

## Risks & Open Questions

- **Not internet-hardened.** No TLS, rate limiting, CORS or a reverse proxy; put it behind one. The
  token and webhook secret are the only guards.
- **SQLite concurrency.** One worker and request threads share the DB; a lock/per-call connection
  keeps it correct, not fast.
- **Long runs.** A run can outlive the HTTP client; the request returns a queued id, not the result.
- **Subprocess cost.** One Python process per run; acceptable for a self-hosted MVP.
- **No retries/cancel.** A failed run is retried by posting it again; a stuck run is killed by the
  timeout.
- **Secret handling.** The app private key path is passed to the child; a malicious git hook in a
  customer repo can still read the token (T5/T10a limit).
- **Open question — should a failed run be `failed` or `completed`?** `failed` with `exit`/`report`
  keeps the status honest; a client inspects the report for per-repo detail.
- **Open question — should the API support a repo list?** No in this slice; installed fan-out is the
  hosted model.

## Out of Scope

- Cloud deployment/Docker, Postgres/Redis, parallel workers, retries, cancellation, metrics.
- Web UI, multi-tenant auth, webhook-triggered runs, bundle upload/signing.
- Provider branding, receiver tracking, new locators/proof levels.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `service-store` | SQLite schema, `RunStore`, ids/timestamps, claim/finish/list/events, store tests. No HTTP/worker. |
| `service-api` | Runner, worker, `Api.handle`, the stdlib server, `provider serve`, docs, end-to-end tests. No store internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | A provider has no durable, request-driven way to run bundles. |
| User understanding | 🟢 | Provider/self-hoster/operator/customer; the run and report are concrete. |
| Success metrics | 🟢 | Command, request, store, worker, auth, webhook, offline tests. |
| Scope clarity | 🟢 | Local self-hosted MVP; deployment/parallel/webhook-run excluded. |
| Edge cases & risks | 🟡 | Not internet-hardened, SQLite concurrency and long runs are real; documented. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Stdlib HTTP/SQLite/threading + the shipped CLI; no new dependency. |
| Go-to-market | 🟢 | The last T10 piece: a provider can run migrations as a service. |

**Areas to strengthen before sharing:** a real deployment needs TLS, a proxy, rate limits, retries
and a queue; the MVP is the honest local service, not a hosted product.

**The question I would want answered before greenlighting this:** *If the service is exposed to the
internet without a proxy, what protects it?* The answer this card records: only the bearer token and
the webhook HMAC; there is no TLS/rate limiting. The operator must put it behind a TLS proxy; the
docs say so, and a hardened deployment is a later card.
