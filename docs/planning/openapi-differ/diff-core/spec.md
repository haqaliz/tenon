# Spec: diff-core

**Slug:** `openapi-differ` · **Aspect 3 of 4** · depends on `change-record`, `spec-ingest`.

## Problem slice

The walk: compare two resolved documents and emit every change kind except `renamed`, with a
correct `breaking` flag and a pointer to the enclosing container.

## In scope

- `diff(old: dict, new: dict) -> DiffResult`, canonically ordered.
- **Paths/operations:** for each path in `old.paths` missing from `new.paths` →
  `endpoint_removed` (pointer `#/paths`, `path` set, `breaking=True`). For each method removed from
  a surviving path → same kind, pointer `#/paths/~1<path>`. New path or method → `endpoint_added`
  (`breaking=False`).
- **Parameters:** merge path-level and operation-level parameters by `(name, in)`, operation level
  winning. Then:
  - present in old, absent in new → `parameter_removed`, `breaking=True`
  - required in new and (absent in old or optional in old) → `parameter_required_added`,
    `breaking=True`
  - `schema.type`/`format` differs → `parameter_type_changed`, `breaking=True`
  - pointer `…/parameters`
- **Request/response schemas:** recurse object properties and array items.
  - property missing in new → `property_removed`, `breaking=True`
  - new property that is in `required` → `property_required_added`, `breaking=True`
  - new optional property → `property_added`, `breaking=False`
  - `type`/`format` differs → `property_type_changed`, `breaking=True`
  - enum in new is a strict subset of old → `enum_narrowed`, `breaking=True`
- **Components:** a schema in `#/components/schemas` present only in old → `schema_removed`;
  only in new → `schema_added`.
- **Composition policy (PRD M5):** traverse `allOf` when every member is a plain object/schema map
  with no `discriminator`; otherwise `UNSUPPORTED_COMPOSITION` at that pointer. `oneOf`/`anyOf`/
  `discriminator` always refuse.
- **Version normalisation (PRD S1):** `type: ["string","null"]` ≡ `type: string, nullable: true`;
  boolean vs numeric `exclusiveMinimum` compared on the normalised value.

## Out of scope

- Rename detection (aspect 4).
- Emitting a change for an added *optional* parameter — the PRD's kind list has no
  `parameter_added`. Recorded as a known gap, not silently widened here.
- MCP/SDK sources. Patch generation.

## Acceptance criteria

1. Each of the 12 non-rename kinds has at least one fixture pair that produces it, and a
   corresponding negative fixture that does not.
2. `breaking` is `True` for every removal/required-add/type-change/enum-narrow, `False` for every
   add.
3. A path-level parameter removed from the path is still reported when the operation inherits it.
4. A `$ref`'d schema changed once in `components` produces exactly one change at the schema, not one
   per referencing operation.
5. `oneOf` in a parameter schema refuses with `UNSUPPORTED_COMPOSITION` and the exact pointer.
6. A nullability-only change (3.0 `nullable` vs 3.1 `type: [x, "null"]`) produces **zero** changes.
7. Reordering keys in either input changes nothing in the output.

## Dependencies & sequencing

After `spec-ingest`. Before `rename-inference`, which consumes its `removed`+`added` records.

## Open questions

- Response-schema changes: are they `breaking`? Default: yes when a response property is removed
  or its type changes (consumers read it), `False` when added (additive for readers). Confirm with
  the first real vendor case.
- `endpoint_added` for a whole new path: one record per path, or one per method? Default: one per
  method — the locator cares about operations, not paths.
