# Spec: `service-api` (T10e)

- **Feature:** `provider-service`
- **PRD:** `docs/planning/provider-service/prd.md` (§ M1, M3–M8)
- **Boundary:** the runner, worker, API handler, stdlib HTTP server, `provider serve` and docs. No
  store internals.

## Problem slice

The store is only useful if a provider can start a run over HTTP, have one worker execute the shipped
installed fan-out, and read the durable status/report, with a guarded API and verified webhooks.

## In-scope requirements

- `src/tenon/service/runner.py`: `CommandRunner(builder, *, timeout=3600, runner=None)` with
  `run(bundle: Path) -> Outcome(exit: int | None, report: dict | None, error: str | None)`.
  - `builder(bundle) -> list[str]`; the default builder in the CLI invokes
    `sys.executable -c "from tenon.cli import main; raise SystemExit(main())" provider migrate
    --installed --bundle <path> --json [--open-pr --remote app --app-* ...]`.
  - Exit 0/1 with a JSON fan-out envelope -> `report`, exit; a non-JSON body -> a named error; exit
    2 -> the capped stderr as the error; `TimeoutExpired` -> "timed out"; `OSError` -> named;
    `shell=False`.
- `src/tenon/service/worker.py`: `Worker(store, execute, *, poll=1.0, stop=None)`:
  - `run_once() -> bool`: claim the oldest queued run, call `execute(run)`, finish with the returned
    `(status, exit, report, error)`; an exception is `failed` with a capped error; `False` when the
    queue is empty.
  - `start()`/`stop()`: one daemon thread, `stop` an `Event`; `stop()` joins.
- `src/tenon/service/api.py`: `Api(store, bundles: Path, token: str, *, webhook_secret=None,
  max_body=65536)` with `handle(method, path, headers, body: bytes) -> Response(status, headers,
  body: bytes)`:
  - `POST /runs`: bearer auth; JSON `{"bundle": "<name>"}`; body <= max_body (413); the name is
    relative, resolve under `bundles`, reject absolute/`..`/symlink escapes/missing/non-file/
    non-`.json` (400); create/return 201 `{"id","status","bundle"}`; an `Idempotency-Key` returns
    the existing run (200).
  - `GET /runs/{id}` and `GET /runs?limit=N`: bearer auth; the run(s) with `report`; 404 unknown;
    limit 1..200 (default 50), a bad limit 400.
  - `GET /health`: 200 `{"status":"ok"}`, no auth.
  - `POST /webhooks/github`: no secret -> 404; verify `X-Hub-Signature-256` in constant time ->
    401; parse a JSON object -> 400; record delivery/event/action/installation/payload -> 202; a
    duplicate delivery is 202 with one row.
  - Unknown path 404, wrong method 405, auth 401 with `WWW-Authenticate: Bearer`; all bodies are
    canonical JSON; errors never contain the token/secret.
- `src/tenon/service/http.py`: a stdlib `ThreadingHTTPServer` handler that reads Content-Length
  (capped), calls `Api.handle`, and writes status/headers/body; `serve(api, host, port)` returns the
  server; request logging is silent (no secrets).
- `src/tenon/cli/main.py`: `tenon provider serve`:
  - Flags: `--bundles`, `--db`, `--api-token` (or `TENON_API_TOKEN`), `--webhook-secret` (or
    `TENON_WEBHOOK_SECRET`), `--host` (default `127.0.0.1`), `--port` (default 8080), `--run-timeout`,
    `--poll`, `--dry-run`, the T10a app flags/`--api-url`.
  - Validate: token non-empty, bundles an existing directory, db parent writable; a bad value is a
    named usage error (exit 2).
  - Build the store/runner/worker/api/server; print `tenon: provider serve: listening on
    http://host:port`; run until KeyboardInterrupt; stop the worker and close the store.
  - `main`'s `--remote requires --open-pr` check must not touch `serve` (only `migrate`/`fix`).
- Docs: README/ARCHITECTURE add the command, endpoints, config, security model, SQLite/single-worker
  limits and the no-deployment/no-TLS boundary.
- Tests: the runner (JSON/exit 2/timeout/OSError), the worker (success/exit 1/exception/FIFO), the
  API (auth, traversal, idempotency, GET, webhook HMAC/no secret/duplicate/malformed, health, body
  limit, 404/405), the CLI parser/config errors and an end-to-end API+real store+worker with a fake
  runner. Offline.

## Out-of-scope

- Store internals, deployment/Docker, Postgres/Redis, parallel workers, retries/cancel, web UI,
  webhook auto-run, multi-tenant auth, bundle upload.

## Acceptance criteria

- **AC1 — Serve.** `tenon provider serve` validates its config (token/bundles/db) and starts a
  worker + HTTP server; `--help` lists the flags; a bad config exits 2 named.
- **AC2 — Queue.** `POST /runs` with a valid bundle queues, returns 201, and an idempotency key
  returns the same run; a traversal/absolute/missing/non-JSON bundle is 400; a big body 413; no/bad
  token 401.
- **AC3 — Read.** `GET /runs/{id}` and `GET /runs` return the durable record/report; unknown 404; a
  bad limit 400; `/health` 200 without auth.
- **AC4 — Worker.** `run_once` executes the oldest run, stores the report/exit, and marks
  succeeded/failed; an exception/timeout is a named failed run; no parallel work.
- **AC5 — Webhook.** A valid HMAC records 202 once; a duplicate is 202 without a second row; a bad
  signature 401; no secret 404; malformed JSON 400.
- **AC6 — Secrets.** The token/secret never appear in responses, errors, the DB or logs; the child
  gets the private key path only.
- **AC7 — End-to-end.** POST -> worker -> GET returns the same fan-out envelope the CLI printed.
- **AC8 — Docs/regression.** README/ARCHITECTURE updated; all prior tests green.

## Dependencies and sequencing

- Depends on `service-store`; last.

## Open questions / risks

- The API handler is pure and testable; the stdlib server is a thin wrapper.
- No TLS/rate limiting; a reverse proxy is required for exposure.
- One worker; a run can outlive the HTTP request.
