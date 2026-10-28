# Spec: symbol-contract

**Slug:** `python-call-site-locator` · **Aspect 2 of 4** · depends on `locate-result`; pure, no filesystem.

## Problem slice

A T1 `Change` speaks HTTP; the scanner speaks Python names. This aspect is the single translation
point: `Change` + `LocateConfig` → `Query`. Getting this wrong makes every downstream certainty
meaningless, so it is pure, table-tested, and refuses what it cannot name.

## In scope

- `Query`: `scope` (`operation|component`), `kind` (the source `ChangeKind`), `method`, `path`,
  `operation_candidates` (`tuple[str, ...]` dotted method paths), `field_name` (the Python name to
  look for, mapped or inferred), `change_field` (the spec-side name, for reporting), `field_presence`
  (`must_exist|must_be_added|absent`), `origin` (`mapping|inferred|none`),
  `reason: LocateReason | None`.
- Scope: `operation` when `change.location.method` and `.path` are both set, `component` when both
  are `None` (T1's `_record_location` behaviour).
- Name extraction per kind, handling the three `before`/`after` shapes T1 actually emits
  (`src/tenon/detect/record.py`, `src/tenon/detect/diff.py`):
  - `property_*` / `parameter_*`: `before["name"]` when the item was removed or changed;
    `after["name"]` when it was added. A payload with no usable `name` is `UNSUPPORTED_CHANGE_KIND`.
  - `renamed`: `before` and `after` are the old and new names as strings; search the **old** name.
  - `endpoint_removed` / `endpoint_added`: no field name; the query is the operation only.
  - `enum_narrowed`, `schema_added`, `schema_removed`: `UNSUPPORTED_CHANGE_KIND`.
- Explicit mapping wins: `"DELETE /v1/charges/{id}"` → operation candidate; `"Charge.amount"` →
  field name, with the schema name parsed out of the JSON pointer
  (`#/components/schemas/Charge/properties` → `Charge`). A mapped field on a component change
  applies; a mapped field on an operation change applies to that operation.
- Inference, only when unmapped:
  - Operation candidates from path segments: drop a leading `v<N>` segment and `{param}` segments,
    join the remaining segments with `.`, append a verb-derived leaf. Verbs:
    `get → get|list|retrieve`, `post → create`, `put|patch → update`, `delete → delete`.
  - Field name: the spec `name` as-is (snake_case is the Python convention and the spec name
    usually is). No guessing at prefixed/suffixed variants.
- `parameter_required_added` (settled): the parameter is new, so the query is the **enclosing
  operation** plus `field_name` for reporting; its sites are calls to that operation. Same for
  `property_required_added` when the property was genuinely added (`before is None`); when
  `before is not None` the item existed and only became required, so the query is its name.
- `field_presence` per kind: `must_exist` for removed / renamed / type-changed; `must_be_added` for
  added / required-added; `absent` for endpoint-only queries.
- Deterministic: candidate tuples are ordered, never set-derived.

## Out of scope

- Reading the OpenAPI document again. `operationId` is not in a `Change`, so it is not a key.
- Any notion of certainty; this aspect only produces candidates and names.
- Scanning source, matching names to sites.
- Resolving the SDK's own package layout.

## Acceptance criteria

1. Table test over **all 13** `ChangeKind` values: each yields a `Query` with either a name/operation
   or `UNSUPPORTED_CHANGE_KIND` — never an exception, never an `AttributeError` from a malformed
   payload.
2. Explicit mapping beats inference for both operations and fields; an exact `METHOD /path` key
   matches regardless of case of the method.
3. Inference: `DELETE /v1/charges/{id}` produces exactly `("charges.delete",)`;
   `GET /v1/customers/{id}` produces the ordered `get|list|retrieve` candidates;
   `/v2/files/{id}/refunds` keeps the intermediate segment (`files.refunds.<verb>`).
4. A component change yields `scope="component"` and the field name; an operation change yields
   `scope="operation"` with the field name when the kind has one.
5. `renamed` searches `before`, not `after`.
6. Same input → identical `Query` (dataclass equality) across runs and hash seeds.

## Dependencies & sequencing

Builds after `locate-result`. Aspect 4 consumes `Query`; aspect 3 does not.

## Open questions

- Inference for `put`/`patch` collapses to `update`; a real SDK may use `replace` or `set`. The
  multi-candidate rule makes that visible rather than wrong, and the mapping file is the escape
  hatch. Revisit after M0.3.
