# Spec: `service-deploy` (T13a)

- **Feature:** `service-deploy`
- **PRD:** `docs/planning/service-deploy/prd.md` (§ M1–M3, M5–M6)
- **Boundary:** Dockerfile, `.dockerignore`, `docker-compose.yml`, `Caddyfile`, `.env.example`,
  `bundles/README.md`, `secrets/.gitkeep`, `DEPLOYMENT.md` and static artifact tests. No runtime
  code.

## In-scope requirements

- **Dockerfile:** a `uv` build stage on `python:3.13-slim` that installs the project with
  `--extra app`, then a runtime stage with `git`/`ca-certificates`, a `tenon` user (uid 10001), an
  owned `/data`, `PYTHONDONTWRITEBYTECODE=1`, `ENTRYPOINT ["tenon"]`, the serve `CMD`, a stdlib
  `urllib` healthcheck and no secret. `.dockerignore` excludes `.git`, `.venv`, tests, docs, local
  data and `.env*`.
- **Compose:** service + caddy; `env_file`/required `TENON_API_TOKEN`; app identity env; git author/
  committer env; `tenon-data:/data`, read-only `./bundles`/`./secrets`; `tmpfs /tmp`; `read_only`;
  `cap_drop: ALL`; `no-new-privileges`; restart; healthcheck; `expose: 8080` and no service `ports`;
  Caddy 80/443 + the Caddyfile + state volumes + `TENON_DOMAIN`.
- **Caddyfile:** `{$TENON_DOMAIN:localhost}` -> `reverse_proxy service:8080` + compression.
- **Docs/artifacts:** `.env.example` (token/domain/webhook/app identity/key path/git identity),
  `bundles/README.md`, `secrets/.gitkeep`, `.gitignore` entries, `DEPLOYMENT.md` (prereqs, secret
  generation, key mount/permissions, bundles, compose up, DNS/TLS incl. the localhost CA, backup/
  restore with `sqlite3 .backup`, token/webhook rotation, upgrades, logs, security checklist).
- **Static tests:** the Dockerfile has a non-root `USER`, `ENTRYPOINT`, `git`/`--extra app`, no
  token assignment; the Compose parses and has the two services, volumes, `read_only`, `cap_drop`,
  no service `ports`; the Caddyfile reverse-proxies; `.dockerignore`/`.env.example`/`DEPLOYMENT.md`
  contain the expected keys. Offline.
- No runtime/API/store change beyond `service-readiness`.

## Out-of-scope

- Running Docker/Compose in tests; Kubernetes/cloud IaC; Postgres; resilience (T13b).

## Acceptance criteria

- **AC1 — Image.** The Dockerfile is multi-stage, installs git/CA + the app extra, creates a non-root
  user/owned `/data`, has the healthcheck and the serve CMD, and contains no secret.
- **AC2 — Stack.** The Compose runs the service behind Caddy, uses the named/read-only volumes,
  read-only root + tmpfs, dropped caps, no host port on the service and a healthcheck.
- **AC3 — TLS.** The Caddyfile reads `TENON_DOMAIN` and reverse-proxies the service.
- **AC4 — Docs.** `.env.example`, the bundle/secret layout and `DEPLOYMENT.md` cover the required
  operations (secrets, backups/restore, rotation, security).
- **AC5 — Static tests.** The invariants above are asserted offline; all prior tests green.
