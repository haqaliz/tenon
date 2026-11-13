# Deploying the service

`tenon provider serve` ships as a small Docker image behind Caddy: the service talks HTTP on the
private compose network, Caddy terminates TLS on 80/443, and only the database volume is writable.
This guide is for a single VM. For the local MVP behavior see the README; T13b adds parallel
workers, bounded retries, cancel and Prometheus metrics.

## Prerequisites

- A Linux host with Docker Engine and the Compose plugin (v2).
- A DNS name with an A/AAAA record pointing at the host (for real TLS).
- Ports 80 and 443 reachable from the internet; nothing else needs to be open.
- This repository checked out on the host (the compose builds the image locally).
- The GitHub App private key for the app identity (T10a).

## Secrets

Generate the API token and the optional webhook secret:

```sh
openssl rand -hex 32   # TENON_API_TOKEN
openssl rand -hex 32   # TENON_WEBHOOK_SECRET (optional)
cp .env.example .env
chmod 600 .env
```

Fill `.env`: the token, `TENON_DOMAIN`, the app id/installation id, and the key **path**
(`TENON_GITHUB_APP_PRIVATE_KEY=/secrets/app.pem`; the contents never go in `.env`).

Mount the key as a file and restrict it to the service uid (10001), because the bind mount is
read-only but still permission-checked:

```sh
sudo cp app.pem secrets/app.pem
sudo chown 10001:10001 secrets/app.pem
sudo chmod 400 secrets/app.pem
```

`openssl rand -hex 32` values, the `.env` file and `secrets/` are gitignored; never commit them.
The image contains no secret: the token and key path arrive at runtime.

## Bundles

Put migration bundles and the specs they reference under `bundles/`; the directory is mounted
read-only at `/data/bundles` (see `bundles/README.md` for the layout). Queue a run with:

```sh
curl -H "Authorization: Bearer $TENON_API_TOKEN" \
     -d '{"bundle": "stripe-v2500-v2596.json"}' https://$TENON_DOMAIN/runs
```

## Start the stack

```sh
docker compose up -d --build
docker compose ps
```

The service is not published on the host: `expose: 8080` is internal only and the compose has no
`ports` entry for it. Caddy is the only public container.

## Workers, retries and cancel

The image runs with one worker and no retries. Add `--workers N` (1..16) and `--retries N` (0..10)
to a compose `command:` (or the image `CMD`) to change that:

```yaml
services:
  service:
    command:
      - provider
      - serve
      - --bundles
      - /data/bundles
      - --db
      - /data/tenon.db
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - --workers
      - "4"
      - --retries
      - "2"
```

Each worker atomically claims the oldest queued run, so N threads share the SQLite queue without
running a row twice. Raise `--workers` only as far as the GitHub App installation's rate limit
allows: every run clones and may push and open PRs.

`--retries` covers infrastructure failures only. A run that produced a report (CLI exit 0 or 1) is
terminal and is never retried, so a retry never duplicates or refuses an already-opened PR. A run
with no report (timeout, exit 2, exception, invalid report) is re-queued up to N extra times; the
`attempts` count is visible in `GET /runs/{id}`. Cancel is terminal and never retried.

Cancel a queued or running run:

```sh
curl -X POST -H "Authorization: Bearer $TENON_API_TOKEN" \
     https://$TENON_DOMAIN/runs/$RUN_ID/cancel
```

A queued run returns 202 with `"status":"cancelled"`; a running run returns 202 with
`"status":"cancelling"`, the worker sees the flag, and the runner stops the CLI's process group
(SIGTERM, then SIGKILL after five seconds), so its git children stop too. A finished run returns 409
with its status.

On startup the service re-queues runs left `running` by an unclean restart, or finishes them
`cancelled` when a cancel had been requested. Run history is durable; no manual cleanup is needed.
**Caveat:** process groups are POSIX-only and a SIGTERM can skip the child's temp-dir cleanup. The
store/report is unaffected, and `/tmp` is a tmpfs in the compose, so leftovers are bounded. Windows
is not a target.

## Webhook triggers

Map a verified GitHub event (and optional action) to a registered bundle with `--trigger`; add it to
the compose `command:` (the webhook secret comes from `TENON_WEBHOOK_SECRET` in `.env`):

```yaml
services:
  service:
    command:
      - provider
      - serve
      - --bundles
      - /data/bundles
      - --db
      - /data/tenon.db
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - --trigger
      - installation_repositories.added=demo.json
      - --trigger
      - push=demo.json
```

