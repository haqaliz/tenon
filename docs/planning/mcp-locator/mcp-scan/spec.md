# Spec: `mcp-scan` (T8b)

- **Feature:** `mcp-locator`
- **PRD:** `docs/planning/mcp-locator/prd.md` (§ M2–M5)
- **Boundary:** Python evidence only. No result policy, no CLI.

## Problem slice

The locator needs evidence about `call_tool` calls: which receiver, which literal tool, which argument
keys, and what is dynamic. This aspect parses Python and emits that evidence without deciding
certainty.

## In-scope requirements

- `scan_mcp(root, client_package) -> McpScan` in `src/tenon/locate/mcp_scan.py`.
- `McpHit(path, line, column, shape, symbol, tool, rooted, line_text)`; `McpDynamic(path, line,
  column, kind, tool, symbol)`; `McpScan(modules, hits, dynamics)`; frozen, slots, canonical order.
- Discovery/reachability: reuse T2's `.py` read and reverse-edge import reachability for the client
  package (`mcp` or submodules); skip the same directories; syntax-error/undecodable files skipped;
  `modules` is the reachable set.
- Client rooting: an import of the client package, a one-hop `session = ClientSession(...)` alias,
  a `with`/`async with ClientSession(...) as session` binding, and a direct
  `ClientSession(...).call_tool(...)` receiver. A parameter/unbound name is unrooted; a second hop is
  `ALIAS_CHAIN`.
- Calls: `call_tool` attribute calls; tool name from the first positional string or the `name=`
  keyword; a non-literal name is a `GETATTR` dynamic. Emit a `call` hit (`symbol="call_tool"`,
  `tool=<literal or None>`, `rooted`).
- Arguments: second positional or `arguments=`; a dict literal emits one `dict_key` hit per string
  key at the quote; `dict(key=...)` emits `keyword` hits; `**` or a variable/other expression emits
  a `STAR_KWARGS` dynamic with the tool name. Nested objects are not walked.
- Columns: 1-based character columns via the T2 UTF-8 rule; `line_text` on every hit.
- No writes, no imports/execution of the scanned code.

## Out-of-scope

- The certainty/ambiguity result, the CLI, `send_request`, TS, output dataflow.
- A general MCP client type checker; cross-file aliases.

## Acceptance criteria

- **AC1 — Reachability.** A file importing `mcp` is scanned; a transitive local importer is scanned;
  an unrelated `call_tool` file is not; no import → empty `modules`.
- **AC2 — Rooting.** `async with ClientSession(...) as session`, a constructor alias and a direct
  constructor receiver are rooted; a parameter is unrooted; a two-hop alias is `ALIAS_CHAIN`.
- **AC3 — Tool name.** A positional literal and a `name=` literal are recorded; a variable name is a
  `GETATTR` dynamic; a call for another tool is still evidence with that tool.
- **AC4 — Arguments.** Dict keys → `dict_key`; `dict(...)` → `keyword`; `**`/variable →
  `STAR_KWARGS` with the tool; nested keys are not emitted.
- **AC5 — Columns/order.** Exact 1-based line/column/shape/symbol/tool; canonical order; two scans
  identical; no writes.

## Dependencies and sequencing

- Depends on the shipped `SiteShape`, T2 read/reachability/alias helpers and `_column`.
- First; `mcp-locate` consumes `McpScan`.

## Open questions / risks

- The T2 helpers are private; reuse them rather than forking the reachability policy.
- The `with` binding is syntactic; a factory-returned session is unrooted.
- A wrapper package with a different client class is not recognized in this card.
