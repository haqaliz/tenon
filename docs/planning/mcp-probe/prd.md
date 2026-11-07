# PRD: `tenon probe` (T8c)

- **Slug:** `mcp-probe`
- **Capability:** T8 in `docs/technical/CAPABILITY_ROADMAP.md` — **final slice, probe mode**
- **Milestone:** M2.3 in `docs/ROADMAP.md` (Phase 2), final slice
- **Status:** implemented 2026-11-07 (`src/tenon/probe/`, 1,436 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T8a/T8b answer "what changed in an MCP server, and where does my code call it?" The product's second
mode (`VISION.md` readiness mode) answers a different question: **can an agent actually use this MCP
server?** A server can publish a perfect `tools/list` and still have tools an agent cannot discover,
call, or recover from. Providers need a readiness report; consumers need a smoke test before wiring an
agent.

T8c adds `tenon probe`: connect to an MCP server over stdio, list its tools, run a set of tasks
through a **user-supplied agent command**, execute the agent's planned tool calls, and report which
tasks worked. No model ships: the agent is the user's own code, behind a documented JSON contract.
The probe is a readiness observation, not a proof level and not a PR.

The dangerous shortcuts are rejected here: calling a model inside Tenon, treating a tool list as
"working" without a call, letting a malformed agent plan pass, hiding a tool error, and reporting a
probe run as proof that a production integration is safe.

**For whom:** a provider checking an MCP server before publishing it, a developer smoke-testing a
server before wiring an agent, and the T8 milestone's lead-generation hook.

## Goals & Success Metrics

1. **One command.** `tenon probe --server-cmd CMD --tasks FILE --agent CMD [--json]` starts the MCP
   server, lists tools, runs every task, and reports.
2. **Honest task verdict.** A task passes only when the agent returned a valid plan, every planned
   call ran without an MCP error, and every expectation matched. A tool error or a malformed plan is
   a failed task, never a pass.
3. **No model, no network by Tenon.** The agent and server are user-supplied commands; Tenon speaks
   stdio JSON-RPC to the local server and writes a JSON request to the agent. No provider, key,
   remote call or bundled model.
4. **Offline tests.** A fake stdio MCP server and a fake agent are committed fixtures; the probe
   suite spawns them locally.
5. **Machine report.** `--json` is one byte-stable object; text is a short per-task report. Exit 0
   when every task worked, 1 when one failed, 2 on usage/connection/config errors.
6. **Standard library only.** A small JSON-RPC stdio client; no new dependency.

## User Personas & Scenarios

- **Provider.** Runs `tenon probe` against their server with an agent wrapper and a task file before
  publishing; fixes the tools the report says an agent could not use.
- **Developer.** Smoke-tests a third-party MCP server before adding it to an agent; sees the exact
  tool call that failed.
- **Reviewer.** The report lists the tools, the agent's plan, each call's result, and the failed
  expectation; no claim beyond what the local run showed.
- **T9 benchmark.** A probe report can later become an outcome datum, not a proof.

Scenario: a fake server exposes `echo` and `fail`. The agent plans `echo` for the "echo" task and
`fail` for the "fail" task. The first passes; the second fails with the server's `isError`; the probe
exits 1 and names the failed call. A malformed agent plan is a failed task with `AGENT_INVALID`.

## Requirements

### Must have

- **M1 — CLI.** `tenon probe` is a third subcommand alongside `check`/`fix`:
  `--server-cmd CMD` (required; `shlex`-split, no shell), `--tasks PATH` (required), `--agent CMD`
  (required), `--timeout SECONDS` (default 30, positive), `--json`. `--help` works; unknown/extra
  args are usage exit 2. The console script and `python -m tenon` include it.
- **M2 — MCP stdio client.** Spawn the server command with `shell=False`, pipes for stdin/stdout/
  stderr and text mode. Speak JSON-RPC 2.0 newline-delimited over stdio:
  - `initialize` with a supported `protocolVersion`, client capabilities and `clientInfo`; read the
    response; accept the server's returned protocol version;
  - `notifications/initialized` (no response);
  - `tools/list`, following `nextCursor` until absent;
  - `tools/call` with `name` and `arguments`;
  - match responses by `id`, ignore notifications, answer an unexpected server request with a
    JSON-RPC `-32601` error;
  - a per-request timeout; a closed pipe, a JSON error, a mismatched id or a timeout is
    `ProbeError`; close stdin and terminate the server on exit.
  - `stderr` is captured and capped for a connection/exit diagnostic.
- **M3 — Tasks.** `load_tasks(path) -> tuple[Task, ...]`: JSON `{"tasks": [...]}`; each task has a
  non-empty string `name` and `prompt`, and an optional `expect`:
  - `tools`: a list of tool names that must each be called;
  - `result_contains`: a string that must appear in at least one call's text result.
  Duplicate names, missing/blank fields, a non-list tasks value, a non-object expect and a non-string
  expectation are named `ValueError`s (exit 2). An empty task list is valid (the report says zero).
- **M4 — Agent contract.** The probe writes one JSON request to the agent's stdin:
  `{"task": <prompt>, "tools": [{"name", "description", "inputSchema"}, ...]}` and reads one JSON
  object from stdout: `{"calls": [{"tool": <name>, "arguments": <object>}, ...]}`. The agent is
  spawned per task with `shell=False`, the same timeout, and a capped stderr tail. A non-zero exit,
  invalid JSON, a missing/non-list `calls`, a non-string tool or non-object arguments is
  `AgentError` with a named reason. No model, key or provider is used.
- **M5 — Probe run.** Connect once, list tools, then per task: run the agent, execute each planned
  call in order against the same session, record the outcome, and evaluate the expectations. A call
  succeeds when the JSON-RPC response has no error and the MCP result does not set `isError: true`.
  A result's text is the concatenated `content` text entries, capped. A task passes only when the
  agent plan is valid, every call succeeded, and every expectation is met. A failed call does not
  stop later calls in the same task (the report shows the sequence); a failed task does not stop
  later tasks.
- **M6 — Report.** `ProbeReport(server, tools, tasks, summary)`:
  - server: the command as given, the negotiated protocol version, the server name/version if
    supplied;
  - tools: name, description (capped), input schema (as returned);
  - per task: name, prompt, `agent_ok`, the plan, each call `{tool, arguments, ok, error,
    result_excerpt}`, expectation details (`missing_tools`, `result_contains`), `ok`, and a named
    task error if any;
  - summary: tasks, ok, failed.
  `to_dict()`/`to_json()` byte-stable for the same observations; text is one line per task plus the
  tool count and the summary. No timestamps, durations or absolute temp paths.
- **M7 — Exit codes.** 0 when every task passed; 1 when at least one failed (including an agent or
  call failure); 2 on usage, a bad tasks file, a server connection/handshake failure or an agent
  spawn failure before any task. With `--json`, a fatal error is one `{"error": {...}}` object on
  stdout; otherwise a stderr line. Never a traceback.
- **M8 — No model / no remote.** Tenon itself makes no network call and loads no model; the server
  and agent are the user's local commands. The task file and report stay local.
- **M9 — Tests.** A fake stdio server (`initialize`, `tools/list` with pagination, `tools/call`
  `echo`/`fail`), a fake agent (valid plan, malformed plan, no calls), and tasks covering pass,
  failed call, missing expected tool, result substring, empty tasks, bad tasks file, server exit,
  timeout and a `--json` report. Offline.

### Should have

- **S1 — `--timeout`** applies per JSON-RPC request and per agent run; a timeout is a named failure.
- **S2 — Tool schema echo.** The tools list in the agent request keeps the server's `inputSchema` so
  an agent can plan valid arguments; the report keeps the same schema.

### Nice to have

- **N1 — HTTP/SSE transport** and the official `mcp` SDK; a later card.
- **N2 — An OpenAPI/API probe**; a later card.
- **N3 — Probe results as T9 corpus outcomes**; a later card.

## Data Model

```
Task(name, prompt, expect: Expectation | None)
Expectation(tools: tuple[str, ...], result_contains: str | None)

ProbeCall(tool, arguments, ok, error: str | None, result_excerpt: str)
TaskReport(name, prompt, agent_ok, plan: tuple[ProbeCall, ...] | None,
           calls: tuple[ProbeCall, ...], expectations: ExpectationReport,
           ok: bool, error: str | None)
ProbeReport(server: ServerInfo, tools: tuple[ToolInfo, ...],
            tasks: tuple[TaskReport, ...], summary: Summary)
```

`ProbeError` / `AgentError` are named exceptions with a stable `reason` and a capped detail. The
report is an observation; it has no proof level, PR or merge path.

## API Contract

```python
from tenon.probe import ProbeError, load_tasks, probe

tasks = load_tasks("tasks.json")
report = probe(
    server_cmd=["python", "server.py"],
    tasks=tasks,
    agent_cmd=["python", "agent.py"],
    timeout=30.0,
)
report.to_dict()   # byte-stable for the same observations
```

CLI:

```sh
tenon probe \
  --server-cmd "python tests/fixtures/mcp/probe_server.py" \
  --tasks tasks.json \
  --agent "python agent.py" \
  --json
```

No model, no HTTP, no PR.

## Technical Considerations

- **Why stdio and stdlib.** The local MCP server over stdio is the common developer/provider case and
  can be tested offline. The handshake is `initialize` → `notifications/initialized` → `tools/list` →
  `tools/call`; a small JSON-RPC client is enough. The official `mcp` SDK would pull
  pydantic/starlette/uvicorn/opentelemetry for one transport; HTTP/SSE is a later card.
- **Why the agent is a command.** Tenon ships no model and no key. The user's agent wrapper turns a
  task and tool list into a plan; the probe executes it. The contract is JSON in/out so any language
  or model CLI can implement it.
- **Why execute the plan in Tenon.** The probe must observe the actual tool call and result; letting
  the agent call the server itself would make the report unverifiable. The plan is data, the probe is
  the executor.
- **Why no timestamps.** The report is a reproducible observation of the local server/agent for the
  same inputs; wall-clock timing is not a readiness signal in this card.
- **Arbitrary code.** The server and agent are user commands, run without a shell, in the user's
  environment. The probe is not a sandbox; document it.
- **Protocol drift.** The client sends `2025-06-18` and accepts the server's version; a future spec
  change is a named follow-up. Unknown server requests are rejected, not ignored.
- **Tool pagination.** Follow `nextCursor` to the end; the report lists every tool.
- **Exit 2 vs 1.** A bad server/agent setup is a usage/connection error before a task; a tool error
  inside a running task is a failed task (exit 1). This keeps CI able to distinguish "broken probe"
  from "server has a broken tool".

## Risks & Open Questions

- **Wire format.** Real MCP stdio servers use newline-delimited JSON-RPC; the fake server pins the
  same. A server that writes logs to stdout corrupts the stream; the client reports a JSON error and
  exits 2 rather than guessing.
- **Protocol version.** A server that only supports an older version may reject `initialize`; the
  client accepts the returned version but does not implement old semantics. A named connection error
  tells the user.
- **Agent quality.** The task verdict is only as good as the user's agent and task expectations. The
  report says exactly which calls and expectations ran; it never calls a task "verified".
- **Server requests.** Sampling/roots/elicitation requests from the server are answered with
  `-32601`; a server that requires them fails the probe. Out of scope.
- **No HTTP/SSE.** A remote MCP server is not probeable in this card; a later transport card.
- **Arbitrary code.** The probe runs the user's server and agent; it is not a sandbox.
- **Open question — should a failed call stop the task?** No: the report shows every planned call in
  order; one failure fails the task but later calls still run. A later `--stop-on-error` can change it.
- **Open question — task expectations.** `tools` + `result_contains` is a small, useful set; richer
  JSON-schema assertions are a later card.

## Out of Scope

- HTTP/SSE transport, the official `mcp` SDK, remote servers.
- An OpenAPI/HTTP API probe.
- A built-in model/agent/provider/key.
- PR creation, proof levels, merges.
- T9 corpus/benchmark; T10/T11.
- Watch mode, sampling/roots/elicitation, resource/prompt probes (tools only).

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `probe-client` | The stdio JSON-RPC client: spawn, initialize, list tools, call tools, timeouts, errors, close. No tasks/agent/CLI. |
| `probe-run` | Tasks, the agent JSON contract, plan execution, expectation evaluation, the report. No subprocess transport details beyond the client seam. |
| `probe-cli` | `tenon probe` argparse, dispatch, text/JSON error envelopes, exit codes, fake end-to-end. No engine internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Readiness mode is named in VISION; a tool list alone is not "working". |
| User understanding | 🟢 | Provider and developer scenarios are concrete; the agent contract is explicit. |
| Success metrics | 🟢 | Task verdict rules, exit codes, offline fake server, byte-stable report. |
| Scope clarity | 🟢 | stdio/tools only; HTTP/API/model/PR excluded. |
| Edge cases & risks | 🟡 | Wire-format/log pollution, protocol drift and agent quality are documented limits. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Stdlib JSON-RPC + a fake server; no dependency. |
| Go-to-market | 🟢 | The provider-facing hook; a report a vendor can act on. |

**Areas to strengthen before sharing:** the agent contract is a new public surface; a user must write
a wrapper. The first docs/examples should include a minimal fake agent and a one-line real wrapper.

**The question I would want answered before greenlighting this:** *If the user's agent is weak, the
probe reports failures that are the agent's fault, not the server's. Does that make the readiness
report misleading?* The answer this card records: the report shows the plan, every call and the
expectations, and says "worked" for this run, not "usable". The brand is honest observation, not a
certification.
