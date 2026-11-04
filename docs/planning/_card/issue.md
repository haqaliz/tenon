# Card: feat/pr-writer

- **Source:** FALLBACK — no GitHub issue (`gh issue view pr-writer` is not an issue id; `gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T5 PR writer** (`docs/technical/CAPABILITY_ROADMAP.md:11`)
- **Milestone:** M1.3 (`docs/ROADMAP.md:27`)
- **Branch:** `feat/pr-writer/aliz`
- **Worktree:** `.claude/worktrees/feat-pr-writer`

## Brief

T1–T4 are shipped and the Phase 0 gate is met on two real repos, but the pipeline still ends in a
temporary copy that T4 deletes. Build T5: take the exact `Proposal.diff` T4 proved plus the
`ProofResult`, and produce a branch and PR whose title and body state only the level that actually
ran.

The writer must never push to the default branch and must never merge. PR creation goes through an
injectable remote adapter so `tests/` stays offline and deterministic; the real GitHub path is the
only network-touching code, behind an explicit opt-in.

## Constraints carried in from the repo

- `CLAUDE.md` §2: honest levels. `TESTS_PASSED` and `UNVERIFIED` are the only levels T4 emits; the
  PR says exactly that and quotes the command (`docs/planning/proof-runner/prd.md:157`).
- `CLAUDE.md` §5: never touch the default branch; never merge. A refusal must be a named result,
  tested.
- `docs/technical/ARCHITECTURE.md`: the diff is the artifact T5 ships; the change record and skipped
  sites travel with it.
- `docs/planning/proof-runner/prd.md:169`: branch names, commit messages and PR text are T5.
- Determinism: PR title and body are byte-stable for the same inputs; no clock, no random id.
- Offline: no network in `tests/`; no real model call and no live GitHub call.

## Scope fence

Not this card: the CLI (`tenon fix`, M1.4), new proposer rules, the T7 proof ladder, T6 TS/JS,
merging, pushing to the default branch, or hosted GitHub App auth.
