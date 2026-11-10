# Spec: `go-integration` (T11b)

- **Feature:** `locator-go`
- **PRD:** `docs/planning/locator-go/prd.md` (§ M4–M6)
- **Boundary:** `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, `package_name`, docs, CLI/bundle
  tests. No scanner internals.

## Problem slice

The Go scanner is only usable if the shipped commands accept `go` and dispatch to it everywhere the
language selects a config type or a locator, including the optional package-name override.

## In-scope requirements

- `src/tenon/cli/config.py`: `LANGUAGES = ("python", "ts", "rust", "go")`; `CliConfig.language`
  literal; named errors say `python, ts, rust or go`; `load_cli_config`, `overrides` and the
  no-config fallback build `GoLocateConfig` for go via `LOCATE_TYPES`; `source=mcp` still requires
  `python`; `locate.package_name` is read for a Go config.
- `src/tenon/cli/main.py`: `--language` choices include `go`; `--package-name` is a common flag
  (used by Go, ignored otherwise); `_locate` uses `LOCATORS`; `check`/`fix` text/JSON and exits
  unchanged.
- `src/tenon/provider/bundle.py`: `LANGUAGES`, `MigrationBundle.language`, `a_locate` builds
  `GoLocateConfig` including `locate.package_name`; a go bundle with `source=mcp` or a bad root/
  package is a named error.
- Docs: README and ARCHITECTURE state `--language go`, the import-root/package config, the supported
  shapes and the limits (method chains, dot imports, reflection, multi-hop data flow).
- Tests: `tenon.toml language = "go"` with `package_name`; `--language go` on a fixture Go repo
  through `tenon check` and `tenon fix`; a Go provider bundle; invalid language/root/package and
  `mcp`+go errors; the existing python/ts/rust tests green. Offline.

## Out-of-scope

- Scanner/config changes; C#; a Go proof preset; new proof levels.
- MCP Go location; a hosted service.

## Acceptance criteria

- **AC1 — CLI.** `tenon check --language go --sdk-package <root> [--package-name <name>]` locates the
  fixture's sites; the text/JSON shape and exits match the other languages.
- **AC2 — Fix.** `tenon fix --language go` proposes/proves the same diff without writing the
  checkout; the proof commands are the user's.
- **AC3 — Config file.** `tenon.toml` `language = "go"` with `package_name` selects the Go config; a
  bad root/package is a named error; `mcp` + `go` is rejected.
- **AC4 — Bundle.** A bundle with `language: "go"` and `locate.package_name` loads and runs through
  `provider migrate`; a bad root/package or `mcp`+go is a named bundle error (exit 2).
- **AC5 — Dispatch.** The existing `LOCATE_TYPES`/`LOCATORS` registry drives go; no python/ts/rust
  behavior changes.
- **AC6 — Docs/regression.** README/ARCHITECTURE updated; all prior tests green.

## Dependencies and sequencing

- Depends on `go-locate`; last.

## Open questions / risks

- The fixture repo is intentionally small; real Go SDK layouts vary.
- A user can pass any proof command; no Go policy is added.
