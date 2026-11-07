# Spec: `provider-cli` (T10b)

- **Feature:** `provider-bundle`
- **PRD:** `docs/planning/provider-bundle/prd.md` (§ M3–M7)
- **Boundary:** `tenon provider migrate`, the fix-flow reuse, the provider report, flags/errors/docs.
  No new pipeline or bundle internals.

## Problem slice

The bundle is only useful if a provider can run it against a customer repo with the same proof and
PR guardrails as `fix`, and read a report that names the provider/migration without changing the PR.

## In-scope requirements

- `tenon provider migrate <repo> --bundle PATH [--open-pr] [--remote gh|app] [--app-id ID]
  [--app-installation-id ID] [--app-private-key PATH] [--api-url URL] [--check CMD]
  [--require LEVEL] [--allow-below-required] [--allow-unverified] [--json]`.
- Build the `CliConfig` from the bundle (locate/commands/require/source/language/breaking_only); apply
  `--check`/`--require` via `overrides`.
- Refactor the fix flow into a reusable result function: `_fix_results(...) -> tuple[FixResult,...]`;
  `fix` and `provider migrate` both call it. The provider command must not duplicate the pipeline.
- Run the same `propose`/`prove_plan`/`write_pr`; the exit code is `fix_exit`. `--open-pr` uses
  `_remote(args)` (gh/app) and the T5 gate.
- Text: `provider: <p>` / `migration: <m>` then the fix report. JSON:
  `{"command":"provider","provider":...,"migration":...,"repo":...,"results":[<fix items>],
  "summary":<fix summary>}`, byte-stable. Reuse the fix item/summary helpers (make them public in
  `cli/report.py` without changing the fix envelope).
- Errors: a bad bundle/spec/usage, `--remote` without `--open-pr` -> exit 2 with a named message and
  a `--json` error object; no traceback.
- Docs: the bundle format, the command, the one-repo scope, the T10c deferral (README/ARCHITECTURE).
- Tests: the loader is covered in `provider-bundle`; the CLI on the `proof-basic` repo with a temp
  bundle (check `sys.executable -c "import acme.billing"`), the JSON envelope, `--open-pr` with a
  fake remote, the overrides, the errors, and the existing commands green. Offline.

## Out-of-scope

- Multi-repo/installed fan-out, webhooks, a database, a hosted service.
- Provider branding in the PR body.
- New pipeline stages/proof levels.

## Acceptance criteria

- **AC1 — Run.** A valid bundle on the fixture repo exits 0/1 like `fix`; the diff/proof appear; the
  checkout is unchanged.
- **AC2 — Config.** The bundle's locate/source/language/commands/require/breaking_only reach the
  pipeline; `--check`/`--require` override.
- **AC3 — JSON.** The provider envelope has the exact keys; results reuse the fix items; byte-stable.
- **AC4 — PR.** `--open-pr --remote gh|app` uses the shipped remote; the app flags/env are the same
  as `fix`; a below-required proof obeys the T5 gate.
- **AC5 — Errors.** A bad/missing bundle/spec, an invalid require and `--remote` without `--open-pr`
  exit 2 with a named message; `--json` errors are one object.
- **AC6 — Docs.** The README/architecture state the bundle format, the command, one-repo scope and
  the T10c deferral.
- **AC7 — Regression.** `check`/`fix`/`probe`/`corpus` and all prior tests stay green.

## Dependencies and sequencing

- Depends on `provider-bundle` and the shipped CLI/PR; last.

## Open questions / risks

- The provider text/JSON is additive; the fix envelope is unchanged.
- The bundle's commands are operator-chosen; the proof runner runs them as-is (not a sandbox).
- No provider note in the PR; T10c can add one.