The event is `X-GitHub-Event`, the action is the payload `action`; an exact `event.action` wins over
an actionless `event`. On a match the service queues a normal installed-fan-out run with
`webhook:<X-GitHub-Delivery>` as its idempotency key and answers 202 with the run id/status/bundle; a
non-match records the event only. A duplicate delivery returns the same run, so a GitHub retry never
queues twice. The bundle must be a `.json` file confined to `--bundles`; a trigger without
`TENON_WEBHOOK_SECRET`/`--webhook-secret` is a usage error, and a bundle deleted after startup
queues a run that fails with the normal missing-bundle error.

The mapping is operator CLI config, never bundle content: a bundle cannot auto-run itself. There is
no per-repo filter in this slice; a triggered run covers the whole installation, so map a specific
action (for example `installation_repositories.added`) rather than a noisy event when that matters.

## Metrics

`GET /metrics` is bearer-guarded and returns Prometheus text: `tenon_runs{status=...}` for
`queued`, `running`, `succeeded`, `failed` and `cancelled`, plus `tenon_workers`. Caddy already
proxies the route, so an external Prometheus scrapes the public TLS name and sends the API token:

```yaml
scrape_configs:
  - job_name: tenon
    scheme: https
    authorization:
      credentials_file: /etc/prometheus/tenon-token
    static_configs:
      - targets: ["$TENON_DOMAIN"]
```

The credentials file holds only the token and must be readable by Prometheus alone. The token is
compared per request and never stored by the service.

## DNS and TLS

With a real `TENON_DOMAIN` and ports 80/443 open, Caddy obtains and renews a Let's Encrypt
certificate automatically; no certificate files are configured by hand. The firewall should allow
only 80/tcp and 443/tcp (plus 443/udp for HTTP/3) to the host.

For `TENON_DOMAIN=localhost` Caddy uses its **internal CA**, which clients do not trust by default.
Trust it explicitly for local testing:

```sh
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# then import caddy-root.crt into the OS/browser trust store
```

Do not use the internal CA for a public deployment.

## Backups and restore

The database lives in the `tenon-data` volume. A naive copy of a live SQLite file can be
inconsistent, so stop the service (or checkpoint) and use SQLite's online backup:

```sh
docker compose stop service
volume=$(docker volume inspect --format '{{ .Mountpoint }}' "$(basename "$PWD")_tenon-data")
sqlite3 "$volume/tenon.db" ".backup '/var/backups/tenon-$(date +%F).db'"
docker compose start service
```

Back up `bundles/` and `.env` separately (they are host files), and copy the backup off the host.

To restore: `docker compose stop service`, copy the backup over `tenon.db` in the same volume (or
restore with `sqlite3 "$volume/tenon.db" ".restore '<backup>'"`), then `docker compose start
service`. Keep the app key and `.env` with the backup set or the service cannot use the restored
history.

## Rotating the token and webhook secret

1. Generate a new value with `openssl rand -hex 32`.
2. Update `TENON_API_TOKEN` (or `TENON_WEBHOOK_SECRET`) in `.env`.
3. `docker compose up -d` recreates the service with the new environment.
4. Update API clients, and the webhook secret in the GitHub App settings.

The token is compared per request and never stored, so old tokens stop working immediately. Keep
the old webhook secret configured in GitHub only until the switchover is done.

## Upgrades

```sh
git pull
docker compose pull          # Caddy
docker compose build --pull  # the service image
docker compose up -d
```

Take a backup first. SQLite migrations run when the store is opened on startup, so no separate
migration step exists. `docker compose down` keeps the named volumes; `down -v` deletes the
database and Caddy state.

Resource limits are host-sized by default; add `deploy.resources.limits` (cpus/memory) to the
service if the VM runs other workloads.

## Logs

```sh
docker compose logs -f service
docker compose logs -f caddy
```

The service logs to stdout/stderr; the token, webhook secret and key contents are never logged.

## Security checklist

- [ ] TLS only: clients use `https://$TENON_DOMAIN`; port 80 is Caddy's redirect, never the service.
- [ ] A long random `TENON_API_TOKEN` (`openssl rand -hex 32`), rotated on suspicion.
- [ ] `TENON_WEBHOOK_SECRET` set if the webhook route is used.
- [ ] The service runs as `tenon` (uid 10001), root filesystem read-only, `/tmp` tmpfs, all caps
      dropped, `no-new-privileges`.
- [ ] No host port on the service; only Caddy publishes 80/443.
- [ ] `secrets/app.pem` is 0400, owned by 10001, mounted read-only; `.env` is 0600 and uncommitted.
- [ ] The database volume is backed up with `sqlite3 .backup` and a restore has been tested.
- [ ] Host firewall allows only 80/443; SSH is key-only.
