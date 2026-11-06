# PRD: MCP tool-call locator (T8b)

- **Slug:** `mcp-locator`
- **Capability:** T8 in `docs/technical/CAPABILITY_ROADMAP.md` — **second slice, MCP tool-call locator**
- **Milestone:** M2.3 in `docs/ROADMAP.md` (Phase 2), second slice
- **Status:** implemented 2026-11-07 (`src/tenon/locate/mcp_*.py`, 1,342 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T8a emits typed `Change` records for MCP tools. Nothing finds the consumer code that calls those
tools, so a removed tool or a renamed argument still sends the user to grep
`call_tool("name", ...)` by hand — exactly the manual work the product exists to remove.

T8b adds the Python MCP tool-call locator: given a T8a `Change` and a repository, find
`session.call_tool("tool", arguments={...})` sites, the argument keys, and the constructs it cannot
prove. It returns the shipped `LocateResult` — certain `Site`s, ambiguity groups with the existing
reasons, or a named non-result — so T3's rename rule, T4's proof runner, T5's PR writer and the CLI
work unchanged. A `--source mcp` switch lets `tenon check` / `tenon fix` use the MCP loader, differ
and locator.

The dangerous shortcut is matching every `call_tool` method by name. A user object can have a
`call_tool` method; an unrooted session can be passed in; the tool name can be a variable. A site is
certain only when the receiver is rooted in the MCP client import/alias **and** the tool name is a
literal matching the changed tool. Everything else is an ambiguity group, never a guess.

**For whom:** the developer whose agent calls an MCP server, T3/T4/T5 once sites exist, and T8c's
probe mode.

## Goals & Success Metrics

1. **Located, not guessed.** `locate_mcp(change, root, config) -> LocateResult` returns file/line/
   column sites for the changed tool and its argument keys.
2. **Rooted + literal.** Certain only when the receiver is an MCP client alias/constructor/context
   binding and the tool name is a literal matching `change.location.path`; dynamic names/receivers
   are named ambiguity groups.
3. **Same contract.** Reuse `Site`, `SiteShape`, `AmbiguousGroup`, `LocateResult`, `LocateReason` and
   `AmbiguityReason`; T3's `keyword`/`dict_key` edits apply to the argument keys.
4. **Usable.** `tenon check` / `tenon fix` accept `--source mcp` and `[locate] source = "mcp"`, load
   T8a documents, diff them and call the MCP locator.
5. **Deterministic and offline.** Same repo/change/config → byte-identical JSON; committed fixtures;
   no MCP server, network, agent or model.

## User Personas & Scenarios

- **Developer.** `tenon check --source mcp tools-v1.json tools-v2.json` reports
  `client.py:12:9 keyword amount` for the renamed argument, plus the tool call.
- **T3 propose.** Edits `{"amount": ...}` to `{"amount_cents": ...}` using the existing `dict_key`
  rule; no new proposer rule.
- **T4 prove.** Runs the repo's test command in a copy; the MCP call is mocked or a fake client, no
  network.
- **Reviewer.** The report names the tool and the argument; an unrooted wrapper is a flagged
  suggestion, not a certain edit.
- **T8c probe.** Reuses the `call_tool`/tool-name knowledge for a live run later.

Scenario: T8a reports `tool create_charge inputSchema.amount` renamed to `amount_cents`. T8b finds
`await session.call_tool("create_charge", arguments={"amount": 100})` certain at the key, and an
`await wrapper.call_tool("create_charge", payload)` in another module as an `UNROOTED_RECEIVER` call
plus `DYNAMIC_KWARGS` for the payload.

## Requirements

### Must have

- **M1 — Config.** `McpLocateConfig(client_package: str = "mcp")`: a Python dotted package name;
  the package matches `mcp` or `mcp.<submodule>`. Frozen, slots. The CLI uses `[locate] sdk_package`
  when set, otherwise `mcp`. Python only in this card.
- **M2 — Python scan.** Parse `.py` files under the root, skipping `.venv`, `venv`, `node_modules`,
  `build`, `dist`, `__pycache__`, cache dirs and dot-directories. Reuse the T2 read/reachability
  policy: a file is scanned when it imports the client package or transitively imports a scanned
  local module; no import anywhere → `NO_SDK_IMPORT`.
- **M3 — Client rooting.** Bind a receiver as an MCP client from:
  - `from mcp import ClientSession; session = ClientSession(...)` (one-hop class alias);
  - `async with ClientSession(...) as session:` and `with ... as session:` (the context binding);
  - a direct `ClientSession(...).call_tool(...)` call.
  A parameter or an unbound variable is unrooted. No cross-file aliasing.
- **M4 — Calls.** Find `call_tool` attribute calls on a rooted or unrooted receiver. Extract the tool
  name from the first positional string literal or the `name=` keyword literal. A non-literal name is
  dynamic. Only calls whose literal name equals `change.location.path` are this tool's sites;
  other tools are ignored.
- **M5 — Arguments.** From the second positional argument or `arguments=`:
  - a dict literal → `dict_key` sites at string keys, column at the quote; `**` → `DYNAMIC_KWARGS`;
  - `dict(key=value, ...)` → `keyword` sites; `**` → `DYNAMIC_KWARGS`;
  - a variable/other expression → `DYNAMIC_KWARGS` at the argument;
  - a nested object under a key is not walked (the changed field is a top-level tool argument).
- **M6 — Change kinds.** `ENDPOINT_REMOVED/ADDED` → the matching call sites (`call`, symbol
  `call_tool`). `PROPERTY_REMOVED/ADDED/REQUIRED_ADDED/TYPE_CHANGED`, `RENAMED`, `ENUM_NARROWED` →
  the call sites plus the argument key for the changed field (the field name comes from the change
  payload; `PROPERTY_REQUIRED_ADDED` also returns the call sites when the argument is absent, because
  the fix is "add it here"). `ADDITIONAL_PROPERTIES_CHANGED` → the call sites. An output-schema
  property change (`/outputSchema/` in the pointer) → the call sites only; no result-value dataflow.
  Anything else → `UNSUPPORTED_CHANGE_KIND`.
- **M7 — Certainty and ambiguity.** A rooted call with a literal matching tool name and a literal
  field key is certain. A dynamic tool name → `DYNAMIC_GETATTR` group with the call site; an unrooted
  receiver → `UNROOTED_RECEIVER` group with the call and its candidate keys; dynamic arguments →
  `DYNAMIC_KWARGS`; no matching call → `NO_SITES`; no MCP import → `NO_SDK_IMPORT`. No new
  `AmbiguityReason` or `LocateReason`.
- **M8 — Result and order.** Reuse `LocateResult`; certain/ambiguous ordering by
  `(path, line, column)`; byte-stable `to_json()`; the `change` passes through unchanged.
- **M9 — CLI source.** `--source openapi|mcp` on `check`/`fix`; `[locate] source` in `tenon.toml`
  (default `openapi`). For `mcp`: `load_mcp`/`diff_mcp` instead of `load`/`diff`, and `locate_mcp`
  instead of `locate`; `sdk_package` is the MCP client package; `language` must be `python` in this
  card (a named usage error otherwise). `propose`/`prove`/`write_pr` are unchanged. The `unanalyzed`
  from `diff_mcp` reaches `write_pr`.
- **M10 — Tests.** Fixtures: a rooted `async with` session + dict arguments; a one-hop constructor
  alias; a direct constructor call; an unrooted receiver; a dynamic tool name; a `dict(...)`
  arguments call; a variable/`**` payload; a non-matching tool; a non-MCP file; an output-schema
  change; a tool removed; a required-added field. CLI tests for `--source mcp` check/fix and config.
- **M11 — Offline.** No MCP server, network, agent or model; fixture repos only.

### Should have

- **S1 — `line_text`** on every site, as T2.
- **S2 — `[locate] client_package`** alias for `sdk_package` in MCP mode; keep one key if free.

### Nice to have

- **N1 — Low-level `send_request("tools/call", ...)`**; skipped in this card unless the scan is free.
- **N2 — TypeScript MCP locator**; a separate card.
- **N3 — Result-field dataflow** for output schemas; out of scope.

## Data Model

```
McpLocateConfig
  client_package: str              # Python dotted, e.g. "mcp"

locate_mcp(change, root, config) -> LocateResult
  certain:   tuple[Site, ...]      # call / dict_key / keyword
  ambiguous: tuple[AmbiguousGroup, ...]
  reason:    LocateReason | None
  to_json() -> str                 # byte-stable
```

The scanner reuses the shipped `Site`/`SiteShape`/`AmbiguousGroup`/`LocateResult`; no new reason or
shape value.

## API Contract

```python
from tenon.locate import McpLocateConfig, locate_mcp

config = McpLocateConfig(client_package="mcp")
result = locate_mcp(change, "path/to/repo", config)
result.certain    # Site(path="client.py", line=12, column=9, shape="dict_key", symbol="amount")
result.ambiguous  # UNROOTED_RECEIVER / DYNAMIC_GETATTR / DYNAMIC_KWARGS
result.reason     # None, NO_SDK_IMPORT, NO_SITES, UNSUPPORTED_CHANGE_KIND, ...
```

CLI:

```sh
tenon check repo --source mcp --old tools-v1.json --new tools-v2.json --sdk-package mcp
tenon fix   repo --source mcp --old tools-v1.json --new tools-v2.json \
  --sdk-package mcp --check "python -m pytest -q"
```

## Technical Considerations

- **Why Python first.** The high-level MCP Python SDK has one stable call shape
  (`ClientSession.call_tool(name, arguments=...)`); the TS SDK wraps a different object shape. T2 is
  the precedent: one language, one contract, then widen.
- **Why root the receiver.** A `call_tool` method name alone is weak evidence; any wrapper can have
  one. The `ClientSession` import/alias plus a literal tool name is the T2-style bar. The `async with`
  binding is the common MCP pattern; support it explicitly.
- **Why filter by tool name.** The same repo may call many tools through one session; only the
  changed tool's calls are sites. A dynamic name cannot be attributed and becomes a group.
- **Why reuse `dict_key`/`keyword`.** T3 already edits those exact spans; a new shape would need a
  new rule. The T2 scanner's key-column rule applies.
- **Output schemas.** A result field is a dataflow question; this card stops at the call site. The
  report says the tool, not the result field.
- **The CLI source switch.** The loader/differ/locator triple is selected once; the report, propose,
  proof and PR paths are unchanged. `language=ts` + `source=mcp` is a named error in this slice.
- **No MCP server.** The diff and locator are static; the probe is T8c.

## Risks & Open Questions

- **MCP client patterns vary.** Low-level `send_request("tools/call")`, wrappers, sessions passed as
  parameters and framework-specific clients may be missed or unrooted. The unrooted group is the
  honest result; a real fixture can force the next pattern.
- **The `async with` binding.** A `ClientSession` created inside a context manager is the common
  shape; a session returned by a factory (`get_session()`) is unrooted. Documented.
- **Output dataflow.** A returned value's `.field` access is not located; the call site is.
- **CLI `source` vs `language`.** MCP is Python-only in this card; a TS MCP locator later extends
  the same source switch.
- **The `mcp` package.** The config names the client package; the user can set a wrapper package,
  but the `call_tool` pattern is fixed. A custom client method needs a config field later.
- **Open question — `send_request` low-level calls.** Skipped; a real repo may use them. The scanner
  can add the pattern without changing the result contract.
- **Open question — a required-added field with no argument present.** The call site is certain (add
  it here); the absence of a key is not a site. The report says the tool call.

## Out of Scope

- The TypeScript MCP locator; `tenon probe`/transport/agent (T8c); T9 benchmark.
- Low-level `send_request("tools/call", ...)`, framework wrappers, cross-file aliases.
- Result-value dataflow for output schemas.
- New proposer rules or edits beyond T3's existing shapes.
- MCP pagination, network calls, a server.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `mcp-scan` | Python file discovery/reachability, client aliases and `with` bindings, `call_tool` extraction, tool name/arguments evidence, dynamics. No result policy. |
| `mcp-locate` | `McpLocateConfig`, `locate_mcp`, change-kind/field-name policy, certainty/ambiguity, fixtures. No CLI. |
| `mcp-cli` | `--source`/`[locate] source`, loader/differ/locator dispatch, `language`/source validation, CLI tests. No probe. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | T8a changes with no consumer surface. |
| User understanding | 🟢 | Developer, T3/T4/T5, T8c; the MCP session pattern is concrete. |
| Success metrics | 🟢 | Rooted+literal certainty, same result contract, CLI source, offline fixtures. |
| Scope clarity | 🟢 | Python `call_tool` only; TS, send_request, probe and dataflow excluded. |
| Edge cases & risks | 🟡 | Wrapper/factory sessions are unrooted; output dataflow is a known gap. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses the T2 scan/result patterns; one new AST pattern and the `async with` binding. |
| Go-to-market | 🟢 | Completes the MCP path T8a opened; T8c is the provider hook. |

**Areas to strengthen before sharing:** the locator only knows the high-level `call_tool` pattern.
A real MCP repo that uses `send_request` or a framework wrapper would be partly unrooted. The report
is honest, but the coverage claim must stay narrow.

**The question I would want answered before greenlighting this:** *If the first real MCP repo passes
its session through a helper (`async def run(session): await session.call_tool(...)`), the locator
marks every call unrooted and finds no certain site. Is that acceptable, or should a parameter typed
`ClientSession` root the receiver?* The answer this card records: no type inference; a parameter is
unrooted until a real fixture forces a type-annotation rule. The ambiguity group tells the user why.
