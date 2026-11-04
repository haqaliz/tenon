# Spec: `pr-render` (T5 PR writer)

- **Feature:** `pr-writer`
- **PRD:** `docs/planning/pr-writer/prd.md` (§ Data Model, M4, M10, M11)
- **Boundary:** pure text. `Proposal` + `ProofResult` + optional `Unanalyzed` in, `PrDraft` out. No
  file reads, no subprocess, no remote, no clock, no randomness.

## Problem slice

The PR is the only artifact a reviewer reads. Its title must state the proof level, its body must say
what ran and what was refused, and its branch and commit must be reproducible. Any clock, random id or
environment-dependent sentence would make two runs of the same proof look like different work.

## In-scope requirements

- Input: `render_pr(proposal: Proposal, proof: ProofResult, *, unanalyzed: Sequence[Unanalyzed] = ())
  -> PrDraft`.
- **Summary.** `f"{kind} {location}"`, plus `: {before} -> {after}` when a before or after value
  exists. `location` is `f"{METHOD} {path}"` when both are present, otherwise the pointer. Scalars
  (`str`, `int`, `float`, `bool`, `None`) render readably; any other value renders as canonical JSON
  (`sort_keys=True`, compact separators).
- **Title.** `[<LEVEL>] tenon: <summary>`.
- **Commit message.** `tenon: <summary>`.
- **Branch.** `tenon/<slug>-<8 hex>`. The slug lower-cases the summary, replaces every run of
  non-alphanumeric characters with `-`, trims leading/trailing `-`, and truncates to 48 characters;
  if empty, use `change`. The hex is the first eight characters of
  `sha256(change_json + "\0" + proposal.diff)`, where `change_json` is `Change.to_json()`.
- **Body.** Fixed section order:
  1. `## Tenon proof: <LEVEL>`.
  2. A fixed sentence for the level. `TESTS_PASSED`: the command returned 0 before and after the
     patch in an isolated copy. `UNVERIFIED`: nothing proved the patch; `Cause: <CAUSE>`.
  3. `### Change` with kind, location, before, after, breaking, confidence.
  4. `### Check` with command, baseline exit, after exit. Missing checks render as `not run`; a
     timeout renders as `timed out`; a failure tail, when present, is a fenced block capped like T4.
  5. `### Files` with `proposal.files`.
  6. `### Skipped sites` with `path:line` , symbol and reason for every `proposal.skipped`; `None.`
     when empty.
  7. `### Not analyzed` with pointer and reason for every supplied entry; omit the section when the
     list is empty.
  8. `### What this proves` with the fixed paragraph for the level.
  9. Footer: `Opened by Tenon. No merge was performed.`
- **Escaping.** Inline code spans replace backticks with `'` and newlines with a space. No raw HTML.
- **Determinism.** The body ends with exactly one `\n`; the draft is byte-identical for the same
  inputs and across hash seeds. The full unified diff is never included.

## Out-of-scope

- Reading the repository, checking the diff, applying anything.
- Deciding whether the proof level is acceptable (`pr-write` owns the gate).
- Localisation, reviewer assignment, labels, issue links.
- Multi-change PRs.

## Acceptance criteria

- **AC1 — Title and commit.** A rename proposal + `TESTS_PASSED` renders
  `[TESTS_PASSED] tenon: renamed POST /v1/checkout/sessions: payment_method_types ->
  allowed_payment_method_types` and commit subject `tenon: renamed POST ...` (same summary, no level).
- **AC2 — Summary values.** String, int, bool, `None`, dict and list before/after values render
  deterministically; a dict/list is compact canonical JSON, not a Python repr.
- **AC3 — Branch.** The branch matches `^tenon/[a-z0-9-]+-[0-9a-f]{8}$`; the same change + diff gives
  the same branch; changing one byte of the diff changes the suffix; a symbol with punctuation/unicode
  produces a valid slug.
- **AC4 — TESTS_PASSED body.** Contains the level, command, baseline exit 0, after exit 0, all files,
  all skipped reasons, the fixed proof sentence and the footer; contains no `--- a/` diff.
- **AC5 — UNVERIFIED body.** Contains `UNVERIFIED`, the exact cause, `Nothing was proven`, and the
  flagged-suggestion sentence; does not contain a sentence claiming the patch passed. Assert on the
  fixed strings, not a naive `"PASSED" not in body` (the level `TESTS_PASSED` is not present, but
  `UNVERIFIED` must not be described as passing).
- **AC6 — Checks.** A missing baseline/after renders `not run`; a timed-out check renders `timed out`;
  a non-empty failure tail appears in a fenced block.
- **AC7 — Skipped and unanalyzed.** Every skipped entry appears with its reason; every supplied
  unanalyzed pointer appears with its reason; an empty list omits the section.
- **AC8 — Escaping and stability.** A backtick or newline in a symbol/path cannot break the inline
  span; the draft is byte-identical across `PYTHONHASHSEED` values.
- **AC9 — No leakage.** The body contains no absolute repo path, no timestamp, no `ProofResult(`
  repr, no enum repr and no full diff.

## Dependencies and sequencing

- Depends on `pr-result` for `PrDraft`.
- Depends on `tenon.propose.Proposal`, `tenon.prove.ProofResult`, `tenon.detect.Unanalyzed`.
- Land before `pr-write`, which calls `render_pr`.

## Open questions / risks

- The summary grammar is optimised for `renamed` (the only rule T3 ships). Other kinds render as
  `kind location: before -> after`; a later card can improve readability without changing the
  contract.
- A symbol containing a markdown fence (` ``` `) is sanitised only inside inline spans; fenced output
  (the failure tail) comes from T4 and is treated as text, capped.
- The 48-character slug is a readability choice; the hash suffix carries uniqueness.
