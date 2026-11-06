# PRD: MCP tool-schema diffs (T8a)

- **Slug:** `mcp-diffs`
- **Capability:** T8 in `docs/technical/CAPABILITY_ROADMAP.md` — **first slice, MCP diffs**
- **Milestone:** M2.3 in `docs/ROADMAP.md` (Phase 2), first slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1 diffs OpenAPI documents. MCP servers publish a machine-readable `tools/list` result — tool names,
input schemas, output schemas — and those tools break consumers the same way HTTP endpoints do. The
official MCP registry listed 43,298 servers on 2026-10-14 (`CLAUDE.md` quick facts); an agent that
calls a renamed tool or a now-required argument fails the same silent way an SDK caller does.

The product already trusts machine-readable sources (`CLAUDE.md` §3) and the architecture names MCP
as a source. Nothing in `detect` can read or diff one. T8a adds the ingest and differ that emit the
**same** `Change` / `DiffResult` records as T1, so a later MCP tool-call locator or `tenon probe` can
consume them unchanged.

The dangerous shortcuts are rejected here: treating a description edit as a breaking change, pairing
two unrelated tools as a "rename", silently skipping `oneOf`, and returning a partial diff when the
input is not a `tools/list` result. A machine-readable source or a named refusal, never a guess.

**For whom:** T2/T6's future MCP tool-call locator, T3/T4/T5 once that locator exists, `tenon probe`
(T8b), and the developer reading a changed-tool report.

## Goals & Success Metrics

1. **Same contract.** `diff_mcp(old, new) -> DiffResult` emits the shipped `Change` records with the
   same kinds, `breaking`, `confidence`, canonical order and byte-stable JSON.
2. **Complete tool surface.** Tool added/removed; input and output schema properties
   added/removed/required-added/type-changed/enum-narrowed; `additionalProperties` changes; nested
   objects and arrays one level deep like T1.
3. **Honest failure.** A non-`tools/list` input, a duplicate/empty tool name, an unsupported
   composition or an external `$ref` is a named `SpecRefusal` or an `unanalyzed` record with a
   pointer — never a traceback, never a partial guess.
4. **Determinism.** Same two inputs → identical records and byte-identical JSON across hash seeds.
5. **Offline.** Committed JSON fixtures; no MCP server, network, agent or model.

Measured by `tests/detect/` fixtures; no live server.

## User Personas & Scenarios

- **Future MCP locator.** "Give me the changed tools and fields with stable pointers, so I can find
  `call_tool("name", {...})` sites." Needs `location.method="tool"`, `path=<tool>`, and the pointer.
- **`tenon probe` (T8b).** Needs a typed change list for a server before/after, not prose.
- **Developer.** Sees `tool "create_charge" inputSchema.amount is now required` in the check report.
- **Reviewer.** The PR body can say the source was a `tools/list` document, not a changelog.

Scenario: a server renames a tool argument from `amount` to `amount_cents` and makes it required.
T8a emits `renamed` (property, inferred) or `property_removed` + `property_required_added`, with the
tool-scoped location and a stable pointer. A tool removed from the list is `endpoint_removed`,
breaking.

## Requirements

### Must have

- **M1 — Loader.** `parse_mcp(text, source) -> dict` and `load_mcp(path) -> dict` accept:
  - a `tools/list` result `{"tools": [...], "nextCursor": ...}` (extra keys ignored), and
  - a bare `[...]` tool array.
  Normalize to `{"tools": {<name>: <tool object>}}`, preserving each tool's `inputSchema` and
  `outputSchema`. JSON or YAML input (JSON is the MCP wire form). Read-only, UTF-8.
- **M2 — Tool validation.** A tool must be a mapping with a non-empty string `name`; names are unique;
  `inputSchema`/`outputSchema`, when present, must be mappings. A violation is `NOT_A_SPEC` with the
  pointer; a syntax error is `UNPARSEABLE` with line/column. No partial document on refusal.
