# Spec: `installed-discovery` (T10d)

- **Feature:** `provider-installed`
- **PRD:** `docs/planning/provider-installed/prd.md` (§ M1)
- **Boundary:** the installation lister and the authenticated temp clone. No CLI/pipeline/report.

## Problem slice

The app knows its installation's repositories, but Tenon has no way to read that list or to obtain a
clean checkout of one without the operator cloning by hand. This aspect adds both, reusing the T10a
API client, token and credential helper.

## In-scope requirements

- `src/tenon/pr/installed.py`:
  - `InstalledRepo(full_name: str, clone_url: str)` frozen/slots; both non-empty strings.
  - `list_installation_repos(api: GitHubApi, token: str, *, per_page: int = 100) ->
    tuple[InstalledRepo, ...]`.
  - `clone_repo(repo: InstalledRepo, token: str, *, runner=None, timeout: float = 30) ->
    Iterator[Path]` context manager.
- Discovery:
  - `GET /installation/repositories?per_page=<n>&page=<p>` with the installation token.
  - Collect non-archived repos in API order; skip `archived: true`.
  - Stop when a page returns fewer than `per_page` repos (an empty page also stops).
  - A page cap of 100 raises a named `GitHubApiError`; a missing/non-list `repositories`, or an item
    without non-empty `full_name`/`clone_url`, is a named `GitHubApiError`.
- Clone:
  - Create a temp dir (`tenon-installed-` prefix); `git -c <credential helper> clone --depth 1 --
    <clone_url> <dir>` with `TENON_GITHUB_TOKEN` and `GIT_TERMINAL_PROMPT=0` in the child env.
  - The token never enters argv or the clone URL; a failing clone raises `RemoteError` naming the
    repo and scrubbing the token from the captured stderr; the temp dir is removed in `finally`.
  - An `OSError`/timeout is a named `RemoteError`; the temp dir is still removed.
- The T10a credential helper moves to one public constant used by both `GitHubAppRemote` and
  `clone_repo`; no behavior change to the remote.
- Export `InstalledRepo`, `list_installation_repos`, `clone_repo` from `tenon.pr`.

## Out-of-scope

- The CLI, the fan-out loop, the report, PR creation.
- Retries, rate-limit handling, filtering, parallelism.
- Webhooks/installation events or a hosted service.

## Acceptance criteria

- **AC1 — List.** One page returns the repos in order with `full_name`/`clone_url`.
- **AC2 — Pages.** A full page continues to the next; a short/empty page stops; the page cap is a
  named error.
- **AC3 — Archived.** Archived repos are skipped; the rest are kept in order.
- **AC4 — Malformed.** A missing/non-list `repositories`, a non-object item, or a blank
  `full_name`/`clone_url` is a named `GitHubApiError`.
- **AC5 — Clone.** A local fixture repo clones into a temp dir with the expected files; the dir is
  removed after the context exits.
- **AC6 — Clone errors.** A failing clone raises a named `RemoteError` with the repo and no token; the
  temp dir is removed; the token is only in the child env.
- **AC7 — Determinism.** Same API input, same tuple; no clock/network in tests.

## Dependencies and sequencing

- First; `installed-fanout` consumes it.
- Reuses `GitHubApi`, `GitHubAppToken`, `RemoteError`, the T10a credential helper and stdlib git.

## Open questions / risks

- A shallow clone is enough for detect/locate/propose/prove and T5's local re-clone.
- A malicious git hook can read the token from the child env (same as T5's push).
- No retry/rate-limit strategy in this slice.
