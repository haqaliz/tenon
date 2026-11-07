# Spec: `app-cli` (T10a)

- **Feature:** `github-app`
- **PRD:** `docs/planning/github-app/prd.md` (§ M4, M6, M8)
- **Boundary:** the `--remote app` CLI, construction, errors and docs. No remote/token internals.

## Problem slice

The app remote is only usable if `tenon fix --open-pr` can construct it from the operator's app
id/installation/private key, with the existing `gh` default untouched.

## In-scope requirements

- `tenon fix` gains `--remote gh|app` (default `gh`), `--app-id`, `--app-installation-id`,
  `--app-private-key PATH`, `--api-url URL`.
- Env fallbacks: `TENON_GITHUB_APP_ID`, `TENON_GITHUB_APP_INSTALLATION_ID`,
  `TENON_GITHUB_APP_PRIVATE_KEY` (a path), `TENON_GITHUB_API_URL`.
- `--remote` requires `--open-pr` (an explicit remote without it is a usage error); the default
  `gh` constructs `GitGhRemote`.
- For `app`: read the private key path (a missing/unreadable file -> exit 2), construct
  `GitHubAppRemote(GitHubAppToken(app_id, installation_id, pem, ...), api_url=...)`; missing
  app id/installation/key -> exit 2 with a named message.
- The `write_pr` call is unchanged; the app remote is passed in.
- Docs: the required app permissions, the flags/env, the self-hosted scope, the deferred
  provider fan-out/hosted service.
- Tests: the app path constructs the remote with the args (monkeypatched class); the gh default; a
  missing flag/key exits 2; `--remote` without `--open-pr` exits 2; the existing fix tests green.
  No live GitHub.

## Out-of-scope

- The remote/token internals, provider bundle/fan-out, webhooks, hosted deployment.
- OAuth/user tokens, GitHub Enterprise Server specifics.

## Acceptance criteria

- **AC1 — Default.** No `--remote` -> `GitGhRemote`; the existing tests unchanged.
- **AC2 — App.** `--remote app --open-pr` with all inputs constructs `GitHubAppRemote` with the app
  id/installation/key/API URL; the fake `write_pr` sees it.
- **AC3 — Env.** Missing flags fall back to the env; a flag wins over the env.
- **AC4 — Errors.** Missing app id/installation/key, an unreadable key and `--remote` without
  `--open-pr` each exit 2 with a named message; `--json` errors are one object; no traceback.
- **AC5 — Docs.** The README/architecture state the app permissions, env/flags, self-hosted scope
  and T10b/T10c deferral.
- **AC6 — Regression.** The check/fix/probe/corpus commands and all prior tests stay green.

## Dependencies and sequencing

- Depends on `app-remote`; last.
- The packaging extra/dev deps land with `app-token`.

## Open questions / risks

- A private key path in an env is supported; key content in an env is not, to avoid process-env
  exposure.
- `--remote` without `--open-pr` is a usage error rather than a silent no-op.
- The app remote is self-hosted; no webhook/installation discovery in this card.