- **M3 — Tool changes.** A removed tool is `endpoint_removed` (`breaking: true`); an added tool is
  `endpoint_added` (`breaking: false`). `location.method = "tool"`, `location.path = <name>`, pointer
  `#/tools/<name>`, `before`/`after` = the tool name. No tool-name rename inference in this card
  (a removed+added pair stays two records).
- **M4 — Schema changes.** Walk `inputSchema` and `outputSchema`:
  - `property_removed` (breaking true), `property_added` (breaking false).
  - Input only: `property_required_added` (breaking true) when a property newly appears in `required`.
  - `property_type_changed` (breaking true) and `enum_narrowed` (breaking true) when the new enum is a
    strict subset.
  - `ADDITIONAL_PROPERTIES_CHANGED` (new `ChangeKind`, breaking true when the schema moves from
    open/absent to `false`) with the schema pointer.
  - Nested object properties and array `items` are walked; the pointer names the property.
  - Property rename inference reuses T1's rule (exactly one removed/added pair with the same type and
    shape) and emits `renamed` with `confidence: "inferred"`; otherwise the pair stays removed+added.
  - Output schemas use the same kinds but do not emit `property_required_added` (a new required
    output is not a consumer requirement); a removed/type-changed/enum-narrowed output is breaking.
- **M5 — Composition and refs.** Local `$ref` is resolved with the T1 resolver; an external ref is
  `EXTERNAL_REF`; a cycle is `unanalyzed` (`CYCLIC_REF`). Plain `allOf` property merges are walked;
  `oneOf`/`anyOf`/`discriminator` and non-merge `allOf` are skipped and recorded in `unanalyzed` as
  `UNSUPPORTED_COMPOSITION` at the pointer.
- **M6 — Refusals.** `SpecRefusal` codes: `NOT_A_SPEC`, `UNPARSEABLE`, `UNRESOLVED_REF`,
  `EXTERNAL_REF`, plus a pointer (or line/column). A refusal returns no `DiffResult`.
- **M7 — Order and JSON.** Reuse `DiffResult`'s canonical order and byte-stable `to_json()`.
- **M8 — API.** Export `parse_mcp`, `load_mcp`, `diff_mcp` from `tenon.detect`; the existing
  `load`/`parse`/`diff` are untouched. `diff_mcp` takes two normalized documents.
- **M9 — Tests.** Fixtures: a `tools/list` envelope, a bare array, a tool add/remove, an input and
  output schema change, a required-added, a type change, an enum narrowing, `additionalProperties`,
  a local `$ref`, an `oneOf` skip, a duplicate name, an empty name, an external `$ref`, a syntax
  error. Offline and deterministic.

### Should have

- **S1 — `nextCursor` ignored**; a paginated save is assumed complete. A later probe can follow cursors.
- **S2 — Tool order is irrelevant**; the normalized mapping and `DiffResult` ordering make it stable.

### Nice to have

- **N1 — `title`/`description` carried on a change for prose**; skipped, as T1 skips prose.
- **N2 — `outputSchema` structural changes beyond properties**; skipped beyond the property walk.

## Data Model

```
McpDocument (normalized)
  tools: { <name>: { name, inputSchema?, outputSchema?, ...other keys preserved } }

Change (shipped)
  kind: endpoint_removed | endpoint_added | property_removed | property_added
        | property_required_added | property_type_changed | enum_narrowed
        | ADDITIONAL_PROPERTIES_CHANGED
  location: { method: "tool", path: <tool>, pointer: "#/tools/<tool>/..." }
  before / after: JSON value | None
  breaking: bool
  confidence: "certain" | "inferred"
```

`ADDITIONAL_PROPERTIES_CHANGED` is a deliberate extension of the closed T1 taxonomy. T1's OpenAPI
differ never emits it; the locate query treats it as `UNSUPPORTED_CHANGE_KIND` until a rule exists.
The MCP tool is a synthetic operation (`method="tool"`), so the existing `operations` mapping key can
be `"tool <name>"` when a locator lands.

## API Contract

```python
from tenon.detect import diff_mcp, load_mcp, parse_mcp

old = load_mcp("tools-v1.json")     # normalized dict; raises SpecRefusal
new = load_mcp("tools-v2.json")
result = diff_mcp(old, new)         # DiffResult; canonical order, byte-stable JSON
result.changes                      # list[Change]
result.unanalyzed                   # composition/cycle markers
```

