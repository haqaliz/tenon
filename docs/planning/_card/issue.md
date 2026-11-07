# Card: feat/corpus

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T9 Benchmark and history** (`docs/technical/CAPABILITY_ROADMAP.md:15`)
- **Milestone:** M2.4 (`docs/ROADMAP.md`)
- **Branch:** `feat/corpus/aliz`
- **Worktree:** `.claude/worktrees/feat-corpus`

## Brief

T1–T8 produce changes, patches, proof levels and probe reports, but nothing keeps the history that
turns those runs into a benchmark. The risk register (R5) says the differentiator is the stated proof
level *and the benchmark*; today there are two real cases in `docs/planning/m0-3-*/evidence.md` and no
queryable record of them.

T9 adds a `(change, patch, proof, outcome)` corpus: a JSONL record per change, built from a
`tenon fix --json` result, with an outcome the user updates after a human merge/reject/incident. A
report groups records by proof level and outcome and computes a merge rate only where real outcomes
exist. The two public M0.3 cases seed a committed `docs/benchmark/corpus.jsonl` + a generated
`README.md`, honestly marked `local_only` (no PR, no merge outcome yet).

The hard rules do not change: the corpus records what actually ran; `local_only`/`pending` never
count as a successful merge; nothing is uploaded; the public seed uses only public repositories; the
record id is deterministic and the date is user-supplied (no clock in tests).

## Constraints carried in from the repo

- `CLAUDE.md` §2: honest levels; the corpus records the `ProofResult` level/cause, never upgrades it.
- `CLAUDE.md` §4: no code egress; the corpus is local and opt-in. The public seed is public data.
- `CLAUDE.md` §5: no merge; an outcome is a human fact recorded later.
- `docs/ROADMAP.md` R5: differentiate on the proof level and the benchmark.
- The `tenon fix --json` shape is the input: `{"command":"fix","results":[{"change","locate",
  "proposal","proof","pr"}],"summary":...}`.
- Offline, deterministic tests; no network, no GitHub outcome detection.

## Scope fence

Not this card: a hosted/public benchmark site, automatic GitHub merge/incident detection, a corpus
upload, T10/T11, new proof levels.
