# Spec: `probe-cli` (T8c)

- **Feature:** `mcp-probe`
- **PRD:** `docs/planning/mcp-probe/prd.md` (§ M1, M7)
- **Boundary:** the `tenon probe` command, dispatch, exit codes and end-to-end tests. No engine
  internals.

## Problem slice

The probe engine is only useful from the CLI. This aspect adds the third subcommand, parses the
user's server/agent/tasks inputs, renders the report, and maps outcomes to exit codes.

## In-scope requirements

- `tenon probe` subcommand in `main`:
  `--server-cmd CMD` (required), `--tasks PATH` (required), `--agent CMD` (required),
  `--timeout SECONDS` (default 30, positive), `--json`, `--help`.
  `CMD` strings are `shlex`-split, no shell.
- The probe command does not take `repo`/`--old`/`--new`; it is a separate parser branch.
- `main` dispatch: load tasks (ValueError -> exit 2), split commands, call `probe`, render text or
  JSON, return 0/1.
- Fatal errors (`ProbeError` connection/handshake/spawn, `AgentError` before any task, bad tasks,
  usage) -> a `{"error": {"kind": "probe", "reason", "message"}}` object on stdout with `--json`, or
  a stderr line; exit 2. A task failure is a report, exit 1.
- `--json` is one object; text is the report renderer. `--help`/no args behave like the other
  subcommands.
- The console script and `python -m tenon` include `probe`.
- Tests: the fake server/agent through the real CLI; pass exit 0; fail exit 1; bad tasks/server exit
  2; the JSON shape; the text; `--help`; the existing check/fix tests stay green.

## Out-of-scope

- The client/runner, HTTP/SSE, a model, a config file (`tenon.toml` is not extended for probe in this
  card).
- PR/proof/T9.

## Acceptance criteria

- **AC1 — Help/dispatch.** `main(["probe", "--help"])` returns 0; a missing required flag returns 2;
  `main([])` still returns 2.
- **AC2 — Pass.** A fake server/agent/tasks run exits 0; text names the tasks/tools; `--json` has the
  report shape.
- **AC3 — Fail.** A task with a tool error or a missing expectation exits 1; the report names it.
- **AC4 — Fatal.** A bad tasks file, a server that exits and a bad agent spawn each exit 2 with one
  error object under `--json`; no traceback.
- **AC5 — Existing.** The OpenAPI/MCP `check`/`fix` commands and all prior tests are unchanged.
- **AC6 — Offline.** No network; the fake server/agent are local subprocesses.
- **AC7 — Determinism.** The same fake observations produce byte-identical JSON.

## Dependencies and sequencing

- Depends on `probe-run`; last.

## Open questions / risks

- The probe reuses `main`'s `_fail`/error envelope; a task failure is not an error envelope, it is a
  report with exit 1.
- `--timeout` is per JSON-RPC request and per agent run; a slow server can fail a task.
- The CLI does not read `tenon.toml` for probe defaults in this card; flags only.
