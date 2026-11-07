# PRD: GitHub App remote (T10a)

- **Slug:** `github-app`
- **Capability:** T10 in `docs/technical/CAPABILITY_ROADMAP.md` — **first slice, GitHub App remote**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, first slice
- **Status:** implemented 2026-11-08 (`src/tenon/pr/{app,api,github_app}.py`, CLI; 1,635 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T5 ships PRs through the user's own `gh` CLI and personal auth. The provider/hosted layer needs an app
identity: a GitHub App installation token, no personal login, no interactive prompt, and the same
four `Remote` operations T5 already depends on. Without that seam, every hosted or provider-facing
PR would require a human's `gh` session on the machine that runs Tenon.

T10a adds a `GitHubAppRemote` implementing the T5 `Remote` protocol: mint an app JWT from the app id
and private key, exchange it for an installation token, use the GitHub REST API for the default
branch, branch existence and PR creation, and push the proven branch with the token through a git
credential helper. The CLI gains `tenon fix --open-pr --remote app`.

The provider migration bundle, customer fan-out, webhooks and a hosted service are T10b/T10c. This
card is the hosted writer foundation, not the marketplace.

The dangerous shortcuts are rejected here: putting the token in the remote URL or argv, logging it,
letting the app merge or push the default branch, and pretending an app installation is a sandbox.
The token is a secret; the remote only adds a branch and a PR.

**For whom:** a provider/self-hoster running Tenon against installed repositories, a developer using
an app installation instead of `gh`, and T10b/T10c, which need this remote.

## Goals & Success Metrics

1. **App identity.** A GitHub App id + installation id + private key mint a JWT and exchange it for
   an installation token; a static token is available for tests/operators.
2. **Same Remote contract.** `GitHubAppRemote` implements `default_branch`, `branch_exists`, `push`
   and `create_pr`; T5's `write_pr` and all guardrails are unchanged.
3. **Token-safe.** The token never appears in a command argument, a report, an error detail or the
   git remote URL; the push uses a credential helper that reads it from the subprocess environment.
4. **CLI.** `tenon fix --open-pr --remote app` with app id/installation/private-key flags or env;
   the default remains the user's `gh`.
5. **Offline tests.** A test RSA key, a fake HTTP transport and a fake git runner; no live GitHub.
6. **Packaged lightly.** `pyjwt` + `cryptography` live in an optional `[app]` extra and the dev
   group; the core install stays as it is.

## User Personas & Scenarios

- **Self-hoster.** Creates a GitHub App with contents/pull-request write permissions, installs it on
  a repo, exports the app id/installation/private key, runs
  `tenon fix ... --open-pr --remote app`; a PR opens under the app identity.
- **Provider (later).** T10b uses the same remote to open migration PRs for installed customer repos.
- **Operator.** Uses a pre-minted installation token (`StaticToken`) for a short-lived CI run.
- **Reviewer.** The PR is a normal branch/PR from the app; no merge, no default-branch push.

Scenario: the M0.3 Stripe rename on a repo installed with the app. T5 clones the clean checkout,
commits the proven diff, pushes with the app token, and creates a PR via the API; the title/body
state `TESTS_PASSED` exactly as with `gh`.

## Requirements

### Must have

- **M1 — Token provider.** `TokenProvider` protocol `token() -> str`; `GitHubAppToken(app_id,
  installation_id, private_key, transport, now)`:
  - JWT claims `iss=app_id`, `iat=now-60`, `exp=now+600`, RS256;
  - `POST {api}/app/installations/{installation_id}/access_tokens` with `Authorization: Bearer
    <jwt>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`;
  - return `token`; a non-2xx/invalid body is `RemoteError` with a capped message and no JWT/token.
  `StaticToken(token)` returns a fixed token.
- **M2 — API client.** `GitHubApi(api_url="https://api.github.com", transport=...)`: a stdlib
  `urllib.request` transport, JSON in/out, a timeout, a per-request bearer token, and
  `RemoteError` on a non-2xx (message from the API, capped). The transport is injectable for tests.
- **M3 — Remote.** `GitHubAppRemote(token_provider, api_url=..., transport=..., runner=...)`:
  - parse the clone's `origin` URL (HTTPS or SSH) to `owner/repo`;
  - `default_branch(repo)`: `GET /repos/{owner}/{repo}` -> `default_branch`;
  - `branch_exists(repo, branch)`: `GET /repos/{owner}/{repo}/git/ref/heads/{branch}`; 200 true,
    404 false, else `RemoteError`;
  - `push(repo, branch)`: `git push origin <branch>` with
    `-c credential.helper=!f() { echo "username=x-access-token"; echo "password=$TENON_GITHUB_TOKEN"; }; f`
    and `TENON_GITHUB_TOKEN` in the subprocess env; `GIT_TERMINAL_PROMPT=0`; never `--force`; no
    token in argv; a failure is `RemoteError` with the stderr tail (token redacted if present);
  - `create_pr(repo, *, branch, base, title, body, draft)`: `POST /repos/{owner}/{repo}/pulls`
    with `head=branch`, `base`, `title`, `body`, `draft`; return `html_url`.
- **M4 — CLI.** `tenon fix --open-pr --remote gh|app` (default `gh`). For `app`:
  `--app-id`, `--app-installation-id`, `--app-private-key PATH`; env fallbacks
  `TENON_GITHUB_APP_ID`, `TENON_GITHUB_APP_INSTALLATION_ID`, `TENON_GITHUB_APP_PRIVATE_KEY`.
  Missing inputs, an unreadable key or a bad combination is exit 2 with a named error. `--open-pr`
  with `app` constructs the app remote; the existing `write_pr` path is unchanged.
- **M5 — Security/guardrails.** No merge/default-branch/force path; the token is not in argv,
  reports, error details or the git remote URL; the app permissions are the user's responsibility
  (contents:write, pull_requests:write) and documented.
- **M6 — Packaging.** `pyproject.toml` gets an optional `[project.optional-dependencies] app =
  ["pyjwt>=2.10", "cryptography>=43"]` and the same two in the dev group; `uv.lock` records them.
  The core install does not grow.
- **M7 — Tests.** A generated test RSA key; JWT claims/signature; the token exchange; API
  default/branch/PR (200/404/error/draft); the owner/repo parse (HTTPS/SSH); the push argv/env (no
  token in argv, token in env); a redacted error; the CLI app/gh paths and missing-input errors.
  Offline, no live GitHub.
- **M8 — Documentation.** The app permissions, the env/flags, the self-hosted scope and the deferred
  provider fan-out are documented in the README/architecture and the PRD.

### Should have

- **S1 — Token reuse.** The remote mints the installation token once and reuses it for its lifetime;
  a later hosted service can add expiry caching.
- **S2 — API version header** on every request.
- **S3 — `--api-url`** for a self-hosted GitHub Enterprise/fake endpoint; default github.com.

### Nice to have

- **N1 — Webhook/installation discovery**; T10b.
- **N2 — Provider migration bundle/fan-out**; T10b.
- **N3 — A hosted deployment**; T10c.

## Data Model

```
TokenProvider (Protocol)
  token() -> str

GitHubAppToken(app_id, installation_id, private_key_pem, transport, now)
StaticToken(token)

GitHubApi(api_url, transport, timeout)
  request(method, path, body=None, token=None) -> dict

GitHubAppRemote(token_provider, api_url, transport, runner, timeout)
  default_branch(repo) -> str
  branch_exists(repo, branch) -> bool
  push(repo, branch) -> None
  create_pr(repo, *, branch, base, title, body, draft) -> str
```

`RemoteError` (shipped) is the only failure type the writer maps; the app errors carry a capped
message, never a secret. The T5 `Remote` protocol is unchanged.

## API Contract

```python
from tenon.pr import GitHubAppRemote, GitHubAppToken

remote = GitHubAppRemote(
    GitHubAppToken(app_id=123, installation_id=456, private_key=pem),
)
result = write_pr(proposal, proof, "path/to/repo", remote=remote)
result.url  # the app-opened PR
```

CLI:

```sh
tenon fix repo --old old.json --new new.json --check "python -m pytest -q" \
  --open-pr --remote app \
  --app-id 123 --app-installation-id 456 --app-private-key app.pem
```

No merge, no default-branch push, no token in argv.

## Technical Considerations

- **Why a GitHub App remote.** The hosted/provider layer cannot depend on a human's `gh` login. An
  installation token is scoped to the installed repo and can be minted by the app.
- **Why the T5 Remote protocol.** The writer's clone/commit/push/PR ordering, dirty-tree and
  default-branch guardrails are already tested; the app is a new host adapter, not a new pipeline.
- **Why the credential helper.** `git push` is the proven branch/commit path; a helper that reads
  `TENON_GITHUB_TOKEN` from the environment keeps the token out of argv, the URL and git config.
  The helper is a fixed shell snippet run by git; the token is data in the env.
- **Why the REST API for the other three.** `default_branch`, branch existence and PR creation are
  small JSON calls; `urllib` avoids a new HTTP dependency. The transport is injectable so tests are
  offline.
- **Why an optional extra.** `PyJWT`/`cryptography` are only needed for app JWT minting; the core CLI
  and the `gh` remote stay dependency-light. The dev group installs them for the test suite.
- **Why no provider fan-out.** T10a is the app identity/writer; the provider bundle, installation
  discovery and customer fan-out need a service/database and are T10b/T10c.
- **Secret handling.** The private key path is read at startup; the PEM is never logged; the JWT and
  installation token are never in an error message; the token is redacted from a git stderr tail.

## Risks & Open Questions

- **Token leakage.** The helper keeps it out of argv/URL; a malicious git hook or `GIT_TRACE` could
  log it. The app is self-hosted; the operator controls the environment. Documented.
- **App permissions.** The app needs contents:write and pull_requests:write on the installed repo;
  a missing permission is a 403 `RemoteError`. The README lists the required permissions.
- **Private key storage.** The key is a high-value secret; the CLI reads a path/env and never writes
  it. A hosted service needs a secret manager; T10c.
- **Clock skew.** The JWT `iat` is 60 s in the past and `exp` 10 min ahead; a skewed host can fail.
  The error names the API message.
- **Git credential helper portability.** The `!f() { ... }; f` helper runs under git's shell on
  macOS/Linux; Windows is not a target yet.
- **GitHub Enterprise.** `--api-url` supports a different API host; the git remote stays the origin.
- **No provider fan-out.** A vendor cannot push to customers in this card; the remote is the
  foundation. The hosted service/webhooks are T10b/T10c.
- **Open question — should the app use the REST commit API instead of git push?** `git push` reuses
  T5's tested commit and is simpler; the token-safe helper is the tradeoff.
- **Open question — should the CLI read the private key from a file or env?** Both: a path flag is
  the normal case; the env is for CI. The key content in an env is supported only via a path value
  in this card to avoid accidental process-env exposure.

## Out of Scope

- Provider migration bundle, customer fan-out, installation discovery, webhooks.
- A hosted service/database/tenancy/deployment.
- OAuth/user tokens, GitHub Enterprise Server specifics, Windows.
- Merging, default-branch pushes, force pushes.
- T11 languages.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `app-token` | `TokenProvider`, `GitHubAppToken` (JWT + installation exchange), `StaticToken`, `GitHubApi` (transport/errors). No Remote/CLI. |
| `app-remote` | `GitHubAppRemote` (owner/repo parse, default branch, branch exists, token-safe push, PR create), redaction. No CLI. |
| `app-cli` | `--remote app` and app flags/env, construction, exit codes, packaging (`[app]` extra/dev deps), docs. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The hosted/provider layer cannot use a personal `gh` login. |
| User understanding | 🟢 | Self-hoster/operator/provider/reviewer scenarios; the app permissions are explicit. |
| Success metrics | 🟢 | App token, same Remote contract, token-safe push, CLI, offline tests. |
| Scope clarity | 🟢 | App remote only; fan-out/hosted/webhooks excluded. |
| Edge cases & risks | 🟡 | Token leakage via hooks/tracing and private-key storage are operational risks, documented. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | PyJWT/cryptography wheels; REST/git are standard; tests are offline. |
| Go-to-market | 🟢 | The foundation for provider-facing PRs, where vendors may pay. |

**Areas to strengthen before sharing:** the app permissions and private-key handling are the
operator's responsibility; the README must be blunt that this is a self-hosted app, not a Tenon
hosted service. The provider fan-out is not here.

**The question I would want answered before greenlighting this:** *If the app installation has
contents:write on every customer repo, a bug in Tenon could push to the default branch or open
unwanted PRs. What bounds it?* The answer this card records: the writer's existing guardrails (clean
tree, base branch refusal, no force, no merge) plus the app's branch-only push; the app token is
scoped to installed repos and the operator controls the installation. A hosted multi-tenant service
needs more (T10c).
