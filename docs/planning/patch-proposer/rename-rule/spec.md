# Spec: rename-rule

**Slug:** `patch-proposer` · **Aspect 2 of 3** · pure: no filesystem, no diff.

## Problem slice

The one mechanical fix this card trusts: a renamed field becomes a renamed identifier at the sites
T2 called certain. Producing candidate edits — not verified ones — keeps the rule testable without
looking at files; verification belongs to assembly.

## In scope

- `RuleProposer.propose(change, located, root) -> tuple[Edit, ...]`. `root` is accepted for protocol
  symmetry and is not read.
- Gate, first match wins:
  - `change.kind is not ChangeKind.RENAMED` → `()`.
  - Endpoint rename: `change.location.method` and `.path` set **and** `before`/`after` are strings
    starting with `/` → `()` (T1's endpoint-rename shape; a request-body property rename also has
    a method and path, so the path-shape check is required).
  - `before`/`after` not non-empty strings, or equal → `()`.
- For each `located.certain` site, with `old = change.before`, `new = change.after`:
  - `shape is SiteShape.CALL` → no edit (a method rename is a different rule).
  - `shape in (KEYWORD, DICT_KEY, ATTRIBUTE)` and `site.symbol == old` → one candidate `Edit` with
    the site's path/line/column/shape.
  - any other symbol → no edit (defensive; the locator should not produce it).
- Deduplicate candidate edits by `(path, line, column, shape, old)`; preserve locator order, which
  is already canonical.
- Never read `located.ambiguous`; assembly turns those into skipped suggestions.
- No `new` validation beyond non-empty and different: a rename to a nonsense name is still a
  candidate; T4 decides.

## Out of scope

- Reading source or verifying that the old name is still there (`STALE_SITE` is assembly).
- Applying edits or rendering a diff.
- Endpoint/method renames, removals, additions, type changes.
- Any model; the protocol is in aspect 1.

## Acceptance criteria

1. `renamed` property `amount → amount_cents` with two certain keyword sites yields two edits, in
   locator order, with the right line/column.
2. A certain `call` site yields no edit; the same input still yields edits for the keyword sites.
3. An endpoint rename (`before="/v1/charges"`, `after="/v2/charges"`, method/path set) yields no
   edits even when certain call sites exist.
4. A request-body property rename (method/path set, `before="amount"`, `after="amount_cents"`)
   **does** yield edits: the path-shape check, not scope alone.
5. `property_removed`, `parameter_required_added`, `property_type_changed`, `enum_narrowed` and
   `endpoint_removed` all yield `()`.
6. A `renamed` record with `before=None` or `before == after` yields `()`, no exception.
7. Duplicate certain sites (same path/line/column) yield one edit.
8. The rule is pure: a call with a `tmp_path` root that does not exist returns edits without
   touching the filesystem, and a monkeypatched `Path.read_text` is never called.

## Dependencies & sequencing

After `proposal-result`; parallel with `diff-render`. Assembly (aspect 3) calls it.

## Open questions

- A field rename where the locator found *no* certain sites but several ambiguous ones: the rule
  returns `()`, and assembly reports `NO_CERTAIN_SITES` with the skipped list. Correct, and T4 will
  turn it into a flagged suggestion.
