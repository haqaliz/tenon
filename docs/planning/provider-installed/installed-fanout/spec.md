# Spec: `installed-fanout` (T10d)

- **Feature:** `provider-installed`
- **PRD:** `docs/planning/provider-installed/prd.md` (§ M2–M5)
- **Boundary:** the `--installed` selector, app/token/remote wiring, the clone-and-run loop, report
  reuse, exits, docs/tests. No new lister/clone internals.

## Problem slice

Discovery and cloning are only useful if `tenon provider migrate --installed` runs the shipped
bundle over every installation repo, isolates per-repo failures and reports with the T10c shape.

## In-scope requirements

- Parser: add `--installed`; `<repo>`, `--repos FILE` and `--installed` are mutually exclusive and
  exactly one is required. Zero or more than one is a `_Usage` (exit 2, named; `--json` one object).
- App identity: factor the T10a app resolution out of `_remote` into `_app(args) ->
  (GitHubAppToken, api_url)`; `_remote` behavior is unchanged. `--installed` uses `_app`; missing
  app id/installation id/key or an unreadable key is a named usage error.
- `--installed --remote gh` is a usage error (`--installed requires --remote app`); `--remote` is
  otherwise only meaningful with `--open-pr`, as before.
- Run:
  - Load the bundle and `_bundle_config` once (the `--check`/`--require` overrides apply to every
    repo), then mint the token once, list the repos once.
  - A token/list failure aborts with exit 2 and a named message.
  - With `--open-pr`, construct `GitHubAppRemote(StaticToken(token), api_url=...)` once (or use the
    injected remote); without it, no remote and no PR call.
  - For each repo in API order: `with clone_repo(repo, token) as checkout:` run the shipped
    `_fix_results`; collect the results and `fix_exit`. A `RemoteError` from the clone is a per-repo
    `error` (capped, token-free) with `exit=1`; the remaining repos still run. A shared spec refusal
    still aborts with exit 2.
  - The report uses T10c's `ProviderRepoResult`/renderers with `repo = full_name`; text/JSON are the
    same envelopes; the overall exit is 0 iff every repo exit is 0, else 1.
- Tests: fake API transport for discovery; local fixture clones for the CLI; two repos, a per-repo
  clone failure, one token mint, one app remote, dry run, selectors, `--remote gh`, missing app
  flags, discovery failure, overrides, text/JSON, byte stability. Offline.
- Docs: README/ARCHITECTURE state the selector, app identity, temp clone, report, exits and the
  no-service boundary.

## Out-of-scope

- Webhooks, installation events, a database, deployment, a hosted service.
- Parallelism, retries, rollback, filtering.
- Provider branding; T11 languages; new proof levels.

## Acceptance criteria

- **AC1 — Fan-out.** Two installation repos clone and pass with exit 0; each report entry is
  `owner/name` with a `TESTS_PASSED` proof; no local checkout is written.
- **AC2 — Partial failure.** A clone error for one repo is a per-repo `error`, the other repo still
  runs, the summary counts the failure and the exit is 1.
- **AC3 — Report.** The text and JSON are the T10c fan-out envelopes with `repo` = `owner/name`;
  JSON is byte-stable.
- **AC4 — Selection.** `<repo>`/`--repos`/`--installed` alone work; zero or two+ is exit 2 with a
  named message; `--installed --remote gh` is exit 2; `--json` errors are one object.
- **AC5 — Token/remote.** One token mint per run; discovery and every clone get it; `--open-pr`
  constructs the app remote once with the same token; the dry run makes no PR call.
- **AC6 — Gate.** The T5 required-level gate, `--allow-below-required` and the no-merge stance apply
  per repo; a refused PR makes the overall exit 1.
- **AC7 — Errors.** Missing app flags, an unreadable key, a token/list failure and a shared bad spec
  exit 2 with a named message and no traceback; the token never appears in output.
- **AC8 — Docs/regression.** README/ARCHITECTURE updated; `check`/`fix`/`probe`/`corpus` and all
  prior tests stay green.

## Dependencies and sequencing

- Depends on `installed-discovery` and the shipped T10a/T10c paths; last.

## Open questions / risks

- Sequential clones and no retries; a large installation is slow and can hit rate limits.
- No rollback; earlier PRs may exist when a later clone fails.
- One token per run; an expired token surfaces as per-repo clone/PR errors.
