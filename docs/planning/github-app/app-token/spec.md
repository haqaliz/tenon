# Spec: `app-token` (T10a)

- **Feature:** `github-app`
- **PRD:** `docs/planning/github-app/prd.md` (§ M1, M2, M6)
- **Boundary:** token minting and the REST client. No Remote/CLI.

## Problem slice

The app remote needs a scoped installation token and a small, testable REST client. Both are pure
enough to test offline with a fake transport and a generated RSA key.

## In-scope requirements

- `TokenProvider` protocol `token() -> str`.
- `GitHubAppToken(app_id, installation_id, private_key_pem, transport, api_url="https://api.github.com",
  now=None)`:
  - `token()` builds a JWT with `iss=str(app_id)`, `iat=now-60`, `exp=now+600`, RS256 via PyJWT;
  - `POST {api_url}/app/installations/{installation_id}/access_tokens` with
    `Authorization: Bearer <jwt>`, `Accept: application/vnd.github+json`,
    `X-GitHub-Api-Version: 2022-11-28`;
  - parse `token`; a non-2xx, invalid JSON or missing token is `RemoteError` with a capped message
    that contains neither the JWT nor the token.
- `StaticToken(token)` returns a fixed token.
- `GitHubApi(api_url, transport, timeout=30)`:
  - `request(method, path, token, body=None) -> dict`: JSON in/out, the same headers plus
    `Authorization: Bearer <token>`; 2xx parses JSON (empty -> `{}`); non-2xx raises
    `GitHubApiError(RemoteError)` with `status` and a capped API message.
  - The transport signature is `(method, url, headers, body: str|None) -> (status, headers, body)`;
    the default uses `urllib.request` with a timeout.
- Packaging: `pyproject.toml` gets `[project.optional-dependencies] app = ["pyjwt>=2.10",
  "cryptography>=43"]` and the same in the dev group; `uv.lock` updated; the core install unchanged.
- Export from `tenon.pr` (or a new `tenon.app`? Keep `tenon.pr` for the remote surface; the app
  classes live in `src/tenon/pr/app.py` and `src/tenon/pr/api.py`).

## Out-of-scope

- The Remote, CLI, provider fan-out, webhooks, hosted service.
- Token caching beyond the remote's single mint; expiry refresh.

## Acceptance criteria

- **AC1 — JWT.** The claims are `iss`, `iat`, `exp` with the expected values; the signature verifies
  with the test public key; the algorithm is RS256.
- **AC2 — Exchange.** The request method/URL/headers/body are correct; a 201 with `token` returns it;
  a 401/500/invalid body raises `RemoteError` without the JWT/token in the message.
- **AC3 — Static.** `StaticToken("t")` returns `"t"`; an empty token raises.
- **AC4 — API.** A 200 JSON returns the dict; an empty body returns `{}`; the headers include the
  bearer/version/accept; a 404/500 raises `GitHubApiError` with `status` and a capped message.
- **AC5 — Transport.** The injected transport receives the exact method/url/headers/body; no
  network in tests.
- **AC6 — Packaging.** The optional extra and dev group are present; `uv run pytest` sees PyJWT and
  cryptography.

## Dependencies and sequencing

- First; `app-remote` consumes the token provider/API.
- New dependencies: PyJWT + cryptography (optional extra + dev).

## Open questions / risks

- The default `urllib` transport is not exercised by a live call; the injected transport is the
  contract. A later integration test can hit a local fake server.
- Clock skew is the API's error; the JWT window is 60 s back / 10 min forward.
- The private key is a PEM string; the CLI reads a path.
