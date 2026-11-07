# PRD: Benchmark and history (T9)

- **Slug:** `corpus`
- **Capability:** T9 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M2.4 in `docs/ROADMAP.md` (Phase 2)
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1–T8 produce changes, patches, proof levels, PR results and probe reports, but nothing keeps the
history that turns those runs into a benchmark. The risk register (R5) says the differentiator is
the stated proof level **and the benchmark**; today the two real cases live only in
`docs/planning/m0-3-*/evidence.md` and cannot be queried, compared or grown.

T9 adds a labelled `(change, patch, proof, outcome)` corpus: one JSONL record per change, built from
a `tenon fix --json` result, with an outcome the user updates after a human merge/reject/incident. A
report groups by proof level and outcome and computes a merge rate only where real outcomes exist.
The two public M0.3 cases seed a committed `docs/benchmark/corpus.jsonl` and a generated README,
honestly marked `local_only` — no PR, no merge outcome yet.

The dangerous shortcuts are rejected here: counting a local check as a merge, inventing outcomes,
uploading a user's code, and presenting a proof level's count as a success rate when no outcome is
known. The corpus records what ran; the human records what happened; the report says which is which.

**For whom:** the project's own benchmark/reputation (R5), a provider or reviewer asking "how often
did this level hold?", and the next cards (T10 hosted, T11 languages) that need outcome history.

## Goals & Success Metrics

1. **One record per change.** `tenon corpus record --from fix.json --repo URL --commit SHA --outcome
   STATUS --date YYYY-MM-DD --corpus PATH` appends a record with the change, proposal diff, proof,
   PR (if any), outcome and evidence.
2. **Human outcomes.** `tenon corpus outcome` updates a record by id; the six outcomes are
   `pending`, `merged`, `rejected`, `closed`, `incident`, `local_only`. Only real outcomes
   (merged/rejected/closed/incident) feed a merge rate; `local_only`/`pending` never count as success.
3. **A useful report.** `tenon corpus report` groups by level and outcome, shows the merge rate only
   when `known > 0`, and renders text or byte-stable JSON.
4. **A public seed.** `docs/benchmark/corpus.jsonl` holds the two public M0.3 cases as `local_only`;
   `docs/benchmark/README.md` states the method and the honest "no merge outcomes yet".
5. **Local, opt-in, deterministic.** No upload, no network, no clock in the record id or tests; the
   date is user-supplied; identical inputs produce identical ids/JSON.
6. **Honest levels.** The proof dict is the shipped `ProofResult`; the corpus never upgrades it.

## User Personas & Scenarios

- **Maintainer.** After a `tenon fix --json`, records the run; after a human merges the PR, runs
  `corpus outcome <id> merged --outcome-url <pr>`; the report starts showing a merge rate.
- **Provider/reviewer.** Reads `docs/benchmark/README.md` and sees two real cases, both
  `local_only`, and no merge rate — not a fabricated 100%.
- **T9/T10 follow-up.** Uses the JSONL as the labelled history for a hosted benchmark or a provider
  report.
- **T11.** Adds a language and can compare its proof outcomes on the same corpus.

Scenario: the FHI run is recorded as `local_only`/`TESTS_PASSED` with the 3-edit diff and the
focused test command. Later a human opens and merges a PR for it; the outcome becomes `merged` with
the PR URL. The report then counts it in `TESTS_PASSED`'s known outcomes and merge rate.

## Requirements

### Must have

- **M1 — Record.** `CorpusRecord(id, repo, commit, change, proposal, proof, pr, outcome, recorded,
  outcome_url, notes, evidence)`; frozen, slots. Validate non-empty repo/commit, dict
  change/proposal/proof, `pr` dict or None, the outcome enum, `recorded` as `YYYY-MM-DD`, and
  `id == record_id(repo, commit, change, proposal)`.
- **M2 — Deterministic id.** `record_id` = first 12 hex of
  `sha256(canonical {repo, commit, change, proposal["diff"]})`; the outcome is not part of the id, so
  an update keeps it. `to_dict()`/`from_dict()`/`to_json()` are byte-stable.
