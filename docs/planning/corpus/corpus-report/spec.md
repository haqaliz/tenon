# Spec: `corpus-report` (T9)

- **Feature:** `corpus`
- **PRD:** `docs/planning/corpus/prd.md` (§ M5)
- **Boundary:** aggregation and rendering. No store/CLI.

## Problem slice

A pile of JSONL is not a benchmark. The report must group by the proof level that actually ran and
by the human outcome, and it must refuse to compute a success rate where no real outcome exists.

## In-scope requirements

- `LevelStats(count, merged, rejected, closed, incident, local_only, pending, known, merge_rate)`.
- `CorpusReport(total, by_level: Mapping[ProofLevel, LevelStats], outcomes: Mapping[Outcome, int])`.
- `benchmark(records: Sequence[CorpusRecord]) -> CorpusReport`.
  - Include every `ProofLevel` with zero stats when absent; every `Outcome` with zero counts.
  - `known = merged + rejected + closed + incident`; `merge_rate = merged / known` when
    `known > 0`, else `None`. `local_only`/`pending` are excluded from `known`.
  - An unknown `proof["level"]` in a record is a `CorpusError` naming the record/id.
- `to_dict()`/`to_json()` byte-stable; a text renderer with a level table and an outcome summary.
  The text shows `n/a` for a null rate.
- Empty records: total 0, every level zero, every outcome zero, all rates None; still valid.

## Out-of-scope

- The record/store/CLI, upload, per-repo tables, charts.
- A confidence interval or a significance claim; the corpus is descriptive.

## Acceptance criteria

- **AC1 — Grouping.** Two levels with mixed outcomes produce the right counts.
- **AC2 — Rate.** `merged=1, rejected=1` -> 0.5; `known=0` -> None; `local_only`/`pending` do not
  change the denominator.
- **AC3 — Shape.** The report includes all five levels and all six outcomes, zero-filled.
- **AC4 — Empty.** Zero records produce a valid report with null rates.
- **AC5 — Text/JSON.** The text has a level table and an outcome line; the JSON has the exact keys;
  both stable for the same records.
- **AC6 — Bad level.** A record whose proof level is not one of the five raises `CorpusError` with
  the id.

## Dependencies and sequencing

- Depends on `corpus-record`; before `corpus-cli`.
- Uses the shipped `ProofLevel` enum; no new proof vocabulary.

## Open questions / risks

- The report is descriptive; with small numbers a rate is noisy. The README says so.
- A merge rate excludes `closed` from the numerator but includes it in `known`; a closed PR is a
  non-success but still a known outcome.
- The text format is a convenience; JSON is the stable machine contract.
