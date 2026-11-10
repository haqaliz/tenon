# Spec: `csharp-integration` (T11c)

- **Feature:** `locator-csharp`
- **PRD:** `docs/planning/locator-csharp/prd.md` (§ M4–M6)
- **Boundary:** `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, docs, CLI/bundle tests. No
  scanner internals.

## Problem slice

The C# scanner is only usable if the shipped commands accept `csharp` and dispatch to it everywhere
the language selects a config type or a locator.

## In-scope requirements

- `src/tenon/cli/config.py`: `LANGUAGES = ("python", "ts", "rust", "go", "csharp")`;
  `CliConfig.language` literal; named errors say `python, ts, rust, go or csharp`;
  `load_cli_config`, `overrides` and the no-config fallback build `CSharpLocateConfig` for csharp via
  `LOCATE_TYPES`; `source=mcp` still requires `python`.
- `src/tenon/cli/main.py`: `--language` choices include `csharp`; `_locate` uses `LOCATORS`;
  `check`/`fix` text/JSON and exits unchanged.
- `src/tenon/provider/bundle.py`: `LANGUAGES`, `MigrationBundle.language`, `a_locate` builds
  `CSharpLocateConfig`; a csharp bundle with `source=mcp` or a bad namespace is a named error.
- Docs: README and ARCHITECTURE state `--language csharp`, the namespace/mapping config, the
  supported shapes and the limits (fluent chains, `using static`, `dynamic`, reflection, multi-hop
  initializer flow).
- Tests: `tenon.toml language = "csharp"`; `--language csharp` on a fixture C# repo through
  `tenon check` and `tenon fix`; a C# provider bundle; invalid language/namespace and `mcp`+csharp
  errors; the existing python/ts/rust/go tests green. Offline.

## Out-of-scope

- Scanner/config changes; a .NET proof preset; new proof levels.
- MCP C# location; a hosted service.

## Acceptance criteria

- **AC1 — CLI.** `tenon check --language csharp --sdk-package <namespace>` locates the fixture's
  sites; the text/JSON shape and exits match the other languages.
- **AC2 — Fix.** `tenon fix --language csharp` proposes/proves the same diff without writing the
  checkout; the proof commands are the user's.
- **AC3 — Config file.** `tenon.toml` `language = "csharp"` selects the C# config; a bad namespace is
  a named error; `mcp` + `csharp` is rejected.
- **AC4 — Bundle.** A bundle with `language: "csharp"` loads and runs through `provider migrate`; a
  bad namespace or `mcp`+csharp is a named bundle error (exit 2).
- **AC5 — Dispatch.** The existing `LOCATE_TYPES`/`LOCATORS` registry drives csharp; no
  python/ts/rust/go behavior changes.
- **AC6 — Docs/regression.** README/ARCHITECTURE updated; all prior tests green.

## Dependencies and sequencing

- Depends on `csharp-locate`; last.

## Open questions / risks

- The fixture repo is intentionally small; real C# SDK layouts vary.
- A user can pass any proof command; no .NET policy is added.
