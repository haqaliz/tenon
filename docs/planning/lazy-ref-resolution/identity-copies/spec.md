# Spec: identity-copies

**Slug:** `lazy-ref-resolution` · **Aspect 2 of 3** · depends on `memoized-resolution`.

## Problem slice

The differ avoids reporting a component schema once per use by hashing every component schema and
comparing canonical JSON. On a DAG that hash expands the document again, and on a large spec it is
the slow path. Identity is both cheaper and more precise: a component copy is the same object.

## In scope

- `_SchemaContext`:
  - `old_ids = {id(schema) for schema in _schemas_of(old).values()}`, same for new.
  - `is_component_copy(old, new)` returns `True` iff `id(old) in old_ids and id(new) in new_ids`.
  - Delete `_component_canons` and its `_canonical` calls from this path.
- Keep `_canonical` where it is still used (ordering keys on `before`/`after`).
- Tests:
  - A path that `$ref`s a component is skipped (the component is reported once, at `components`).
  - A structurally equal inline schema that is **not** a ref is diffed at its own location (the
    stricter identity rule does not suppress a real occurrence).
  - A component that is itself a `$ref` to another component resolves to the same object; both ids
    are in the set; a nested ref is skipped.
  - The Twilio pair's 37 changes are unchanged.

## Out of scope

- Changing `_diff_components` or the root-component diff.
- Semantic composition.
- Performance beyond removing the hashing.

## Acceptance criteria

1. A document with one component used by two paths reports the component's change once, not twice.
2. An inline copy of the same schema (not a ref) is diffed where it appears.
3. `_component_canons` is gone; no `_canonical` call remains in `_SchemaContext`.
4. The full suite is green; the Twilio pair is unchanged.
5. The real Stripe `v2500` -> `v2596` run completes and its counts match the evidence.

## Dependencies & sequencing

After aspect 1. Aspect 3 records the real run.

## Open questions

- If a component schema is a `$ref` to another component, the resolved object is shared; the id set
  contains both names. That is intended: either name is the same schema.
