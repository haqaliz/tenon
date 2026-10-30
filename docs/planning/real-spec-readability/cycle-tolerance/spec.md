# Spec: cycle-tolerance

**Slug:** `real-spec-readability` · **Aspect 2 of 3** · depends on `unanalyzed-contract`.

## Problem slice

A recursive schema must not refuse the document. Leave a marker where the cycle closes, record it
when the differ reaches it, and keep diffing everything else.

## In scope

- `resolve_refs`: when `ref in chain`, return `{"$ref": ref}` instead of raising. External refs,
  non-pointer refs and unresolved pointers still raise `SpecRefusal`.
- Diff walkers:
  - `_diff_schema_node`: a `$ref` in either side records `CYCLIC_REF` at `pointer` and returns
    without comparing.
  - `_diff_schema`: the `(id(old), id(new))` recursion guard records `CYCLIC_REF` at `pointer` and
    returns instead of raising.
  - `_flatten`: a `$ref` records `CYCLIC_REF` at `pointer` and returns `None`.
- A small committed fixture pair with a self-referential schema (`Node.children -> Node`) plus one
  ordinary changed property, proving the change is still reported.
- Existing cycle-refusal tests in `tests/detect/test_ingest.py` are rewritten: loading no longer
  raises; the marker remains; diffing records the skip.

## Out of scope

- Composition keywords (aspect 3).
- Resolving cycles by object identity.
- Changing `Change` records.

## Acceptance criteria

1. Loading a spec with `Node -> Node` succeeds; the nested node is `{"$ref": "#/components/schemas/Node"}`
   (exact form), and the top-level schema is otherwise fully resolved.
2. Diffing the cycle fixture pair reports the ordinary property change and exactly one
   `CYCLIC_REF` at the back-edge pointer.
3. A spec with two independent cycles records two entries, ordered by pointer.
4. An external `$ref` still raises `EXTERNAL_REF`; an unresolved local pointer still raises
   `UNRESOLVED_REF`.
5. No `Change` is invented from the skipped back-edge (no spurious `property_removed`).
6. The full suite is green; only cycle-refusal tests change.

## Dependencies & sequencing

After aspect 1; before aspect 3 (both touch `_flatten`, but cycles land first).

## Open questions

- Should the marker keep the full `$ref` string or only the target? Keep the original string; it is
  what the document said.
