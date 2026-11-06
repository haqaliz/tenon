# Spec: `mcp-diff` (T8a)

- **Feature:** `mcp-diffs`
- **PRD:** `docs/planning/mcp-diffs/prd.md` (§ M3–M7)
- **Boundary:** two normalized MCP documents into the shipped `DiffResult`. No CLI, probe or network.

## Problem slice

The differ must answer what broke between two `tools/list` documents in the same typed records T1
uses, so a future MCP locator and the report can consume them unchanged.

## In-scope requirements

- `diff_mcp(old, new) -> DiffResult`; both are normalized documents from `mcp-ingest`.
- `ChangeKind.ADDITIONAL_PROPERTIES_CHANGED` added to the closed taxonomy; the T1 OpenAPI differ does
  not emit it.
- Tools: removed → `ENDPOINT_REMOVED` (breaking true); added → `ENDPOINT_ADDED` (breaking false);
  `location.method = "tool"`, `path = <name>`, pointer `#/tools/<name>`, before/after = the name.
- Schemas: walk `inputSchema` and `outputSchema` with T1's shapes:
  - property removed (breaking true), added (breaking false);
  - input required-added (breaking true); output required-added is not emitted separately;
  - type changed (breaking true);
  - enum narrowed when the new enum is a strict subset (breaking true);
  - `additionalProperties` changed: breaking true when the schema becomes closed/absent→false;
    a widening is non-breaking; pointer at the schema; `before`/`after` the boolean/absent value.
  - Nested object properties and array `items` are walked; pointers name the property.
- Property rename inference reuses `infer_renames`; tool names are not inferred as renames.
- Composition: plain `allOf` merge walked; `oneOf`/`anyOf`/discriminator/non-merge `allOf` skipped and
  recorded in `unanalyzed` (`UNSUPPORTED_COMPOSITION`); a cyclic `$ref` marker is `CYCLIC_REF`.
- `DiffResult` canonical order and byte-stable JSON; no partial result on a `SpecRefusal` (the ingest
  refuses first).
- Export `diff_mcp` from `tenon.detect`; the existing `diff` is untouched.

## Out-of-scope

- The loader/validation (mcp-ingest), CLI, MCP tool-call locator, probe.
- Description/annotation diffs; output `required` semantics beyond not emitting required-added.
- A JSON Schema validator or full `oneOf` reasoning.

## Acceptance criteria

- **AC1 — Tool changes.** Removed/added tools emit the right kind, method/path/pointer, before/after
  and breaking flag; tool order is irrelevant.
- **AC2 — Input properties.** Removed, added, required-added, type-changed and enum-narrowed emit the
  right kind, pointer, before/after and breaking flag.
- **AC3 — Output properties.** Removed/type/enum are breaking; added is not; no separate
  required-added record.
- **AC4 — additionalProperties.** Open/absent → false emits `ADDITIONAL_PROPERTIES_CHANGED` with
  breaking true; the reverse is non-breaking; no record when equal.
- **AC5 — Nested.** Object properties and array items are walked; pointers are exact.
- **AC6 — Renames.** A unique removed/added property pair of the same shape becomes `renamed`
  (inferred); ambiguous pairs stay removed+added; tools never pair as renames.
- **AC7 — Composition.** `oneOf`/`anyOf`/non-merge `allOf`/cycles appear in `unanalyzed` with the
  pointer; plain `allOf` merges are walked.
- **AC8 — Determinism.** Byte-identical JSON across hash seeds and input tool order; canonical order.
- **AC9 — Taxonomy.** `ChangeKind` has exactly fourteen values; the T1 differ's 13-kind behavior is
  unchanged.

## Dependencies and sequencing

- Depends on `mcp-ingest` and the shipped `Change`/`DiffResult`/`infer_renames`.
- Last.

## Open questions / risks

- Reusing T1's request kinds for output schemas is a simplification; documented.
- The new kind is `UNSUPPORTED_CHANGE_KIND` downstream until a rule/locator exists.
- Real MCP schemas may be largely `oneOf`; the `unanalyzed` record is the honest result.
