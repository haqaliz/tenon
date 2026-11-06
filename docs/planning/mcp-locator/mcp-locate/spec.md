# Spec: `mcp-locate` (T8b)

- **Feature:** `mcp-locator`
- **PRD:** `docs/planning/mcp-locator/prd.md` (§ M1, M6–M8)
- **Boundary:** `McpLocateConfig`, `locate_mcp`, certainty and the shared result. No CLI.

## Problem slice

The scanner reports evidence; this aspect turns it into the shipped `LocateResult`: certain sites for
the changed tool/field, ambiguity groups for everything it cannot prove, and a named reason when
nothing ran.

## In-scope requirements

- `McpLocateConfig(client_package: str = "mcp")`: Python dotted package; frozen, slots; matches `mcp`
  or `mcp.<submodule>`; a bad name raises `ValueError`.
- `locate_mcp(change, root, config) -> LocateResult`:
  - Tool: `change.location.method == "tool"` and a non-empty `path`; otherwise
    `UNSUPPORTED_CHANGE_KIND`.
  - Kinds:
    - `ENDPOINT_REMOVED`/`ENDPOINT_ADDED` → matching call sites.
    - `PROPERTY_REMOVED`/`PROPERTY_ADDED`/`PROPERTY_REQUIRED_ADDED`/`PROPERTY_TYPE_CHANGED`,
      `RENAMED`, `ENUM_NARROWED` → matching calls plus the argument key for the change's field name
      (from the payload; `RENAMED` uses `before`). `PROPERTY_REQUIRED_ADDED` also returns the call
      sites when the argument is absent.
    - `ADDITIONAL_PROPERTIES_CHANGED` → matching call sites.
    - A pointer containing `/outputSchema` → matching call sites only.
    - `SCHEMA_*` and anything else → `UNSUPPORTED_CHANGE_KIND`.
  - Certainty: a rooted call with the literal tool name is a certain `call` site; a rooted argument
    key with the field name is a certain `keyword`/`dict_key` site.
  - Ambiguity: dynamic tool name → `DYNAMIC_GETATTR` with the call; `STAR_KWARGS` for the tool →
    `DYNAMIC_KWARGS` with the call; unrooted matching calls → `UNROOTED_RECEIVER` with the call and
    its candidate keys; a second-hop alias → `ALIAS_CHAIN`.
  - Reasons: no reachable module → `NO_SDK_IMPORT`; no matching call/key and no group → `NO_SITES`;
    a non-tool change/unsupported kind → `UNSUPPORTED_CHANGE_KIND`.
  - Reuse `Site`, `SiteShape`, `AmbiguousGroup`, `LocateResult`, the shipped reasons and canonical
    ordering; no new enum value.
- Export `McpLocateConfig` and `locate_mcp` from `tenon.locate`.

## Out-of-scope

- The scanner, CLI, TS, probe, output dataflow.
- New proposer rules; T3 edits the shipped shapes.
- `send_request`, factory/wrapper sessions.

## Acceptance criteria

- **AC1 — Config.** `default "mcp"` and a submodule package construct; empty/whitespace/path-like
  names raise.
- **AC2 — Tool call.** A rooted `async with` session call → a certain `call` site at the exact
  line/column; the `change` passes through.
- **AC3 — Field key.** A renamed/removed/required/type/enum field → the certain key site; a
  required-added with no key also returns the call site.
- **AC4 — Certainty.** A dynamic tool name → `DYNAMIC_GETATTR`; a variable/`**` payload →
  `DYNAMIC_KWARGS`; an unrooted matching call → `UNROOTED_RECEIVER` with the call and candidate
  key; no certain site from any of them.
- **AC5 — Reasons.** No MCP import → `NO_SDK_IMPORT`; no matching tool → `NO_SITES`; a schema kind →
  `UNSUPPORTED_CHANGE_KIND`.
- **AC6 — Output.** A `/outputSchema` property change returns the call site only, no argument key.
- **AC7 — Determinism.** `to_json()` byte-identical across runs/hash seeds; canonical order; a site
  is never both certain and a candidate.

## Dependencies and sequencing

- Depends on `mcp-scan`; before `mcp-cli`.
- The `Change` records come from `diff_mcp` or direct construction in tests.

## Open questions / risks

- Field-name extraction depends on T8a's payload shapes (`before`/`after` dicts or strings); a kind
  with no name is a tool-level change.
- A `RENAMED` tool (no T8a inference) is two endpoint records; each locates the matching call.
- Output dataflow is out; the call site is the honest target.
