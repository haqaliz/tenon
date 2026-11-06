# Spec: `probe-client` (T8c)

- **Feature:** `mcp-probe`
- **PRD:** `docs/planning/mcp-probe/prd.md` (§ M2)
- **Boundary:** the stdio JSON-RPC client only. No tasks, agent, report or CLI.

## Problem slice

The probe needs a small, correct MCP client: spawn a local server, complete the handshake, list tools
with pagination, call a tool, and turn every wire failure into a named error without hanging or
guessing.

## In-scope requirements

- `McpStdioClient.start(command: Sequence[str], timeout: float)`; `initialize()`; `list_tools() ->
  tuple[dict, ...]`; `call_tool(name, arguments) -> dict`; `close()`.
- Spawn `subprocess.Popen(command, stdin/stdout/stderr=PIPE, text=True, bufsize=1,
  shell=False)`; no shell. UTF-8.
- JSON-RPC 2.0, newline-delimited: one object per line on stdin/stdout. An `id` counter; match
  responses by id; ignore notifications; answer an unexpected server request (`method` + `id`) with a
  `-32601` error.
- Handshake: `initialize` with `protocolVersion="2025-06-18"`, empty client capabilities,
  `clientInfo={"name":"tenon","version":<package version>}`; read the result; accept the server's
  returned protocol version; send `notifications/initialized`.
- `tools/list`: follow `nextCursor` until absent; return every tool object.
- `tools/call`: `params={"name": name, "arguments": arguments}`; return the result object. A
  JSON-RPC error response is a `ProbeError` the caller records per call; a transport/parse error is a
  `ProbeError` too.
- `ProbeError(reason, detail)`: stable reasons for spawn failure, closed pipe, timeout, invalid JSON,
  protocol error, server exit. The detail is capped.
- Per-request timeout via a `selectors`-based read or a reader thread; a timeout kills/closes the
  server. `close()` closes stdin, terminates then kills, and captures the stderr tail.
- No writes to the repo; the server process is the only side effect.

## Out-of-scope

- Tasks, the agent, the report, the CLI.
- HTTP/SSE, the official `mcp` SDK, sampling/roots/elicitation.
- A sandbox; the server is the user's code.

## Acceptance criteria

- **AC1 — Spawn/handshake.** The fake server starts; `initialize` returns its protocol version and
  server info; `notifications/initialized` is sent before `tools/list`.
- **AC2 — Tools.** `list_tools` follows a `nextCursor` page and returns both pages' tools.
- **AC3 — Call.** `call_tool("echo", {"text": "hi"})` returns the result; `call_tool("fail", ...)`
  returns an `isError` result (not a client error); an unknown tool's JSON-RPC error is a
  `ProbeError`.
- **AC4 — Errors.** A server that exits, a malformed line, a mismatched id and a timeout each raise a
  `ProbeError` with a stable reason and a capped detail; no hang.
- **AC5 — Server request.** An unknown server request is answered with `-32601`; the client keeps
  working.
- **AC6 — Close.** The server process is gone after `close()`; the stderr tail is available for a
  diagnostic.
- **AC7 — Offline.** The fake server is committed; no network.

## Dependencies and sequencing

- First; `probe-run` consumes the client.
- Stdlib only.

## Open questions / risks

- The MCP stdio framing is newline JSON; a server logging to stdout is a protocol error, not a
  retry.
- Protocol-version drift is a named connection error; the client does not implement old semantics.
- A reader thread vs `selectors`; either is allowed if the timeout is reliable on macOS/Linux.
