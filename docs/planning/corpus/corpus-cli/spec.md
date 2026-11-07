# Spec: `corpus-cli` (T9)

- **Feature:** `corpus`
- **PRD:** `docs/planning/corpus/prd.md` (§ M4–M7)
- **Boundary:** `tenon corpus` record/outcome/report, the fix-JSON input, exit codes and the public
  seed. No record/report internals.

## Problem slice

The corpus is only useful if a run can enter it and a human can update the outcome without editing
JSON by hand. This aspect adds the CLI and commits the two honest public cases.

## In-scope requirements

- `tenon corpus` with subcommands:
  - `record --from FIX_JSON --repo URL --commit SHA --outcome STATUS --date YYYY-MM-DD --corpus PATH
    [--outcome-url URL] [--notes TEXT] [--evidence TEXT] [--json]`;
  - `outcome --corpus PATH --id ID --outcome STATUS [--outcome-url URL] [--notes TEXT] [--json]`;
  - `report --corpus PATH [--json]`.
- `record` reads a `tenon fix --json` object: `command == "fix"`, a `results` list; each result must
  have `change`, `proposal` and `proof` mappings; `pr` is mapping or None; one record per result.
  The `locate` is ignored. Print the recorded ids.
- Exit 0 on success; 2 on usage, a bad fix JSON, a missing/malformed corpus, an unknown id/outcome,
  a bad date; `--json` errors are one object; no traceback.
- `docs/benchmark/corpus.jsonl` seeded with the two public M0.3 cases, both `local_only`,
  `TESTS_PASSED`, with the exact change/proposal/proof, repo/commit, evidence path and date.
- `docs/benchmark/README.md`: the record/outcome method, the two cases, the no-merge-outcome note,
  the `tenon corpus report` command, and the local/opt-in note.

## Out-of-scope

- `fix --corpus` auto-record, GitHub outcome detection, a hosted site.
- The record/store/report internals.

## Acceptance criteria

- **AC1 — Record.** A valid fix JSON with two results appends two records with deterministic ids;
  the repo/commit/outcome/date/notes/evidence are carried; `--json` lists the ids.
- **AC2 — Bad input.** A non-fix JSON, a missing `results`, a missing result key, a bad date and an
  unknown outcome each exit 2 with a named message; no partial append.
- **AC3 — Outcome.** Updating an id changes the outcome/url/notes and keeps the id; a missing id
  exits 2; `--json` returns the updated record.
- **AC4 — Report.** The text/JSON report matches `benchmark`; an empty file is valid; a missing file
  exits 2.
- **AC5 — Seed.** `docs/benchmark/corpus.jsonl` loads as exactly two valid records, both
  `local_only`/`TESTS_PASSED`; the report's `known` is 0 and every rate is None.
- **AC6 — Regression.** The check/fix/probe commands and all prior tests stay green.
- **AC7 — Offline.** No network/upload; fixed dates/ids.

## Dependencies and sequencing

- Depends on `corpus-record` and `corpus-report`; last.
- The seed records use `record_id`; the ids are computed, not hand-written.

## Open questions / risks

- The seed's change/proposal/proof are snapshots from the evidence; a later schema change is a
  migration, not a reinterpretation.
- The public README must say "no merge outcomes yet" prominently.
- `record` is explicit; no fix side effect in this card.
