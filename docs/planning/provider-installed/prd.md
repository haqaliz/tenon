# PRD: Installed provider fan-out (T10d)

- **Slug:** `provider-installed`
- **Capability:** T10 in `docs/technical/CAPABILITY_ROADMAP.md` — **fourth slice, installed repo
  discovery and fan-out**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, fourth slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T10c fans a bundle out over a local repos file. A provider using the GitHub App still has to clone
every customer checkout by hand and keep the list current. The app already knows its installation's
repositories, and the T10a token can clone them.

T10d adds **installed repo discovery and fan-out**: `tenon provider migrate --installed` lists the
installation's non-archived repositories through the GitHub API, clones each into a temp checkout
with the installation token, runs the shipped T10b/T10c pipeline and opens one PR per repo. The
report, per-repo failure isolation and exit codes are T10c's. There is no webhook, database,
deployment or hosted service in this slice.

The dangerous shortcuts are rejected here: putting the token in argv or a URL, treating an API
listing as a successful run, aborting the whole fan-out when one clone fails, and letting the
installed path skip the T5 proof/PR gate.

**For whom:** a provider running a migration across the app installation's customers, a self-hoster
with an app, the customer reviewing each PR, and a future hosted service.

## Goals & Success Metrics

1. **Discovery.** List every non-archived repository in the app installation, paginated, through
   `GitHubApi` with the installation token; a malformed/error response is a named failure.
2. **One token per run.** Mint once and share it across discovery, cloning and the app remote.
3. **Temp checkout per repo.** Clone with the T10a credential helper (token in the environment, never
   argv/URL), run the pipeline there, always remove the temp dir.
4. **One PR per repo.** Reuse T10a's `GitHubAppRemote` and T5's gate; no merge/default branch/force.
5. **T10c report.** The same text/JSON fan-out envelope, with `repo` = `owner/name`; per-repo
   failures continue; exits 0/1/2 as in T10c.
6. **Offline tests.** Fake API transport, local fixture clones; no network or live GitHub.

## User Personas & Scenarios

- **Provider.** Installs the app on 50 customer orgs, runs `tenon provider migrate --installed
  --bundle ... --open-pr --remote app`; gets 50 temp clones, 48 PRs and 2 named failures.
- **Self-hoster.** Uses the app flags/env for a dry run without `--open-pr`; no PRs, just the report.
- **Customer/reviewer.** Gets the normal T5 PR; no provider branding.
- **Future hosted service.** Reuses discovery/clone/report under a webhook-driven runner.

Scenario: the installation has three repos; one is archived (skipped), one clone fails (per-repo
`error`), one passes with a PR. The summary is `repos: 2, passed: 1, failed: 1`; exit 1.

## Requirements

### Must have

- **M1 — Discovery.** `src/tenon/pr/installed.py`:
  - `InstalledRepo(full_name, clone_url)` frozen/slots.
  - `list_installation_repos(api, token) -> tuple[InstalledRepo, ...]`: `GET
    /installation/repositories?per_page=100&page=N` with the installation token; collect non-archived
    repos in API order; stop on a batch smaller than `per_page`; a page cap (100) guards a
    non-conforming server; a malformed body or API error is a `GitHubApiError`/`RemoteError`.
  - `clone_repo(repo, token) -> Iterator[Path]` context manager: a temp dir, `git -c <credential
    helper> clone --depth 1 -- <clone_url> <dir>` with `TENON_GITHUB_TOKEN` and
    `GIT_TERMINAL_PROMPT=0`; scrub the token from error text; always remove the temp dir.
  - The credential helper moves to one shared constant (imported by `GitHubAppRemote` and the
    clone); no behavior change to T10a.
- **M2 — CLI.** `tenon provider migrate [<repo>|--repos FILE|--installed] --bundle PATH ...`.
  - Exactly one selector; zero or two+ is a `_Usage` (exit 2).
  - `--installed` resolves the T10a app identity from `--app-id`/`--app-installation-id`/
    `--app-private-key`/`--api-url` or their `TENON_GITHUB_APP_*`/`TENON_GITHUB_API_URL` env vars;
    missing values are named usage errors. `--remote gh` with `--installed` is rejected; the app
    identity is implicit. `--open-pr` uses the app remote; without it the run is a dry run.
  - Mint the installation token once; discovery and every clone use it; with `--open-pr` construct
    `GitHubAppRemote(StaticToken(token), api_url=...)` once.
  - Load the bundle and `CliConfig` once (the `--check`/`--require` overrides apply to every repo).
    For each repo in API order: clone; run the shipped `_fix_results`; collect the results and
    `fix_exit`. A clone failure is a per-repo `error` and the remaining repos still run. A discovery,
    token or app-identity failure aborts with exit 2.
  - The temp clone is never the customer's checkout; no local path is written.
- **M3 — Report/exits.** Reuse T10c's `ProviderRepoResult`, text and JSON renderers with
  `repo` = `owner/name`; overall exit 0 iff every repo passes, 1 if any failed, 2 on
  usage/bundle/auth/discovery errors. The token never appears in the report or an error.
