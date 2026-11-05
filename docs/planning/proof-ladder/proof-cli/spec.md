# Spec: `proof-cli` (T7)

- **Feature:** `proof-ladder`
- **PRD:** `docs/planning/proof-ladder/prd.md` (§ M8–M9)
- **Boundary:** CLI flags/config, `--require`, exit codes, stage reports, and the `write_pr` call.
  No runner internals, no PR text.

## Problem slice

The CLI advertises the ladder but only accepts two levels and one command. It must assemble a
`ProofPlan` from flags/config, run it, compare the result with `--require`, report every stage, and
pass the requirement to the PR gate.

## In-scope requirements

- `CliConfig` gains `build`, `characterize`, `replay` command tuples (tests stay in `command`).
- `[tenon]` gains `build`, `characterize`, `replay` arrays next to `command`; each is validated like
  `command` (array of non-empty strings).
- `fix` gains `--build CMD`, `--characterize CMD`, `--replay CMD` (each `shlex`-split, no shell);
  `--check` remains tests.
- `a_level`/`_require` accept all five levels; `--require` and `[tenon] require` validate them.
- `fix` builds one `ProofPlan` per run and calls `prove_plan(proposal, repo, plan)` per change.
- `fix_exit` uses `PROOF_RANK`; exit 0 only when every result meets `--require` and every requested
  PR opened.
- Summary counts: `passed`, `characterized`, `replayed`, `build_only`, `unverified`, `prs_opened`,
  `prs_refused` (replace the old `passed`/`unverified` pair).
- Text/JSON: every configured stage's command and both exit codes are shown, with the stage name;
  the level and cause stay at the top. The JSON `proof` object already carries `checks`; add the
  counts.
- `--open-pr` passes `required=config.require` and `allow_below_required`; the new flag is
  `--allow-below-required` with `--allow-unverified` as an alias.
- Python/TS language dispatch is unchanged.

## Out-of-scope

- The runner, result invariants and PR text.
- `tenon check` `--require` (no proof there).
- Per-stage timeouts, generators, T8/T9.

## Acceptance criteria

- **AC1 — Commands.** `--build`/`--characterize`/`--replay` and the `[tenon]` arrays reach the plan;
  a missing flag falls back to the config; an empty stage is omitted.
- **AC2 — Build only.** A build-only fixture with `--require TYPES_BUILD_ONLY` exits 0; the text says
  `TYPES_BUILD_ONLY` and shows the build command/exits.
- **AC3 — Required tests.** The same build-only result with `--require TESTS_PASSED` exits 1.
- **AC4 — Fail closed.** A plan with a green build and a red test exits 1 with
  `UNVERIFIED / TESTS_FAILED_AFTER`; the build pass is visible.
- **AC5 — Open PR.** Below the requirement and no opt-in → no `write_pr` call, exit 1; with
  `--allow-below-required` → the fake `write_pr` sees `required` and `allow_below_required=True`;
  at/above the requirement → the normal call.
- **AC6 — Alias.** `--allow-unverified` behaves like `--allow-below-required`.
- **AC7 — Summary/JSON.** The summary counts each level; the JSON has the stage checks; byte-stable.
- **AC8 — Regression.** The Python/TS `check` paths and the non-proof `fix` behavior are unchanged.

## Dependencies and sequencing

- Depends on `proof-result`, `proof-plan`, `proof-pr`.
- Last.

## Open questions / risks

- The `fix` text becomes longer with four stages; the spec groups by stage and caps tails as T4.
- The `--check` name for tests is historical; the config `command` matches it. Renaming would break
  the shipped CLI; keep it.
- A user can configure a stage that is weaker than their `--require`; the exit/PR gate tells them.
