# Card: feat/proof-runner

- **Source:** FALLBACK — no GitHub issue.
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T4 — Proof runner** (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** M1.2 (`docs/ROADMAP.md`, Phase 1)
- **Branch:** `feat/proof-runner/aliz`
- **Worktree:** `.claude/worktrees/feat-proof-runner`

## Brief

Build `src/tenon/prove/` so that a T3 `Proposal` is applied to an isolated copy of the repository,
the user's check runs against the copy before and after the patch, and the result is a proof level:
`TESTS_PASSED` when the baseline was green and the patched tree is green, `UNVERIFIED` with a named
cause otherwise. The user's checkout is never modified and nothing is merged.

Acceptance tests: a rename proposal against a fixture repo reaches `TESTS_PASSED`; a red baseline
reports `TESTS_FAILED_BEFORE` and never applies the patch; a patch that breaks the check reports
`TESTS_FAILED_AFTER`; a non-applying diff reports `PATCH_DID_NOT_APPLY`; a missing command reports
`NO_TESTS_FOUND`; a timeout reports `CHECK_TIMED_OUT`; the repository tree is byte-identical before
and after.

## Constraints carried in from the repo

- `CLAUDE.md` §1: execution decides, never the model. This is the only module allowed to assign
  `TESTS_PASSED`.
- `CLAUDE.md` §2: honest proof levels. `UNVERIFIED` is never presented as verified.
- `CLAUDE.md` §5: never touch the default branch. This card writes only inside a temp copy.
- `ARCHITECTURE.md`: isolated working copy; baseline first; `UNVERIFIED` causes.
- Risk `R1` (many repos lack tests): `NO_TESTS_FOUND` is a first-class result.
- Risk `R2` (a verified PR still breaks production): the level says what ran, no more.

## Scope fence

Not this card: `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY` (T7); branch/PR creation (T5); CLI
(M1.4); running anything against the user's real checkout.