- **M3 — Store.** `load_corpus(path) -> tuple[CorpusRecord, ...]` (JSONL, one object per line, file
  order preserved); `append_records(path, records)` (create the file, append, keep existing order);
  `update_outcome(path, id, outcome, outcome_url=None, notes=None)` rewrites the file with the same
  order and returns the record. A malformed line, a missing id or a bad record is `CorpusError` with
  a message (CLI exit 2).
- **M4 — CLI record.** `tenon corpus record --from FIX_JSON --repo URL --commit SHA --outcome
  STATUS --date YYYY-MM-DD --corpus PATH [--outcome-url URL] [--notes TEXT] [--evidence TEXT]
  [--json]`. Read a `tenon fix --json` object (`command == "fix"`, `results` list); one record per
  result using its `change`, `proposal`, `proof`, `pr`; print the ids. A bad/missing key is exit 2.
- **M5 — CLI outcome/report.** `tenon corpus outcome --corpus PATH --id ID --outcome STATUS
  [--outcome-url URL] [--notes TEXT] [--json]`; `tenon corpus report --corpus PATH [--json]`. The
  report: total; per level `count, merged, rejected, closed, incident, local_only, pending, known,
  merge_rate`; per outcome counts. `merge_rate` is `merged / known` when `known > 0`, else null.
  `local_only` and `pending` are excluded from `known`.
- **M6 — Seed and docs.** `docs/benchmark/corpus.jsonl` with the two public M0.3 cases
  (`fighthealthinsurance` @ `56e69cf`, `stripe-template` @ `9d9178c`), both `local_only`,
  `TESTS_PASSED`, with the exact change/proposal/proof and the evidence path. `docs/benchmark/README.md`
  states the record/outcome method, the two cases, the absence of merge outcomes and the report
  command.
- **M7 — Exit codes/errors.** 0 on success; 2 on usage, a bad fix JSON, a malformed corpus, an
  unknown id/outcome or a date that is not `YYYY-MM-DD`. `--json` errors are one object; no
  traceback.
- **M8 — Offline/determinism.** No network/upload; tests use fixed dates/ids; the seed report is
  byte-stable; the report with no records is valid (zeros, null rate).

### Should have

- **S1 — `--json`** on record/outcome/report; text is readable.
- **S2 — Evidence path/URL** stored and shown in the report text (not the rate calculation).
- **S3 — Notes** for the human context (e.g. "focused test, no PR").

### Nice to have

- **N1 — `tenon fix --corpus PATH`** auto-record with `pending`; skipped in this card (the explicit
  `corpus record --from` is the contract).
- **N2 — GitHub merge/incident detection**; a later card.
- **N3 — A hosted/public benchmark site**; T10.

## Data Model

```
Outcome = pending | merged | rejected | closed | incident | local_only

CorpusRecord
  id: str                 # 12 hex, deterministic
  repo: str               # URL
  commit: str             # SHA
  change: dict            # Change.to_dict()
  proposal: dict          # Proposal.to_dict() (includes the diff)
  proof: dict             # ProofResult.to_dict()
  pr: dict | None         # PrResult.to_dict()
  outcome: Outcome
  recorded: str           # YYYY-MM-DD, user-supplied
  outcome_url: str | None # PR/issue URL
  notes: str
  evidence: str           # path/URL

CorpusReport
  total: int
  by_level: {level: {count, merged, rejected, closed, incident, local_only,
                     pending, known, merge_rate}}
  outcomes: {outcome: count}
  to_dict() / to_json() / text
```

No timestamps beyond `recorded`; no durations, scores or confidence.

## API Contract

```python
from tenon.corpus import CorpusRecord, benchmark, load_corpus, record_id

records = load_corpus("docs/benchmark/corpus.jsonl")
report = benchmark(records)
report.by_level["TESTS_PASSED"].merge_rate  # None when known == 0
report.to_json()                            # byte-stable
```

CLI:

```sh
tenon corpus record --from fix.json --repo https://github.com/o/r --commit SHA \
  --outcome local_only --date 2026-11-07 --corpus corpus.jsonl
tenon corpus outcome --corpus corpus.jsonl --id <id> --outcome merged \
  --outcome-url https://github.com/o/r/pull/1
tenon corpus report --corpus corpus.jsonl --json
```

No upload, no PR, no proof-level change.

## Technical Considerations

- **Why JSONL.** Append-only lines are git-friendly, easy to inspect and stream, and one bad line is
  a named error. The file order is the history; the id is the key.
- **Why the id excludes the outcome.** The outcome changes over time; the record identity is the
  run (repo + commit + change + diff). An outcome update rewrites the line, not the id.
- **Why the merge rate excludes local/pending.** A local check or an unmerged PR is not a success.
  Showing `2/2` for two `local_only` cases would be the exact dishonesty R5 warns about.
- **Why the date is user-supplied.** Tests must be deterministic, and a historical record's date is
  a fact the user knows. No clock in the record path.
- **Why the public seed is public.** Both repos are public and already in committed evidence. A
  user's corpus is local; nothing is uploaded. The README says so.
- **Why no auto GitHub detection.** It needs network/auth and turns a human outcome into an
  inferred one; a later T10 concern.

## Risks & Open Questions

- **R5 (differentiation).** The benchmark is only as good as the number of recorded outcomes. The
  seed has two local-only cases; the merge rate is null. The report says that plainly.
- **R6 (egress).** The corpus can contain code/diffs. It is local by default; the public seed is
  public data. A user who commits their corpus chooses to share it.
- **Outcome honesty.** A user can record `merged` for anything; the corpus is a claim by the user,
  not a Tenet-verified fact. The record includes the PR URL/evidence so it can be checked.
- **Record drift.** The `change`/`proposal`/`proof` dicts are snapshots from a shipped version; a
  later schema change is a corpus migration, not a silent reinterpretation. The `id` and `to_dict`
  are pinned.
- **A malformed line stops the load.** `CorpusError` names the line; the CLI exits 2. A later
  `--skip-bad` can be added if needed.
- **Open question — should the report include a per-repo/per-change table?** Not in this card; the
  JSONL is the detail, the report is the aggregate.
- **Open question — should `fix --corpus` auto-record?** Not in this card; the explicit
  `corpus record --from` keeps the side effect visible.

## Out of Scope

- Hosted/public benchmark, upload, GitHub outcome detection.
- Automatic corpus recording from `fix` (the `--from` path only).
- New proof levels, PR behavior, probe changes.
- T10/T11.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `corpus-record` | `Outcome`, `CorpusRecord`, `record_id`, validation, JSON, the JSONL store (load/append/update). No report/CLI. |
| `corpus-report` | Aggregation by level/outcome, merge-rate rule, text/JSON. No store/CLI. |
| `corpus-cli` | `tenon corpus record/outcome/report`, fix-JSON input, exit codes, the seed docs/tests. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | R5 names the benchmark; the two cases are stranded in evidence files. |
| User understanding | 🟢 | Maintainer, reviewer, T10/T11; the outcome workflow is concrete. |
| Success metrics | 🟢 | Record id, six outcomes, merge-rate rule, public seed, deterministic tests. |
| Scope clarity | 🟢 | Local JSONL + CLI; hosted/auto-GitHub excluded. |
| Edge cases & risks | 🟡 | The seed has no merge outcomes; the report must say so loudly. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Stdlib JSON/JSONL; no dependency. |
| Go-to-market | 🟢 | The proof-level benchmark is the R5 differentiator; the seed starts it honestly. |

**Areas to strengthen before sharing:** with two `local_only` records the "benchmark" is a method,
not a statistic. The README must not imply otherwise; the first real merged PR is the first datum.

**The question I would want answered before greenlighting this:** *If the only public corpus has two
local checks and no merges, is shipping it better than shipping nothing?* The answer this card
records: yes — it proves the format, records the two honest cases and makes the first merge a
one-line update; a fabricated success rate would be worse than an empty one.
