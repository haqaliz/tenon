# Spec: memoized-resolution

**Slug:** `lazy-ref-resolution` · **Aspect 1 of 3** · builds first.

## Problem slice

Make `resolve_refs` linear in distinct nodes instead of exponential in ref occurrences. One raw
node, one resolved object; refs share it; back-edges stay markers.

## In scope

- `resolve_refs(document)`:
  - `cache: dict[int, object]` keyed by `id(raw_node)`; every dict and list resolves once.
  - `active: set[int]` of raw target ids on the current path; a ref to an active target returns
    `{"$ref": ref}` exactly.
  - A `$ref` to a cached target returns the cached object (identity, not equality).
  - External/non-pointer/unresolved refs still raise the existing `SpecRefusal` codes.
- `parse`/`load` docstrings: the returned document may share subtrees; do not `json.dumps` it.
- Synthetic fixture `tests/fixtures/specs/dag-old.yaml` / `dag-new.yaml`:
  ```
  components:
    schemas:
      L0:
        type: object
        properties:
          a: {$ref: '#/components/schemas/L1'}
          b: {$ref: '#/components/schemas/L1'}
      ...
      L30: {type: object, properties: {value: {type: string}}}
  ```
  `dag-new` changes `L30.value` to integer.
- Test helper `distinct_nodes(document) -> int` walking dicts/lists by `id` (in the test file; not
  production code).

## Out of scope

- Component-copy detection (aspect 2).
- Any differ change.
- Lazy resolution inside the differ.

## Acceptance criteria

1. Loading `dag-old` produces fewer than 100 distinct dict/list objects (2^30 under eager
   resolution); the test completes in well under a second.
2. `doc["components"]["schemas"]["L0"]["properties"]["a"] is doc[...]["b"]` — same object.
3. Diffing `dag-old`/`dag-new` reports the `L30.value` type change exactly once and completes.
4. A two-cycle fixture still leaves markers at the back-edges (existing tests).
5. External and unresolved refs still refuse with the same codes.
6. The Twilio pair loads and diffs with the same 37 changes; its resolved document is a DAG but
   every value is equal to before.

## Dependencies & sequencing

None. First. Aspect 2 needs the identity property.

## Open questions

- Should the cache key be the raw node id or a pointer string? Id is what identity copies need; two
  pointers to one node collapse. Keep id.
- `resolve_refs` is not required to be idempotent on its own output; it expects a raw document.
