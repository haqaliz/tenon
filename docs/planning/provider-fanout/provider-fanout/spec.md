# Spec: `provider-fanout` (T10c)

- **Feature:** `provider-fanout`
- **PRD:** `docs/planning/provider-fanout/prd.md` (§ M2–M7)
- **Boundary:** the `--repos` CLI path, the per-repo loop, the fan-out report, exits, docs/tests.
  No new pipeline, bundle internals or repo-list parsing.

## Problem slice

The repo list is only useful if `tenon provider migrate` can run the shipped T10b/T5 path once per
listed checkout, keep going after a bad path, open one PR per repo through one remote, and report
every repo honestly.

## In-scope requirements

- Parser: `tenon provider migrate [<repo>] --bundle PATH --repos FILE ...`; `<repo>` becomes optional.
  `<repo>` and `--repos` are mutually exclusive and exactly one is required; a violation is a
  `_Usage` (exit 2) naming both forms. The other flags are unchanged.
- Dispatch in `_provider`: no `--repos` -> the shipped single-repo path byte-for-byte; `--repos` ->
  fan-out.
- Fan-out:
  - `load_bundle` once, `_bundle_config` once (the `--check`/`--require` overrides apply to every
    repo), `load_repos` once.
  - The remote is resolved once when `--open-pr` (injected `remote`, else `gh`/`app`).
  - For each repo in list order: if it is not a directory, record a per-repo result with
    `error="not a directory"` and `exit=1` and continue; otherwise call the shipped `_fix_results`
    with the bundle's specs, collect the changes/results, and set `exit=fix_exit(...)`.
  - A shared spec refusal from `_fix_results` propagates: exit 2, as for one repo. A repo-specific
    failure (missing path, failed proof, refused PR) is per-repo exit 1.
- Report:
  - `ProviderRepoResult(repo, results, exit, error)` in `cli/report.py`; `summary` reuses
    `fix_summary` (zeros for a repo that did not run).
  - Text: `provider: <p>\nmigration: <m>\n\n`, then for each repo `repo: <path>` followed by the fix
    report, or `error: <text>`; then `repos: N, passed: X, failed: Y`. Byte-stable.
  - JSON: `{"command":"provider","provider":...,"migration":...,"repos":[{"repo","results",
    "summary","exit","error"}],"summary":{"repos","passed","failed"}}`, canonical/byte-stable; the
    per-repo results reuse `fix_result_dict`.
  - Overall exit: 0 iff every repo exit is 0; otherwise 1.
- Docs: README and ARCHITECTURE state the repo-list format, the fan-out command, per-repo PRs, the
  exit codes and the T10d deferral.
- Tests: the loader is covered in `provider-repos`; the CLI fan-out is covered here with copies of
  `tests/fixtures/repos/proof-basic` and a temp bundle whose check is
  `[sys.executable, "-c", "import acme.billing"]`. Offline.

## Out-of-scope

- Installed/hosted fan-out, webhooks, installation discovery, a database, deployment.
- Parallelism, retries, rollback.
- Provider branding in the PR body.
- New pipeline stages/proof levels.

## Acceptance criteria

- **AC1 — Fan-out passes.** Two fixture copies and one bundle exit 0; each repo has its own results
  and a `TESTS_PASSED` proof; the checkouts are unchanged.
- **AC2 — Partial failure.** A missing directory in the list is a per-repo `not a directory`
  failure while the other repos still run; the summary counts it; the overall exit is 1.
- **AC3 — JSON.** The fan-out envelope has exactly `command`, `provider`, `migration`, `repos`,
  `summary`; each repo has `repo`, `results`, `summary`, `exit`, `error`; byte-stable.
- **AC4 — Text.** The provider header, one `repo:` block per repo (fix report or error) and the
  `repos/passed/failed` summary.
- **AC5 — Selection.** `<repo>` alone is T10b unchanged; `--repos` alone fans out; both or neither is
  exit 2 with a named message; `--json` errors are one object.
- **AC6 — PR.** `--open-pr` runs per repo with one remote; the app remote is constructed once; the
  T5 gate, `--allow-below-required` and the no-merge stance are unchanged.
- **AC7 — Errors/overrides.** `--check`/`--require` reach every repo; a bad bundle, repos file or
  require exits 2 with a named message and no traceback; a shared spec refusal exits 2.
- **AC8 — Docs/regression.** README/ARCHITECTURE updated; `check`/`fix`/`probe`/`corpus` and all
  prior tests stay green.

## Dependencies and sequencing

- Depends on `provider-repos` and the shipped T10b/T5 path; last.

## Open questions / risks

- No rollback: earlier repos may have PRs when a later repo fails; the report names every repo.
- Sequential by design; `--parallel` is a later card.
- One token mint per run; a long fan-out may outlive it.
