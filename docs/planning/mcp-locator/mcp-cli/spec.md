# Spec: `mcp-cli` (T8b)

- **Feature:** `mcp-locator`
- **PRD:** `docs/planning/mcp-locator/prd.md` (§ M9)
- **Boundary:** the CLI source switch and dispatch. No scanner/locator internals, no probe.

## Problem slice

The MCP diff and locator exist; the CLI still only reads OpenAPI. This aspect adds `--source mcp` and
`[locate] source`, selects the MCP loader/differ/locator, and keeps every downstream stage unchanged.

## In-scope requirements

- `CliConfig.source: Literal["openapi", "mcp"] = "openapi"`; `locate` union adds `McpLocateConfig`.
- `[locate] source` in `tenon.toml` (default `openapi`); `--source openapi|mcp` on both subcommands.
- `load_cli_config(path, language=None, source=None)`:
  - `openapi`: the shipped `python`/`ts` config branch.
  - `mcp`: `language` must be `python` (a named `ValueError` otherwise); build
    `McpLocateConfig(client_package=section.get("sdk_package", "mcp"))`; `operations`/`fields` are
    ignored or validated as empty? Accept and ignore them for now; the tool name comes from the
    change.
- `overrides` gains `source`; a source change rebuilds the config; an invalid combination is a
  `ValueError` -> exit 2.
- `main`: `--source`; `_config`; `_diff_and_filter` chooses `load`/`diff` (openapi) or
  `load_mcp`/`diff_mcp` (mcp); `_locate` chooses `locate`/`locate_ts` or `locate_mcp`; the
  `unanalyzed` from `diff_mcp` reaches `write_pr`.
- `check`/`fix` output/proof/PR paths unchanged; the MCP `Change` records flow through T3/T4/T5.
- Tests: a fixture repo with an `async with ClientSession` call; `check --source mcp` exits 1 and
  names the argument key; `[locate] source = "mcp"` works; `--language ts --source mcp` exits 2;
  `fix --source mcp` with a monkeypatched `prove_plan` renders the diff and exits 0; the existing
  OpenAPI paths stay green.

## Out-of-scope

- The scanner/locator, TS MCP, probe, low-level `send_request`.
- A new proof or PR behavior.

## Acceptance criteria

- **AC1 — Default.** No `source`/flag → openapi; all existing CLI tests green.
- **AC2 — Config.** `[locate] source = "mcp"` builds `McpLocateConfig`; `sdk_package` defaults to
  `mcp`; `--source` overrides; an unknown source is exit 2.
- **AC3 — Check.** `check --source mcp` on the fixture exits 1; text/JSON name the tool/argument;
  a clean MCP change exits 0.
- **AC4 — Fix.** `fix --source mcp` calls `locate_mcp`/`propose`; a monkeypatched `prove_plan`
  returning `TESTS_PASSED` renders the diff and exits 0; the fixture is unchanged.
- **AC5 — Validation.** `language=ts` + `source=mcp` is a named exit-2 error; a missing config with
  `--source mcp` and no `--sdk-package` uses `mcp` or names the error.
- **AC6 — Offline.** No MCP server/network/agent; the scanner is static.

## Dependencies and sequencing

- Depends on `mcp-locate` and the shipped CLI.
- Last.

## Open questions / risks

- The `[locate] operations`/`fields` tables are OpenAPI-specific; MCP ignores them. A later card can
  use them for custom client methods.
- The `source` + `language` matrix is small now (openapi×python/ts, mcp×python); a TS MCP locator
  extends it.
- The CLI `fix` proof for an MCP repo still depends on the user's check command and T4's copy; no
  new proof logic.
