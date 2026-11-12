# PRD: Deployable service (T13a)

- **Slug:** `service-deploy`
- **Capability:** **T13 Hardened deployment** — **first slice: a deployable service**
- **Milestone:** next phase after T12; T13b (resilience) follows
- **Status:** implemented 2026-11-12 (`Dockerfile`, `docker-compose.yml`, `Caddyfile`, `/ready`; 2,473 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

`tenon provider serve` is a local-first MVP: a bare Python process, one worker, SQLite, a bearer
token and a webhook HMAC, with no container, TLS, readiness, backups or a non-root runtime. A
provider cannot put it on a server safely.

T13a makes the service **deployable**: a non-root multi-stage Docker image with git and the app extra,
a Compose stack with the service plus Caddy for automatic HTTPS, read-only mounts for the bundles and
the GitHub App key, a writable volume for SQLite, a readiness endpoint, and a deployment guide
(secrets, TLS, backups/restore, token rotation, upgrades, security checklist).

The service process, API, worker and store behavior do not change beyond `/ready`; T13b adds parallel
workers, retries, cancel, metrics and the SQLite hardening.

**For whom:** a provider/self-hoster deploying the service on a VM, the operator handling secrets and
backups, and the customer whose PRs the service opens.

## Goals & Success Metrics

1. **One image.** `docker build .` yields a non-root image with git, CA certificates, the `[app]`
   extra and no secrets, starting `tenon provider serve`.
2. **One stack.** `docker compose up` runs the service behind Caddy with a domain, TLS, volumes and
   healthchecks; the service is not published directly.
3. **One readiness signal.** `GET /ready` reports the store is usable; a broken DB is 503.
4. **One guide.** `docs/technical/DEPLOYMENT.md` covers secrets, bundles, TLS, backups/restore,
   rotation, upgrades and the security checklist.
5. **Offline tests.** `/ready`/store tests and static deployment-artifact checks; no Docker run in
   pytest.

## Requirements

### Must have

- **M1 — Image.** `Dockerfile` (multi-stage, `python:3.13-slim` + `uv` from the official image):
  installs the project with `--extra app`, `git` and `ca-certificates`; a `tenon` user (uid 10001);
  `PYTHONDONTWRITEBYTECODE=1`; `ENTRYPOINT ["tenon"]`; `CMD ["provider","serve","--bundles",
  "/data/bundles","--db","/data/tenon.db","--host","0.0.0.0","--port","8080"]`; a `HEALTHCHECK` using
  the stdlib `urllib` `/health`; no secret in any layer; a `.dockerignore` excluding `.git`,
  `.venv`, tests, docs and local data.
- **M2 — Compose.** `docker-compose.yml`:
  - `service`: build ., `env_file: .env`, the app identity/token/webhook env, git author/committer
    env (a commit identity in the container), volumes `tenon-data:/data`,
    `./bundles:/data/bundles:ro`, `./secrets:/secrets:ro`, `tmpfs: /tmp`,
    `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`,
    `restart: unless-stopped`, a healthcheck, `expose: 8080` and **no** host port.
  - `caddy`: `caddy:2`, ports 80/443 (and 443/udp), the `Caddyfile`, `caddy-data`/`caddy-config`
    volumes, `depends_on: service`.
  - Named volumes for the DB and Caddy state; the bundle and secret mounts are read-only.
- **M3 — TLS.** `Caddyfile`: `{$TENON_DOMAIN:localhost}` -> `reverse_proxy service:8080` plus
  compression; automatic HTTPS for a real domain; the localhost/internal-CA caveat documented.
- **M4 — Readiness.** `RunStore.ping()` (`SELECT 1`) and `GET /ready` (no auth): 200
  `{"status":"ready"}` when the store is usable, 503 `{"status":"unavailable"}` otherwise; the
  existing `/health` stays a liveness-only 200.
- **M5 — Docs/artifacts.** `.env.example` (token, webhook secret, app id/installation/key path,
  domain, git identity); `bundles/README.md`; `secrets/.gitkeep`/ignore; `DEPLOYMENT.md` with
  prerequisites, secret generation, the app key mount, bundle placement, `compose up`, DNS/TLS,
  backups/restore (`sqlite3 .backup` with the service stopped/checkpointed), token/webhook rotation,
  upgrades, resource limits, logs and a security checklist.
- **M6 — Tests.** Store `ping` and `/ready` (ready/unavailable), plus static artifact tests:
  the Dockerfile has a non-root `USER` and no token, the Compose has `caddy`/volumes/`read_only` and
  no service `ports`, and the Caddyfile reverse-proxies the service. Offline.

### Should have

- **S1 — Read-only bundles/key.** The mounts are `:ro`; the DB volume is the only writable data.
- **S2 — Commit identity.** The compose sets `GIT_AUTHOR_*`/`GIT_COMMITTER_*` so a fresh clone can
  commit even when the customer repo has no identity.
- **S3 — Local run.** `TENON_DOMAIN=localhost docker compose up` works with Caddy's internal CA.

### Nice to have

- **N1 — Kubernetes manifests**; a later card.
- **N2 — Postgres**; T13b/never (SQLite is the chosen store).
- **N3 — A CI image build/push**; a later card.

## Data Model / API

```
GET /ready  -> 200 {"status":"ready"} | 503 {"status":"unavailable"}
```

No store schema change; `ping` is a read.

## Technical Considerations

- **Why Compose + Caddy.** The smallest real deployment: one host, automatic TLS, two containers and
  a volume; no cluster or cloud API.
- **Why non-root + read-only root.** The service only writes `/data` (SQLite) and `/tmp` (temp
  clones); the rest can be immutable.
- **Why no host port on the service.** Only Caddy is public; the token is not exposed over HTTP.
- **Why `/ready` separate from `/health`.** Liveness must not fail on a DB blip; readiness should.
- **Why no Docker test.** The artifacts are static and reviewed; pytest checks their invariants, not
  a daemon that CI may not have.

## Risks & Open Questions

- **Untested image at runtime.** The Dockerfile/Compose are not executed in pytest; the first
  operator run is the integration test. The static checks catch the obvious mistakes.
- **Secrets on disk.** The app key and `.env` live on the host; permissions/ownership are the
  operator's responsibility (documented 0400/0600).
- **SQLite backups.** A naive file copy of a live DB can be inconsistent; the guide uses
  `sqlite3 .backup`/checkpoint with the service stopped. T13b adds WAL.
- **Local TLS.** Caddy's internal CA is not trusted by default; the guide explains the trust step.
- **Image size/build network.** Building needs PyPI; the runtime image has no secrets and no build
  tools.
- **Open question — should the service run as uid 10001 or the host user?** 10001 with the volume
  ownership documented; a host-user mapping is an operator choice.

## Out of Scope

- Parallel workers, retries, cancel, metrics and the SQLite WAL hardening (T13b).
- Kubernetes, cloud IaC, Postgres, a web UI, multi-tenant auth, a SaaS control plane.
- New locators/provider features.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `service-readiness` | `RunStore.ping`, `GET /ready`, the API tests. No deployment files. |
| `service-deploy` | Dockerfile, `.dockerignore`, `docker-compose.yml`, `Caddyfile`, `.env.example`, `bundles/README.md`, `DEPLOYMENT.md`, static artifact tests. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The MVP cannot be deployed safely as-is. |
| User understanding | 🟢 | Provider/operator/customer; the compose and guide are concrete. |
| Success metrics | 🟢 | Image, stack, TLS, readiness, guide, static tests. |
| Scope clarity | 🟢 | Deployment only; resilience is T13b. |
| Edge cases & risks | 🟡 | Untested runtime and secret ownership are real; documented/static-checked. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Standard image/compose/Caddy; one small code change (`/ready`). |
| Go-to-market | 🟢 | A provider can run the service on a VM with TLS. |

**Areas to strengthen before sharing:** the image is not exercised in CI; a smoke test on a real
Docker host is the first operator step. The static checks cover the obvious invariants.

**The question I would want answered before greenlighting this:** *If an operator exposes the service
without Caddy, what protects it?* The answer this card records: the bearer token and the webhook HMAC
only; the Compose has no host port on the service, and the guide says Caddy/TLS is required. A direct
exposure is operator error, not a supported path.
