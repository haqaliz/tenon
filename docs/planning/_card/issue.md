# Card: feat/github-app

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer and GitHub App (hosted)** — first slice: **GitHub App remote**
  (`docs/technical/CAPABILITY_ROADMAP.md:16`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), first slice
- **Branch:** `feat/github-app/aliz`
- **Worktree:** `.claude/worktrees/feat-github-app`

## Brief

T5 ships PRs through the user's own `gh` CLI and auth. The hosted/provider layer needs an app
identity instead: a GitHub App installation token, no personal `gh` login, no interactive prompt, and
the same four `Remote` operations T5 already depends on.

T10a adds a `GitHubAppRemote` implementing the T5 `Remote` protocol:
- mint a GitHub App JWT from the app id + private key, exchange it for an installation token;
- `default_branch` and `branch_exists` via the GitHub REST API;
- push the proven branch with the token through a git credential helper (no token in argv);
- `create_pr` via the REST API, draft flag included;
- CLI `tenon fix --open-pr --remote app` with app id/installation/private-key inputs.

The provider-facing migration bundle, customer fan-out, webhooks and a hosted service are T10b/T10c.
This card is the hosted writer foundation, not the marketplace.

The hard rules do not change: no merge, no default-branch push, no force; the app token is a secret
that never appears in argv, a report or an error detail; the remote is opt-in and self-hosted; the
tests are offline with an injected transport/runner and a test RSA key.

## Constraints carried in from the repo

- `CLAUDE.md` §4–5: no code egress by default; no merge/default branch; the app is the user's own
  installation, self-hosted.
- `CLAUDE.md` tech direction: "OSS CLI first, GitHub App and hosted later"; Python core; the app is
  opt-in.
- T5's `Remote` protocol and `RemoteError` are the seam; the writer's guardrails stay untouched.
- `docs/ROADMAP.md` Phase 3: GitHub App, provider-facing PRs, hosted; T11 on demand.
- Offline tests: no live GitHub, no network; a fake HTTP transport and git runner.

## Scope fence

Not this card: the provider migration bundle/fan-out, webhook server, tenancy/database, hosted
deployment, OAuth/user tokens, T11 languages. Those are T10b/T10c.
