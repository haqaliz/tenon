# Spec: `app-remote` (T10a)

- **Feature:** `github-app`
- **PRD:** `docs/planning/github-app/prd.md` (§ M3, M5)
- **Boundary:** the `Remote` implementation. No token minting/API client internals, no CLI.

## Problem slice

The writer needs the same four host operations it already trusts, now under an app identity, without
leaking the token or adding a merge/default-branch path.

## In-scope requirements

- `GitHubAppRemote(token_provider, api_url="https://api.github.com", transport=..., runner=...,
  timeout=30)` implementing the shipped `Remote` protocol.
- `_owner_repo(repo)`: run `git remote get-url origin` in the clone via the runner; parse
  `https://github.com/owner/repo(.git)` and `git@github.com:owner/repo(.git)`; a non-GitHub/parse
  failure is `RemoteError`.
- Token: mint once per remote instance and reuse; a mint failure is `RemoteError`.
- `default_branch(repo)`: `GET /repos/{owner}/{repo}` -> `default_branch`; missing -> `RemoteError`.
- `branch_exists(repo, branch)`: `GET /repos/{owner}/{repo}/git/ref/heads/{branch}`; 200 true,
  404 false, anything else `RemoteError`.
- `push(repo, branch)`: `git -c credential.helper=!f() { echo "username=x-access-token"; echo
  "password=$TENON_GITHUB_TOKEN"; }; f push origin <branch>` with `TENON_GITHUB_TOKEN` in the
  subprocess env and `GIT_TERMINAL_PROMPT=0`; no `--force`; no token in argv; a failure is
  `RemoteError` with the stderr tail, token redacted to `***`.
- `create_pr(repo, *, branch, base, title, body, draft)`: `POST /repos/{owner}/{repo}/pulls` with
  `head=branch`, `base`, `title`, `body`, `draft`; return `html_url`; a missing URL is `RemoteError`.
- No merge/default-branch/force path. The T5 `write_pr` guardrails are untouched.

## Out-of-scope

- The token/API internals, CLI, provider fan-out, hosted service.
- GitHub Enterprise Server specifics beyond `api_url`.
- Windows credential-helper portability.

## Acceptance criteria

- **AC1 — Parse.** HTTPS/SSH GitHub URLs parse to owner/repo; a non-GitHub/relative URL is
  `RemoteError`.
- **AC2 — Default/branch.** The API paths are exact; `default_branch` returns the field; a 200/404
  branch check returns True/False; a 500 is `RemoteError`.
- **AC3 — Push.** The argv contains the credential helper and `origin <branch>`, no token and no
  `--force`; the env has `TENON_GITHUB_TOKEN` and `GIT_TERMINAL_PROMPT=0`; a failure maps to
  `RemoteError`.
- **AC4 — Redaction.** A stderr tail containing the token is returned with `***`, not the token.
- **AC5 — PR.** The body has head/base/title/body/draft; the `html_url` is returned; a missing URL
  is `RemoteError`.
- **AC6 — Token.** The provider is called once per remote instance; a mint failure is `RemoteError`.
- **AC7 — No secret leak.** The token/JWT never appears in the argv, the PR body or an error detail.

## Dependencies and sequencing

- Depends on `app-token`; before `app-cli`.
- Reuses the shipped `Remote`/`RemoteError`/`write_pr`.

## Open questions / risks

- The credential helper runs under git's shell; a malicious hook/`GIT_TRACE` can still expose the
  token. Self-hosted operator responsibility; documented.
- `git remote get-url origin` is a local command; the clone's origin is the real remote (T5).
- The app needs contents:write + pull_requests:write; a 403 is a named error.