No CLI, no network, no MCP server, no probe.

## Technical Considerations

- **Why normalize to a name-keyed mapping.** A JSON pointer into the wire array (`#/tools/0`) moves
  when tools are reordered. A name-keyed normalized document gives stable pointers and matches the
  `operations` mapping convention.
- **Why reuse `Change`/`DiffResult`.** The architecture's unit is the change record; a parallel MCP
  record would fork T2–T5. The new kind is the only taxonomy extension.
- **Why the synthetic `method="tool"`.** It gives the future locator the same operation scope T2
  already understands, without adding a `Location.source` field. The mapping key is explicit; there
  is no verb inference for tools.
- **Schema walking.** Reuse T1's property/type/enum/required rules and local `$ref` resolver rather
  than a second JSON Schema implementation. Extract shared helpers only if the OpenAPI diff couples
  them to paths/components.
- **Output vs input.** Required-added is an input requirement; an output's new required field is not
  a consumer requirement. Removals/types/enums remain breaking on both sides.
- **No tool rename inference.** Two tools with different names are not assumed to be the same tool;
  property renames inside a tool use T1's cautious rule.

## Risks & Open Questions

- **Schema diversity.** Real MCP input schemas use `$ref`, `oneOf`, nested objects and formats. The
  compositor policy records what it cannot analyze; it does not guess.
- **The new kind.** `ADDITIONAL_PROPERTIES_CHANGED` expands the T1 taxonomy. Downstream returns
  `UNSUPPORTED_CHANGE_KIND`; the record is still available to a report. A future locator/rule can
  consume it.
- **Tool names in pointers.** A name with `/` or `~` is RFC 6901-escaped; fixtures cover it.
- **Output-schema semantics.** Reusing the request kinds for responses is a simplification; a future
  consumer-facing rule may split them.
- **No real server fixture.** The fixtures are saved `tools/list` results, not a live capture; a
  later probe card records real ones.
- **Open question — should a tool removed and added under the same name with a different schema be a
  `renamed`?** No: same name means the same tool; its schema changes are property records.
- **Open question — pagination.** `nextCursor` is ignored in this slice; a probe can follow it.

## Out of Scope

- `tenon probe`, MCP transports (stdio/HTTP/SSE), an agent, network calls.
- An MCP tool-call locator for Python/TS; a CLI `--source mcp`.
- SDK release metadata; T9 benchmark; T10/T11.
- Prose/description/annotation diffs; a JSON Schema validator.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `mcp-ingest` | Envelope/array parsing, normalization, tool validation, refusals, `$ref` resolution, byte-stable input document. No diff. |
| `mcp-diff` | Tool add/remove, input/output schema walk, property/type/enum/required/additionalProperties records, rename inference, unanalyzed composition, `DiffResult`. No CLI. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | MCP is a named machine-readable source; the registry size is cited. |
| User understanding | 🟡 | The first consumers are future locator/probe cards; no live MCP user yet. |
| Success metrics | 🟢 | Same contract, tool+schema coverage, refusals, deterministic JSON, offline. |
| Scope clarity | 🟢 | Engine-only; probe, locator, CLI and prose excluded. |
| Edge cases & risks | 🟡 | Schema diversity, output semantics and the new kind are documented limits. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses T1's records/resolver; one small taxonomy extension. |
| Go-to-market | 🟢 | The first MCP change source; the probe is the provider-facing hook. |

**Areas to strengthen before sharing:** the engine-only slice does not yet find MCP call sites. A
reviewer may ask why a diff without a locator is useful; the answer is that it is the source contract
T8b/T8c build on, and it is testable offline now.

**The question I would want answered before greenlighting this:** *If real MCP schemas are full of
`oneOf` and `$ref`, the differ may record most of a server as unanalyzed and find little. Is that
acceptable, or should the first slice cover more JSON Schema composition?* The answer this card
records: record what cannot be analyzed, never guess; a real fixture can force the composition
follow-up.
