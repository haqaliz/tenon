# Spec: composition-skip

**Slug:** `real-spec-readability` · **Aspect 3 of 3** · depends on aspects 1-2.

## Problem slice

`oneOf`, `anyOf`, `discriminator` and non-plain `allOf` stop the whole document today. Skip only the
subtree, record why, and never manufacture a change from an unanalyzed pair.

## In scope

- `_flatten(schema, pointer, context, active=None) -> dict | None`:
  - `oneOf`/`anyOf`/`discriminator` → `context.record(pointer, UNSUPPORTED_COMPOSITION)`, return
    `None`.
  - `allOf` that is not a plain object merge (non-list, non-dict members, extra keywords, wrong
    container type) → same.
  - `allOf` cycles (id in `active`) → record `CYCLIC_REF`, return `None`.
  - A plain merge still returns the merged dict, recursively flattening members with the same
    context.
- Callers:
  - `_diff_schema_node`: if either flattened side is `None`, return without comparing.
  - `_diff_parameters`: if either schema is `None`, `continue` (no type record).
  - Any other `_flatten` caller: same guard; no `_type_basis(None)`.
- `_SchemaContext` gains `unanalyzed: list[Unanalyzed]` and `record(pointer, reason)` (dedupe by
  `(pointer, reason)`).
- `diff()` passes `context.unanalyzed` into `DiffResult`.
- Committed composition fixture pair: a schema with `oneOf` and a sibling property that changes.
- Manual real-spec run: fetch Stripe `v2590` and `v2596` (`latest/openapi.spec3.json`), `load` +
  `diff`, record the change count, `unanalyzed` count and elapsed time in
  `docs/planning/real-spec-readability/evidence.md`. The spec files are not committed.

## Out of scope

- Semantic comparison of union branches.
- Making `unanalyzed` block anything downstream.
- Performance tuning.
- The `format` false positive.

## Acceptance criteria

1. The composition fixture pair diffs without refusal; the sibling property change is reported; the
   `oneOf` pointer appears once in `unanalyzed` with `UNSUPPORTED_COMPOSITION`.
2. `anyOf`, `discriminator` and a non-plain `allOf` each record `UNSUPPORTED_COMPOSITION` in their
   own fixture; no `Change` is produced from the skipped subtree.
3. A skipped side paired with an analyzable side produces no `property_removed` or `type_changed`.
4. The Twilio pair still yields 37 changes, 3 breaking schema removals, 0 renames, and
   `unanalyzed == ()`.
5. The real Stripe `v2590` document loads and diffs; `unanalyzed` is non-empty; the run is recorded
   with counts and time. No network in the test suite.
6. `to_json()` is byte-stable across hash seeds with skips present.
7. Full suite green (565 baseline, updated where the refusal contract changed).

## Dependencies & sequencing

Last. Needs aspects 1-2; the only aspect that touches the walker broadly.

## Open questions

- Should a schema with both `oneOf` and `properties` skip the whole schema or diff the properties?
  Current answer: skip the whole subtree. Splitting would require a partial-schema model; not worth
  it until a real case needs it.
