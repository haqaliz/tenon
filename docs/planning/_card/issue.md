# Card: feat/mcp-diffs

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T8 MCP diffs and probe mode** — first slice: **MCP tool-schema diffs**
  (`docs/technical/CAPABILITY_ROADMAP.md:14`)
- **Milestone:** M2.3 (`docs/ROADMAP.md`), first slice
- **State:** shipped 2026-11-07 (`src/tenon/detect/mcp_*.py`, 1,253 tests)
- **Branch:** `feat/mcp-diffs/aliz`
- **Worktree:** `.claude/worktrees/feat-mcp-diffs`

## Brief

T1 diffs OpenAPI documents. MCP servers publish a machine-readable `tools/list` result — tool names,
input schemas, output schemas — and those tools break consumers the same way HTTP endpoints do. The
product promises to trust machine-readable change sources; MCP is one of them (`CLAUDE.md` §3).

This card adds an MCP tool-schema ingest and differ that emits the **same** `Change` / `DiffResult`
records as T1, so a later MCP tool-call locator, `tenon check` source switch or probe mode can consume
it unchanged. It is engine-only: no network, no agent, no probe.

The hard rules do not change: only a machine-readable `tools/list` document is a source; an
unparseable or unsupported schema is a named refusal with a pointer, never a partial guess;
descriptions are not changes; output is deterministic and byte-stable.

## Constraints carried in from the repo

- `CLAUDE.md` §3: machine-readable sources only; a changelog paragraph is a hint.
- `docs/technical/ARCHITECTURE.md`: the change record is the unit; adding a source should not touch
  locate or prove.
- T1's `Change`, `DiffResult`, `SpecRefusal` and canonical ordering are the contract to reuse.
- Offline: committed JSON fixtures; no MCP server, no network, no model.

## Scope fence

Not this card: `tenon probe`, an agent, network transport, an MCP tool-call locator, CLI
`--source mcp`, SDK release metadata. Those are T8b/T8c after the diff contract is stable.
