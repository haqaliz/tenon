# Spec: `receiver-config-all` (T12b)

- **Feature:** `receivers-rest`
- **PRD:** `docs/planning/receivers-rest/prd.md` (§ M1)
- **Boundary:** the `receivers` field on the three remaining configs and the TOML/bundle/CLI plumbing
  for all five. No scanner logic.

## In-scope requirements

- `LocateConfig` (Python), `TsLocateConfig` and `CSharpLocateConfig` gain
  `receivers: Mapping[str, str] = {}` with the T12a validation (non-empty strings, no whitespace at
  the edges or inside, read-only copies, named `ValueError`).
- `[locate.receivers]`, a bundle `locate.receivers` and a repeatable `--receiver KEY=VALUE` apply to
  every OpenAPI language (python, ts, rust, go, csharp); the T12a "ignored for other languages" rule
  is removed. A malformed entry/pair is a named error (CLI exit 2).
- A flag entry overrides a config entry with the same key; the no-config `--sdk-package` fallback
  passes the mapping for every language.
- Existing Rust/Go behavior and tests stay green; the tests that asserted the old "ignored" behavior
  are updated to the new contract.

## Out-of-scope

- Scanner evidence/chain logic (the other aspects).
- A global receiver type or return-type inference.

## Acceptance criteria

- **AC1 — Configs.** All three configs accept a valid mapping, store it read-only, and reject bad
  entries with a named error.
- **AC2 — TOML.** `[locate.receivers]` reaches every language's config; a bad entry is named.
- **AC3 — Bundle.** `locate.receivers` loads for every OpenAPI language; a non-object/non-string
  entry is a named bundle error.
- **AC4 — CLI.** `--receiver` reaches every language; a flag overrides a config key; a malformed pair
  is exit 2.
- **AC5 — Regression.** Rust/Go behavior and all prior tests stay green.
