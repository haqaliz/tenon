# Spec: `proof-result` (T7)

- **Feature:** `proof-ladder`
- **PRD:** `docs/planning/proof-ladder/prd.md` (§ M1, M2, M6, M7)
- **Boundary:** the extended result contract. No subprocess, no copy, no CLI, no PR.

## Problem slice

The runner can only report two levels and one check. The ladder needs five levels, an explicit rank,
a stage on every check, and a result that records every stage that ran — without breaking the
shipped `ProofResult` constructors the rest of the engine uses.

## In-scope requirements

- `ProofStage`: `BUILD`, `CHARACTERIZE`, `REPLAY`, `TESTS` (runner order).
- `ProofLevel`: `TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY`, `UNVERIFIED`
  (docs order).
- `PROOF_RANK`: `{TESTS_PASSED: 4, CHARACTERIZED: 3, REPLAYED: 2, TYPES_BUILD_ONLY: 1,
  UNVERIFIED: 0}`; `proof_rank(level) -> int` (coerces strings).
- `ProofCause` adds `BUILD_FAILED_BEFORE`, `BUILD_FAILED_AFTER`, `CHARACTERIZE_FAILED_BEFORE`,
  `CHARACTERIZE_FAILED_AFTER`, `REPLAY_FAILED_BEFORE`, `REPLAY_FAILED_AFTER`, `NO_PROOF_COMMAND`;
  the existing seven stay.
- `CheckResult.stage: ProofStage = ProofStage.TESTS`; coerced; `to_dict()` adds `"stage"`; all
  existing constructors keep working.
- `ProofResult.checks: tuple[CheckResult, ...] = ()`; coerced.
- `ProofResult.to_dict()` adds `"checks": [check.to_dict(), ...]`; all existing keys stay.
- Invariants:
  - When `checks` is non-empty, a green level (`TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`,
    `TYPES_BUILD_ONLY`) needs a matching `after` check (`stage` TESTS/CHARACTERIZE/REPLAY/BUILD),
    `returncode == 0`, `timed_out is False`, `patch_applied is True`, `cause is None`.
  - When `checks` is empty, `TESTS_PASSED` keeps the T4 invariant; the three new green levels raise
    `ValueError` (they need evidence); `UNVERIFIED` needs a cause.
  - `UNVERIFIED` always carries a cause and never `patch_applied`? No: an after failure has
    `patch_applied=True`; the T4 rule allows it. Keep that.
- `__all__` exports the new names; the existing names stay.

## Out-of-scope

- The runner (`proof-plan`), CLI, PR.
- Per-stage timeouts, durations, scores.
- Changing the old cause names.

## Acceptance criteria

- **AC1 — Enums.** The five levels and four stages have the exact values/order; every value
  constructs from its string.
- **AC2 — Rank.** `proof_rank` orders the five; a string coerces; an unknown value raises.
- **AC3 — Stage.** `CheckResult` without `stage` is `TESTS`; a string coerces; `to_dict()` includes it.
- **AC4 — Checks.** `ProofResult` without `checks` is `()`; a sequence coerces to a tuple;
  `to_dict()` includes `checks`.
- **AC5 — Invariants.** Each green level with a matching green after check and `patch_applied=True`
  constructs; a missing/mismatched/red after raises; the new levels without `checks` raise; a green
  level with a cause raises.
- **AC6 — Backward compatibility.** The old `ProofResult(level="UNVERIFIED", cause=..., baseline=...,
  after=..., patch_applied=...)` constructs; the old `TESTS_PASSED` shape constructs.
- **AC7 — JSON.** `to_dict()` keys are the old keys plus `checks`; each check has the old keys plus
  `stage`; only JSON primitives; byte-stable across hash seeds.
- **AC8 — Causes.** The fourteen causes are the closed set; every value round-trips.

## Dependencies and sequencing

- First aspect; `proof-plan`, `proof-cli` and `proof-pr` depend on it.
- Update the T4 tests that pin the two-value level list, the seven causes, and the dict key sets.

## Open questions / risks

- The `checks` invariant is stricter than the old constructors; the new levels require evidence by
  design. The plan runner always populates `checks`.
- The enum order is presentational; `PROOF_RANK` is the only comparison.
