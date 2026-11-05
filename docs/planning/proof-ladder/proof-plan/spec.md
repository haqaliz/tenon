# Spec: `proof-plan` (T7)

- **Feature:** `proof-ladder`
- **PRD:** `docs/planning/proof-ladder/prd.md` (§ M3–M5)
- **Boundary:** `ProofPlan` and the multi-stage runner. No CLI, no PR, no config file.

## Problem slice

One check command cannot express a ladder. The runner must run every configured stage against a
green baseline, apply the patch once, run every after-check, and report the strongest stage that
actually passed — failing closed when any configured stage fails.

## In-scope requirements

- `ProofPlan(tests=(), characterize=(), replay=(), build=())`: frozen, slots; each a tuple of
  strings; a bare string is a `ValueError`; `is_empty()`.
- `prove_plan(proposal, root, plan, timeout=300.0) -> ProofResult`:
  1. Validate the plan, non-empty, positive timeout; a string command raises.
  2. `proposal.edits` empty: `STALE_SITE` → `PATCH_DID_NOT_APPLY`, else `NO_PATCH_PROPOSED`.
  3. Empty plan → `NO_PROOF_COMMAND` before copying.
  4. Copy once. For each configured stage in `BUILD`, `CHARACTERIZE`, `REPLAY`, `TESTS` order, run
     the baseline (`CheckResult(stage=..., kind="baseline")`). A red baseline or timeout stops before
     applying: the stage's `*_FAILED_BEFORE` or `CHECK_TIMED_OUT`; `checks` holds that baseline.
  5. Apply `proposal.diff` once (`PATCH_DID_NOT_APPLY` on failure); the baselines are in `checks`.
  6. Run each configured stage's after-check in the same order. A red after or timeout → the stage's
     `*_FAILED_AFTER` or `CHECK_TIMED_OUT`; `checks` holds all baselines and the afters up to the
     failure.
  7. All green → level is the strongest configured stage (`TESTS > CHARACTERIZE > REPLAY > BUILD`);
     `checks` holds every baseline/after.
  8. `baseline`/`after` primary: the failing check when there is one; otherwise the tests check if
     configured, else the strongest configured stage's. `patch_applied` only after a successful apply.
  9. Delete the copy on every path; no writes to the source.
- `prove(proposal, root, command, timeout)` stays: empty command → `NO_TESTS_FOUND` before copying;
  otherwise `prove_plan(plan=ProofPlan(tests=tuple(command)))`. Existing results/causes unchanged.

## Out-of-scope

- CLI flags/config, PR text/gate.
- Generated tests, traffic recording, per-stage timeouts, retries, dependency installation.
- New proposer rules.

## Acceptance criteria

- **AC1 — Build only.** A green build before/after with no tests → `TYPES_BUILD_ONLY`; the check
  stage is `BUILD`; `patch_applied` true.
- **AC2 — Characterize/replay.** Green characterize only → `CHARACTERIZED`; green replay only →
  `REPLAYED`; the matching check stage is present.
- **AC3 — All green.** Build+characterize+replay+tests green → `TESTS_PASSED`; `checks` has eight
  records in stage order; the primary is the tests check.
- **AC4 — Fail closed.** Green build + red tests after → `UNVERIFIED / TESTS_FAILED_AFTER`, not
  `TYPES_BUILD_ONLY`; the build pass stays in `checks`.
- **AC5 — Baselines first.** A red build baseline → `BUILD_FAILED_BEFORE`, no apply, no after check;
  `patch_applied` false. A red replay baseline → `REPLAY_FAILED_BEFORE`.
- **AC6 — Apply once.** A successful run applies the diff once; a garbage diff →
  `PATCH_DID_NOT_APPLY` and no after checks.
- **AC7 — Timeout.** A stage timeout → `CHECK_TIMED_OUT` with the stage on the check record.
- **AC8 — Empty.** An empty plan → `NO_PROOF_COMMAND`; the `prove` shortcut with an empty command →
  `NO_TESTS_FOUND`.
- **AC9 — Isolation.** The source tree is unchanged; the temp copy is removed on success and failure.
- **AC10 — Determinism.** Same inputs → byte-identical `to_dict()`; check order is stage order.

## Dependencies and sequencing

- Depends on `proof-result`; before `proof-cli` and `proof-pr`.
- Reuse `tenon.prove.copy` (`isolated_copy`, `apply_diff`), `run_check`, and `tail`.

## Open questions / risks

- The stage order is fixed; a user who wants tests first cannot reorder. The level is independent of
  order; only the failure cause of the first red baseline depends on it.
- A slow stage shares the same timeout; a later card can split it.
- The primary `baseline`/`after` selection is a compatibility convenience; `checks` is the complete
  record.
