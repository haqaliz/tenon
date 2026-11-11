# Card: feat/provider-service

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer and GitHub App (hosted)** — fifth slice: **hosted service MVP**
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), final T10 slice
- **Branch:** `feat/provider-service/aliz`
- **Worktree:** `.claude/worktrees/feat-provider-service`

## Brief

T10a–T10d give a provider an app identity, a bundle, local and installed fan-out. The provider still
runs the CLI by hand for each migration. The last T10 piece is a self-hosted service that accepts a
run request, executes the installed fan-out in a worker, records the per-repo report, and exposes the
run's status.

T10e adds **`tenon provider serve`**:
- a small stdlib HTTP API: `POST /runs` to queue a migration, `GET /runs/{id}` and `GET /runs` to
  read status/reports; an API bearer token guards them;
- a **SQLite run store** (queued/running/succeeded/failed, timestamps, exit, report JSON, error);
- one background worker that runs the shipped T10d installed fan-out (the same bundle/config,
  discovery, temp clones, report) and records the result;
- a `POST /webhooks/github` endpoint that verifies `X-Hub-Signature-256` with a configured secret
  and records `installation`/`installation_repositories` events (no auto-run trigger in this slice);
- bundle registration by name under a configured `--bundles DIR` (no arbitrary server paths);
- no cloud deployment, database server, queue service or parallel workers: the service is
  self-hosted, local-first, and honest about its single worker.

The hard rules do not change: the service never merges or pushes the default branch; the app identity
is the T10a one; the T5 proof/PR gate applies per repo; the API token and webhook secret are secrets,
never logged; bundle names are confined to the bundle directory; the report is the T10c/T10d fan-out
envelope.

## Constraints carried in from the repo

- T10d's `_installed`/`list_installation_repos`/`clone_repo`, T10c's report types and the T10a app
  identity are the seams to reuse; no new pipeline.
- `CLAUDE.md` §1–5: execution decides, honest levels, no merge/default branch, no egress by default.
- Stdlib only: `http.server`/`wsgiref`, `sqlite3`, `hmac`, `threading`; no new dependency.
- Offline tests: fake fan-out, fake app API, temp SQLite, no network/live GitHub.

## Scope fence

Not this card: cloud deployment/Docker, Postgres/Redis, parallel workers, a web UI, webhook-triggered
runs, multi-tenant auth, bundle upload/signing, provider branding, receiver tracking.
