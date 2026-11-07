# Spec: `corpus-record` (T9)

- **Feature:** `corpus`
- **PRD:** `docs/planning/corpus/prd.md` (§ M1–M3)
- **Boundary:** the record type, deterministic id, JSON and the JSONL store. No report/CLI.

## Problem slice

The benchmark needs one stable identity and one honest line per run before any aggregation. This
aspect defines the record, validates it, and gives the file an append/update interface that keeps the
history intact.

## In-scope requirements

- `Outcome`: `PENDING`, `MERGED`, `REJECTED`, `CLOSED`, `INCIDENT`, `LOCAL_ONLY` (this order).
- `CorpusRecord(id, repo, commit, change, proposal, proof, pr, outcome, recorded, outcome_url,
  notes, evidence)`; frozen, slots.
  - `repo`/`commit` non-empty strings; `change`/`proposal`/`proof` mappings; `pr` mapping or None;
    `outcome` coerces to `Outcome`; `recorded` is a `YYYY-MM-DD` string (a real date); the string
    fields are strings.
  - `id` must equal `record_id(repo, commit, change, proposal)`; a mismatch raises `ValueError`.
  - `to_dict()`/`from_dict()`/`to_json()` byte-stable (canonical JSON).
- `record_id(repo, commit, change, proposal)`: canonical
  `{"repo":..., "commit":..., "change":..., "proposal": proposal["diff"]}`, sha256, first 12 hex.
- `CorpusError` for a malformed line, a missing file, an unknown id or a bad record.
- `load_corpus(path) -> tuple[CorpusRecord, ...]`: JSONL, blank lines ignored, file order preserved;
  a missing file is a `CorpusError` (append creates it).
- `append_records(path, records)`: create the parent dir/file, append one canonical JSON line per
  record, keep existing lines.
- `update_outcome(path, id, outcome, outcome_url=None, notes=None) -> CorpusRecord`: replace the
  matching record in place, keep the id/order, write atomically (temp + replace); a missing id is a
  `CorpusError`.

## Out-of-scope

- The report, CLI, seed docs.
- Upload, network, GitHub outcome detection.

## Acceptance criteria

- **AC1 — Enum.** The six outcomes in order; every value constructs from its string; an unknown
  value raises.
- **AC2 — Record.** A valid record round-trips; empty repo/commit, non-dict change/proposal/proof,
  a bad date, a non-Outcome and an id mismatch raise `ValueError`.
- **AC3 — Id.** The same repo/commit/change/diff gives the same 12-hex id; changing the diff,
  commit or change changes it; the outcome is not in the id.
- **AC4 — Load.** A two-line file returns two records in order; blank lines ignored; a missing file
  and a malformed line are `CorpusError`s naming the path/line.
- **AC5 — Append.** Appending to a new/existing file keeps the previous records and adds one line per
  record; the bytes are canonical.
- **AC6 — Update.** Updating an id changes only its outcome/url/notes, keeps the order and the id;
  a missing id is a `CorpusError`; the file is not left half-written.
- **AC7 — Determinism.** The same record inputs serialise identically across hash seeds.

## Dependencies and sequencing

- First; `corpus-report` and `corpus-cli` depend on it.
- The record stores the shipped `Change`/`Proposal`/`ProofResult` dictionaries; it does not validate
  their internal shape beyond being mappings.

## Open questions / risks

- A `repo` or `commit` typo is a user error; the id is deterministic but not a proof of provenance.
- The date is user-supplied; no clock.
- `load_corpus` on a missing file is an error, not an empty corpus; `append` creates.
