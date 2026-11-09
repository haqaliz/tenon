# Card: feat/provider-installed

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer and GitHub App (hosted)** — fourth slice: **installed repo
  discovery and fan-out** (`docs/technical/CAPABILITY_ROADMAP.md:16`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), fourth slice
- **Branch:** `feat/provider-installed/aliz`
- **Worktree:** `.claude/worktrees/feat-provider-installed`

## Brief

T10c fans a bundle out over a local repos file. A provider using the GitHub App still has to clone
every customer checkout by hand and keep the list current. The app already knows its installation's
repositories.

T10d adds **installed repo discovery and fan-out**:
- a selector that lists the app installation's repositories through the GitHub API
  (`GET /installation/repositories`, paginated) instead of a local repos file;
- one temp clone per repo using the installation token through the existing credential-helper
  mechanism (never in argv or a URL), then the shipped T10b/T10c pipeline and one PR per repo;
- the same per-repo text/JSON fan-out report, per-repo failure isolation and exit codes as T10c;
- no webhooks, database, deployment or hosted service in this slice.

The hard rules do not change: the app identity is the T10a one; T5/T10a guardrails apply per repo;
no merge/default branch/force; the token never enters argv or the report; offline tests use the
injectable API transport and local fixture remotes.

## Constraints carried in from the repo

- T10a's `GitHubAppToken`, `GitHubApi` (injectable transport), `GitHubAppRemote` and its
  `TENON_GITHUB_TOKEN` credential helper are the seams to reuse; no new auth scheme.
- T10c's `ProviderRepoResult`, `render_fanout_*` and per-repo exit semantics are the report seam.
- `CLAUDE.md` §1–5: execution decides, honest levels, no merge/default branch, no egress by default.
- Offline tests: fake API transport, fixture repos, local git remotes; no network/live GitHub.

## Scope fence

Not this card: webhooks, installation discovery events, a database, a hosted service, deployment,
parallelism, rollback, provider branding, T11.
