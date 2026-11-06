# Card: feat/mcp-locator

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T8 MCP diffs and probe mode** — second slice: **MCP tool-call locator**
  (`docs/technical/CAPABILITY_ROADMAP.md:14`)
- **Milestone:** M2.3 (`docs/ROADMAP.md`), second slice
- **Branch:** `feat/mcp-locator/aliz`
- **Worktree:** `.claude/worktrees/feat-mcp-locator`

## Brief

T8a emits typed `Change` records for MCP tools, but nothing finds the consumer code that calls those
tools. A tool removed, an argument renamed or a required argument added is reported; the user still
has to grep `call_tool("name", ...)` by hand.

T8b adds the MCP tool-call locator for Python: given a T8a `Change` and a repository, find
`session.call_tool("tool", arguments={...})` sites, the argument keys, and the sites the locator
cannot prove. It returns the same `LocateResult` — certain `Site`s, ambiguity groups with named
reasons, or a named non-result — so T3's existing rename rule, T4's proof runner, T5's PR writer and
the CLI work unchanged. A `--source mcp` switch lets `tenon check` / `tenon fix` use the MCP loader,
differ and locator.

The hard rules do not change: a site is certain only when the receiver is rooted in an MCP client
import/alias and the tool name is a literal that matches the changed tool; a dynamic tool name,
dynamic arguments or an unrooted receiver is an ambiguity group, never a guess.

## Constraints carried in from the repo

- `CLAUDE.md` §1–2: execution decides; ambiguity is reported, never guessed.
- T2's `Site`/`SiteShape`/`AmbiguousGroup`/`LocateResult` and certainty policy; T3 edits `keyword`/
  `dict_key`/`attribute` spans; no new proposer rule unless the MCP shape needs one.
- T8a's `Change` records: `location.method="tool"`, `path=<tool>`, pointer under `#/tools/<tool>/...`.
- Offline: committed fixture repos; no MCP server, network, agent or model.

## Scope fence

Not this card: the TypeScript MCP locator, `tenon probe`/transport/agent, low-level
`send_request("tools/call", ...)` (unless the interview chooses it), output-schema dataflow, T9.
