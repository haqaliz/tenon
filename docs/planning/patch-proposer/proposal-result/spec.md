# Spec: proposal-result

**Slug:** `patch-proposer` · **Aspect 1 of 3** · builds first, everything depends on it.

## Problem slice

T4 and T5 need one honest answer type before any rule or diff exists: what an edit is, what was
skipped and why, when a proposal carries a reason, and how it serializes. No I/O, no `difflib`.

## In scope

- `Edit`: `path`, `line`, `column`, `shape: SiteShape`, `old`, `new`. Frozen, slots.
- `SkipReason`: `AmbiguityReason` values plus `SHAPE_NOT_EDITABLE` and `STALE_SITE`, as one closed
  `StrEnum`. Every ambiguity reason maps to the same value, so a `Skipped` entry never needs two
  enums.
- `Skipped`: `site: Site`, `reason: SkipReason`.
- `ProposalReason`: `NO_RULE`, `NO_CERTAIN_SITES`, `NO_EDITABLE_SITES`, `STALE_SITE`.
- `Proposal`: `change`, `edits`, `skipped`, `files`, `diff`, `reason`.
  - `files` is **derived**, not passed: the sorted unique edit paths.
  - `reason` is set iff `edits` is empty; an empty proposal with a non-empty skipped list is valid.
  - `diff == ""` iff `edits` is empty.
- Canonical order: `edits` by `(path, line, column, shape, old)`; `skipped` by
  `(site.path, site.line, site.column, reason)`.
- `to_dict()` / `to_json()`: JSON-safe, `sort_keys`, byte-stable, matching `LocateResult.to_json`.
- `Proposer` protocol (duck-typed, no `typing.Protocol` runtime dependency): a callable
  `propose(change, located, root) -> tuple[Edit, ...]`, documented in the module docstring.

## Out of scope

- Reading files, verifying spans, applying edits, `difflib`.
- The rename rule.
- Skip classification (aspect 3 decides what is stale or uneditable).

## Acceptance criteria

1. An `Edit` and a `Skipped` entry construct for every `SiteShape` and every `SkipReason`.
2. `files` equals `sorted({edit.path})`; passing a mismatched `files` is impossible (it is derived).
3. `edits`/`skipped` are canonically ordered from any insertion order.
4. `to_json()` is byte-identical across `PYTHONHASHSEED` values and parses as JSON with primitives
   only; no dataclass reprs, no enums as objects.
5. A `Proposal` with `edits=()` and `reason=None` raises `ValueError`; one with `edits` and a reason
   raises too.
6. A `Proposal` with `edits=()` and `diff="x"` raises `ValueError`; an edit-bearing proposal with
   `diff=""` raises as well.
7. Every `AmbiguityReason` value is constructible as a `SkipReason` with the same string value.

## Dependencies & sequencing

None. First. Aspects 2 and 3 import from it.

## Open questions

- Should `Skipped` carry the group's reason and its candidate count instead of one entry per site?
  One entry per site is more useful downstream and sorts cleanly; keep it.
