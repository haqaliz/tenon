# Spec: `mcp-ingest` (T8a)

- **Feature:** `mcp-diffs`
- **PRD:** `docs/planning/mcp-diffs/prd.md` (§ M1, M2, M5)
- **Boundary:** reading a `tools/list` document into a normalized, validated mapping. No diff.

## Problem slice

The differ needs one stable document shape before it can compare anything. The MCP wire result is an
array with a cursor; a JSON pointer into it moves when tools are reordered. This aspect normalizes it
to a name-keyed mapping, validates the tool surface, resolves local `$ref`s and refuses bad input by
name.

## In-scope requirements

- `parse_mcp(text, source) -> dict`, `load_mcp(path) -> dict` (UTF-8, read-only).
- Accept `{"tools": [...], "nextCursor": ...}` (extra keys ignored) and a bare `[...]` array.
- Normalize to `{"tools": {<name>: <tool object>}}`; preserve `inputSchema`, `outputSchema` and
  other tool keys.
- Validate: `tools` is a list (or the bare array); each tool is a mapping; `name` is a non-empty
  string; names are unique; `inputSchema`/`outputSchema`, when present, are mappings. Violations are
  `NOT_A_SPEC` with the pointer.
- `UNPARSEABLE` for a YAML/JSON syntax error, with line/column; `EXTERNAL_REF` for a non-local
  `$ref`; `UNRESOLVED_REF` for a local ref that does not resolve.
- Resolve local `$ref` with the shipped `resolve_refs`; a cycle is left as a marker for the differ to
  record as `unanalyzed` (`CYCLIC_REF`).
- Deterministic normalized document; JSON byte-stable; tool order does not matter.
- Export `parse_mcp`/`load_mcp` from `tenon.detect`.

## Out-of-scope

- The diff, the new `ChangeKind`, CLI, probe, network.
- Following `nextCursor`; a saved page is assumed complete.
- Descriptions/titles/annotations.

## Acceptance criteria

- **AC1 — Shapes.** The envelope, the bare array and JSON/YAML all normalize to the same mapping;
  `nextCursor` and extra keys are ignored.
- **AC2 — Validation.** A missing `tools`, a non-list `tools`, a non-mapping tool, an empty/non-string
  name, a duplicate name, and a non-mapping `inputSchema`/`outputSchema` each raise `SpecRefusal`
  with a pointer.
- **AC3 — Parse errors.** Bad YAML/JSON is `UNPARSEABLE` with line/column; an empty document is
  `UNPARSEABLE`.
- **AC4 — Refs.** A local `#/...` ref resolves; an external ref is `EXTERNAL_REF`; a missing local
  ref is `UNRESOLVED_REF`; a cycle is preserved as a marker, not a crash.
- **AC5 — Determinism.** The normalized document serialises identically across hash seeds and tool
  order; `load_mcp` equals `parse_mcp` on the same bytes.
- **AC6 — No diff.** The module never imports or calls `diff_mcp`/`diff`; the shipped `load`/`parse`
  are untouched.

## Dependencies and sequencing

- Depends on the shipped `SpecRefusal`, `resolve_refs` and `UnanalyzedReason`.
- First; `mcp-diff` consumes the normalized document.

## Open questions / risks

- `resolve_refs` resolves the whole normalized document; a `$ref` to a tool schema is fine, a `$ref`
  to a non-schema value is the differ's concern.
- A tool name containing `/`/`~` is escaped only when a pointer is built; the mapping key stays the
  raw name.
