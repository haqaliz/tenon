# Spec: diff-render

**Slug:** `patch-proposer` · **Aspect 3 of 3** · depends on `proposal-result`; uses `rename-rule`.

## Problem slice

Two jobs that both need the file text and must stay inseparable: verify each candidate edit against
the current source, and render the surviving edits as a reviewable unified diff. Then assemble the
final `Proposal`, including everything that was skipped.

## In scope

- `verify(edit, root) -> bool`: read `root / edit.path` as UTF-8, check the **exact** text at
  `(line, column)` for the shape:
  - `keyword` / `attribute`: `line[column-1 : column-1+len(old)] == old`;
  - `dict_key`: the character at `column-1` is `"` or `'`, and
    `line[column : column+len(old)] == old` with the same quote at `column+len(old)`.
  A short line, a missing file, or a decode error is `False` (assembly turns it into `STALE_SITE`).
- Path safety: reject an absolute path or any `..` segment with `ValueError` before reading.
- `apply_edits(text, edits) -> str`: apply in descending `(line, column)` order; a replacement never
  shifts an earlier offset. Raise `ValueError` if two edits overlap on the same span.
- `render(paths_and_texts) -> str`: `difflib.unified_diff` per file, ordered by path, headers
  `a/<path>` / `b/<path>`, `n=3`, newline-stable (`lineterm="\n"`). No output for an unchanged file.
- `propose(change, located, root, proposer=RuleProposer()) -> Proposal`:
  1. `candidates = proposer.propose(change, located, root)`;
  2. partition into verified edits and stale ones;
  3. skipped = every site of every `located.ambiguous` group (with the group's reason) + certain
     sites whose shape is `CALL` (`SHAPE_NOT_EDITABLE`) + stale candidates (`STALE_SITE`), each once,
     canonically ordered;
  4. reason: `NO_RULE` when the kind has no mechanical rule, `NO_CERTAIN_SITES` when there were
     no certain sites at all, `NO_EDITABLE_SITES` when certain sites exist but none has an
     editable shape, `STALE_SITE` when candidates existed but none verified. `None` when edits
     survived. One read per file: verify and apply against the same text, so a mid-run edit cannot
     slip into the diff unverified.
  5. build the diff; return the `Proposal`. Never write.
- Files with no surviving edits produce no diff hunk.

## Out of scope

- The rename rule's matching logic.
- Applying to disk, running `git`, tests, PR text.
- Model proposers.

## Acceptance criteria

1. `apply_edits` on two edits in one line (descending columns) produces the expected text; an
   overlapping pair raises `ValueError`.
2. `verify` accepts a real fixture site; rejects a line where the symbol has moved (`STALE_SITE`),
   a `dict_key` with a mismatched quote, an absolute path and a `..` path.
3. A renamed `amount` on `sdk-basic` produces a diff whose context is the `client.charges.create`
   line and whose only change is `amount` → `amount_cents`; the on-disk file is byte-identical
   before and after (propose is read-only).
4. `git apply` of the diff on a copy of the fixture repo yields the expected file content
   (skip with a clear message if `git` is unavailable; it is available on this machine).
5. A decoy-only change (all sites unrooted) returns `NO_CERTAIN_SITES`, an empty diff, and one
   `Skipped` per ambiguous candidate with its reason.
6. A `**kwargs` site is never edited and appears as `DYNAMIC_KWARGS` in `skipped`.
7. A certain `call` site appears as `SHAPE_NOT_EDITABLE` and produces no edit.
8. A stale candidate (source edited between locate and propose) returns `STALE_SITE` and no diff.
9. Two runs produce byte-identical `to_json()`; `PYTHONHASHSEED` does not change it.
10. `propose` with a fake `Proposer` returning one recorded edit succeeds through the same assembly,
    proving the seam without a model.

## Dependencies & sequencing

Last. Needs aspects 1 and 2. The only aspect that reads the repository.

## Open questions

- `git apply` in tests needs a real work tree. Use a copy under `tmp_path` plus `git init` and
  `git add -A` before `git apply --check`; if that proves fragile, apply the diff with `git apply`
  directly and compare the resulting file (still a real check).
