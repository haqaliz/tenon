# Spec: `probe-run` (T8c)

- **Feature:** `mcp-probe`
- **PRD:** `docs/planning/mcp-probe/prd.md` (§ M3–M6)
- **Boundary:** tasks, the agent contract, plan execution, expectations and the report. No CLI, no
  transport internals.

## Problem slice

The client can talk to a server; the probe must turn a task file and a user-supplied agent into an
honest per-task verdict and a report that shows exactly what happened.

## In-scope requirements

- `Task(name, prompt, expect: Expectation | None)`; `Expectation(tools: tuple[str, ...],
  result_contains: str | None)`; `load_tasks(path)`.
- JSON `{"tasks": [...]}`; each task has non-empty string `name`/`prompt`; `expect` optional with
  `tools` (list of non-empty strings) and `result_contains` (non-empty string). Duplicate names,
  missing/blank fields, non-object expect, non-list tools/strings are `ValueError`s.
- `run_agent(command, request, timeout) -> tuple[PlanCall, ...]`:
  - The request `{"task": prompt, "tools": [{"name", "description", "inputSchema"}, ...]}` on stdin.
  - The response `{"calls": [{"tool": name, "arguments": object}, ...]}`; validate each call; a
    non-zero exit, invalid JSON, a missing/non-list `calls`, a non-string tool or non-object
    arguments is `AgentError(reason, detail)`.
- `probe(server_cmd, tasks, agent_cmd, timeout) -> ProbeReport`:
  - Start the client; list tools; keep the server info/protocol version.
  - Per task: run the agent; execute each planned call in order; record `ok`/`error`/result excerpt;
    evaluate expectations; build a `TaskReport`. A failed call does not stop later calls; a failed
    task does not stop later tasks.
  - A call succeeds only when the JSON-RPC response has no error and the MCP result has no
    `isError: true`; the result text is the concatenated `content` text entries, capped.
  - A task passes only when the agent plan is valid, every call succeeded, and every expectation is
    met.
  - Close the client on every path.
- `ProbeReport(server, tools, tasks, summary)` with `to_dict()`/`to_json()` byte-stable and a text
  renderer. No timestamps, durations or temp paths.
- `ProbeError`/`AgentError` with stable reasons and capped details.
- Export `probe`, `load_tasks`, `ProbeError`, `AgentError`, the report/task types from
  `tenon.probe`.

## Out-of-scope

- The stdio client internals, CLI, HTTP/SSE, a model.
- PR/proof levels; T9 corpus.
- Richer expectations (JSON schema assertions).

## Acceptance criteria

- **AC1 — Tasks.** A valid file loads; every malformed shape is a `ValueError` naming the task/key.
- **AC2 — Agent.** A valid plan is returned; a bad exit/JSON/shape is `AgentError`; the request
  carries the task and the tools with their schemas.
- **AC3 — Pass.** A task whose plan calls `echo` and whose expectation matches passes; the report
  has the call/result.
- **AC4 — Fail.** A task calling `fail` fails on `isError`; a missing expected tool fails with
  `missing_tools`; a missing result substring fails; later calls/tasks still run.
- **AC5 — Empty.** An empty task list is valid; summary zeros.
- **AC6 — Server error.** A connection/handshake failure is a `ProbeError` before any task.
- **AC7 — Report.** The JSON has the exact shape; same observations → byte-identical; text is one
  line per task + the summary; no timestamps/paths.
- **AC8 — Close.** The server is closed on success and on a failure.

## Dependencies and sequencing

- Depends on `probe-client`; before `probe-cli`.
- The fake server/agent fixtures are shared with the CLI tests.

## Open questions / risks

- The report is an observation of the user's agent; it is not a certification.
- A failed call is recorded and later calls still run; `--stop-on-error` is later.
- The agent request includes the server's input schemas; a huge schema is capped only in the report,
  not in the request.
