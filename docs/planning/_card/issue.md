# Card: feat/proof-ladder

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T7 Proof ladder** (`docs/technical/CAPABILITY_ROADMAP.md:13`)
- **Milestone:** M2.2 (`docs/ROADMAP.md`)
- **Branch:** `feat/proof-ladder/aliz`
- **Worktree:** `.claude/worktrees/feat-proof-ladder`

## Brief

T4 records only `TESTS_PASSED` and `UNVERIFIED`, with one check command. `CLAUDE.md`'s proof contract
names four usable levels — `TESTS_PASSED`, `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY` — and the
CLI `--require` ladder promises the user can choose one. R1 (many repos lack tests) is the biggest
adoption blocker: without a weaker, honestly labelled level, those repos get `UNVERIFIED` and no PR.

T7 widens the proof contract and the runner: a `ProofPlan` of stage commands, baseline-first runs,
a `ProofResult` that names the strongest level that actually passed, the new `ProofCause` values,
the CLI `--require` ladder and exit codes, and the PR title/body/draft gate for weak proof.

The hard rule does not change: execution decides. A model may propose a patch; only a command that
ran and exited 0 after a green baseline may label it. Weak proof is labelled weak, never promoted.

## Constraints carried in from the repo

- `CLAUDE.md` §1–2: execution decides; honest levels; `UNVERIFIED` is never presented as verified.
- `CLAUDE.md` §5: no merge, no default branch; T5's guardrails stay.
- `docs/technical/ARCHITECTURE.md`: `--require TESTS_PASSED|CHARACTERIZED|REPLAYED|TYPES_BUILD_ONLY`;
  a required level not reached means a flagged PR, not a verified one.
- `src/tenon/prove/`: T4's baseline-first, isolated copy, capped tails and closed cause set; T7 extends
  the contract without weakening those properties.
- `src/tenon/cli/` and `src/tenon/pr/` consume `ProofLevel`; both must learn the new levels.
- Offline tests: fixture commands only; no network, no model, no real API call.

## Scope fence

Not this card unless the interview chooses it: generating characterization tests, recording real
traffic, T8 MCP/probe, T9 benchmark, new proposer rules.
