# Spec: `rust-integration` (T11a)

- **Feature:** `locator-rust`
- **PRD:** `docs/planning/locator-rust/prd.md` (§ M4–M6)
- **Boundary:** `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, docs, CLI/bundle tests. No
  scanner internals.

## Problem slice

The Rust scanner is only usable if the shipped commands accept `rust` and dispatch to it everywhere
the language selects a config type or a locator.

## In-scope requirements

- `src/tenon/cli/config.py`: `LANGUAGES = ("python", "ts", "rust")`; `CliConfig.language` literal;
  named errors say `python, ts or rust`; `load_cli_config` and `overrides` build `RustLocateConfig`
  for `rust` (one dispatch table, no `if` chains); `source=mcp` still requires `python`.
- `src/tenon/cli/main.py`: `--language` choices include `rust`; the no-config `--sdk-package`
  fallback and `_locate` dispatch use the same table; `check`/`fix` text/JSON and exits unchanged.
- `src/tenon/provider/bundle.py`: `LANGUAGES`, `MigrationBundle.language`, `a_locate` build
  `RustLocateConfig`; a rust bundle with `source=mcp` is a named error.
- Docs: README and ARCHITECTURE state `--language rust`, the crate/mapping config, the supported
  shapes and the limits (methods/macros/re-exports).
- Tests: `tenon.toml language = "rust"`; `--language rust` on a fixture Rust repo through
  `tenon check` and `tenon fix`; a Rust provider bundle; invalid language/`mcp`+rust errors; the
  existing python/ts tests green. Offline.

## Out-of-scope

- Scanner/config changes; Go/C#; a Cargo proof preset; new proof levels.
- MCP Rust location; a hosted service.

## Acceptance criteria

- **AC1 — CLI.** `tenon check --language rust --sdk-package <crate>` locates the fixture's sites; the
  text/JSON shape and exits match the other languages.
- **AC2 — Fix.** `tenon fix --language rust` proposes/proves the same diff without writing the
  checkout; the proof commands are the user's.
- **AC3 — Config file.** `tenon.toml` `language = "rust"` selects the Rust config; a bad crate is a
  named error; `mcp` + `rust` is rejected.
- **AC4 — Bundle.** A bundle with `language: "rust"` loads and runs through `provider migrate`; a bad
  crate or `mcp`+rust is a named bundle error (exit 2).
- **AC5 — Dispatch.** One table drives the locate type and the locator for python/ts/rust; no
  python/ts behavior changes.
- **AC6 — Docs/regression.** README/ARCHITECTURE updated; all prior tests green.

## Dependencies and sequencing

- Depends on `rust-locate`; last.

## Open questions / risks

- The fixture repo is intentionally small; real Rust SDK layouts vary.
- A user can pass any proof command; no Cargo policy is added.
