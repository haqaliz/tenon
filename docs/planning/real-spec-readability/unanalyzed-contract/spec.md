# Spec: unanalyzed-contract

**Slug:** `real-spec-readability` · **Aspect 1 of 3** · builds first.

## Problem slice

The skipped-subtree record is the price of readability. Define it, attach it to `DiffResult`, and
make it byte-stable before any walker changes. No ingest, no diff logic.

## In scope

- `UnanalyzedReason`: `CYCLIC_REF`, `UNSUPPORTED_COMPOSITION`, `UNRESOLVED_REF` as `StrEnum`.
- `Unanalyzed`: frozen, slots, `pointer: str`, `reason: UnanalyzedReason`; `to_dict()/from_dict()`;
  pointer validated with the existing `_POINTER` regex.
- `DiffResult(changes, unanalyzed=())`:
  - `unanalyzed` coerced to a tuple, deduplicated by `(pointer, reason.value)`, sorted by
    `(pointer, reason.value)`.
  - `to_dict()` returns `{"changes": [...], "unanalyzed": [...]}`; `to_json()` unchanged in style
    (`sort_keys`, `ensure_ascii=False`, compact separators).
  - One-argument construction stays valid; `unanalyzed` defaults to `()`.
- Exports from `tenon.detect`: `Unanalyzed`, `UnanalyzedReason`.

## Out of scope

- Recording anything (aspects 2-3).
- Changing `Change` or `SpecRefusal`.
- Downstream consumers.

## Acceptance criteria

1. Every reason constructs and round-trips through `to_dict()`/`from_dict()`.
2. An invalid pointer raises `ValueError` (reuse the `_POINTER` regex).
3. `DiffResult(changes)` has `unanalyzed == ()` and its JSON has an empty list.
4. Duplicate `(pointer, reason)` entries collapse to one; different reasons at the same pointer
   survive; order is canonical from any insertion order.
5. `to_json()` is byte-identical across `PYTHONHASHSEED` values and contains only JSON primitives.
6. The existing `changes` ordering and JSON are unchanged.

## Dependencies & sequencing

None. First. Aspects 2-3 record into this type.

## Open questions

- Should `Unanalyzed` carry a message (e.g., the composition keyword)? The reason enum already says
  which; a pointer locates it. Keep it small.