- **M4 — Tests/docs.** Discovery pagination/archived/filter/errors; clone success, cleanup, token
  scrub and failure; the CLI with a fake lister/cloner over `proof-basic` copies (two repos, a
  per-repo clone failure, one token mint, one app remote, text/JSON, selectors, errors). Offline.
  README/ARCHITECTURE document the selector, app identity, temp clone, report and the no-service
  boundary.
- **M5 — No service.** No webhooks, installation events, database, deployment, parallelism,
  rollback or hosted runner in this slice.

### Should have

- **S1 — Deterministic order.** API order is report/PR order; no sorting.
- **S2 — Named clone errors.** A per-repo clone failure is a capped, token-free message, never a
  traceback.
- **S3 — Dry run.** `--installed` without `--open-pr` still discovers, clones, runs the pipeline and
  reports; no PR call.

### Nice to have

- **N1 — `--match GLOB`** to select a subset; a later card.
- **N2 — `--parallel N`**; a later card.
- **N3 — Webhook-driven runs / a hosted service**; a later milestone.

## Data Model

```
InstalledRepo
  full_name: str        # owner/name, the report key
  clone_url: str        # https clone URL from the API

ProviderRepoResult     # unchanged from T10c
  repo: str            # owner/name for --installed
  results, exit, error
```

No new report type; the token is never part of either model.

## API Contract

```python
from tenon.pr import GitHubApi, list_installation_repos

api = GitHubApi(api_url="https://api.github.com")
repos = list_installation_repos(api, installation_token)   # tuple[InstalledRepo, ...]
```

CLI:

```sh
tenon provider migrate --installed --bundle stripe-v2500-v2596.json \
  --open-pr --remote app --app-id 123 --app-installation-id 456 --app-private-key app.pem
```

No service, webhooks or database.

## Technical Considerations

- **Why discovery in `pr/`.** The API client, token and credential helper already live there; the
  provider package stays pipeline-free. The CLI is the composition root, as in T10b/T10c.
- **Why one token.** `GitHubAppToken.token()` mints; discovery and clone share the value; the PR
  remote gets a `StaticToken` with the same value. One API mint per run, and the token lives in an
  env var only for the git child.
- **Why a temp clone.** The installed path has no customer checkout. A shallow clone at the default
  branch is enough for detect/locate/propose/prove and for T5's local re-clone; the temp dir is
  removed even on failure.
- **Why non-archived.** An archived repo is read-only; a PR cannot be opened and the migration is
  moot. Skipping it keeps the report honest.
- **Why reuse the T10c report.** The per-repo shape already survives the local-to-installed
  replacement, exactly as the T10c PRD anticipated.
- **Trust boundary.** The API response and the bundle are untrusted input; names/URLs are used as
  data, the token is never printed, and the T5 writer still refuses dirty/default-branch/below-level.

## Risks & Open Questions

- **Token exposure.** The token is in the git child's environment (same as T5's push), not argv; a
  malicious git hook can still read it. Windows is not a target.
- **API limits.** A large installation needs several pages; rate limits and transient failures are
  not retried in this slice.
- **Clone cost.** N shallow clones are still N network operations; sequential by design.
- **No rollback.** Earlier PRs may exist when a later clone fails; the report names every repo.
- **Archived repos are invisible.** The report does not count them; a provider may want a skip count
  later.
- **Open question — should `--installed` allow `--remote gh`?** No: discovery needs the app token, and
  a gh-created PR would not match the app identity. Rejected as a usage error.
- **Open question — should a failed clone be retried?** Not in this slice; retries are a later card.

## Out of Scope

- Webhooks, installation events, a database, deployment, a hosted service.
- Parallelism, retries, rollback.
- Repo filtering (`--match`), archived-skip counts.
- Provider branding in the PR body; T11 languages; new proof levels.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `installed-discovery` | `InstalledRepo`, `list_installation_repos`, `clone_repo`, the shared credential helper. No CLI/pipeline. |
| `installed-fanout` | The `--installed` selector, app/token/remote wiring, the clone-and-run loop, report reuse, exits, docs/tests. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | T10c needs local checkouts; the app already knows the repos. |
| User understanding | 🟢 | Provider/self-hoster/customer/future service; the dry run is concrete. |
| Success metrics | 🟢 | Discovery, one token, temp clone, one PR per repo, T10c report, offline tests. |
| Scope clarity | 🟢 | No service/webhooks/database; filtering and parallelism excluded. |
| Edge cases & risks | 🟡 | Token exposure, rate limits and clone cost are real operational edges. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses T10a's API/token/remote and T10c's loop/report; stdlib + git. |
| Go-to-market | 🟢 | The first zero-manual-clone provider flow; the hosted runner is later. |

**Areas to strengthen before sharing:** a large installation means many sequential clones and API
pages; there is no retry or rate-limit strategy. The honest first step is the per-repo report.

**The question I would want answered before greenlighting this:** *If the installation has 200 repos
and the token expires halfway through, what happens?* The answer this card records: the token is
minted once; a failure after expiry surfaces as per-repo clone/PR errors for the remaining repos,
the report names them, and the operator reruns. Token refresh is a later card.
