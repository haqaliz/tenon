# Card: feat/mcp-probe

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T8 MCP diffs and probe mode** — final slice: **`tenon probe`**
  (`docs/technical/CAPABILITY_ROADMAP.md:14`)
- **Milestone:** M2.3 (`docs/ROADMAP.md`), final slice
- **Branch:** `feat/mcp-probe/aliz`
- **Worktree:** `.claude/worktrees/feat-mcp-probe`

## Brief

T8a/T8b diff MCP tools and locate their call sites. The product's second mode is readiness: point
Tenon at an MCP server, run tasks through a user-supplied agent, and report what actually worked.

T8c adds `tenon probe`: start an MCP server over stdio with a small stdlib JSON-RPC client, list its
tools, run each task through `--agent CMD` (a JSON request in, a JSON plan out), execute the planned
`tools/call` requests, evaluate the task expectations, and print a text or byte-stable JSON report.
Exit 0 when every task worked, 1 when one failed, 2 on usage/connection/config errors.

No model ships. Tenon makes no network call; the server and agent are the user's local commands. The
report is an observation, not a proof level or a PR.

## Constraints carried in from the repo

- `CLAUDE.md` §1–2: execution decides; no "verified" claim without a check. The probe says "worked
  in this run", not "usable".
- `CLAUDE.md` §3: machine-readable sources; the probe reads the live `tools/list`, not prose.
- `CLAUDE.md` §4: no code egress by default; no model/provider/key in the probe.
- `VISION.md` readiness mode: an agent runs against the server; the report is the lead-gen hook.
- Offline: a fake stdio server and fake agent are committed fixtures; no network.
- No new dependency: stdlib `json`/`subprocess`/`selectors`.

## Scope fence

Not this card: HTTP/SSE, the official `mcp` SDK, an OpenAPI/API probe, a built-in model, PR/proof,
T9 corpus. Those are later cards.
