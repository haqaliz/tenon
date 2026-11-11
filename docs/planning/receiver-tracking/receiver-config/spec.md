# Spec: `receiver-config` (T12a)

- **Feature:** `receiver-tracking`
- **PRD:** `docs/planning/receiver-tracking/prd.md` (§ M1)
- **Boundary:** the `receivers` mapping on the Rust/Go configs and its `tenon.toml`, bundle and CLI
  plumbing. No scanner logic.

## Problem slice

The scanners need a provider-authored map from a factory/constructor expression to a type chain, and
the operator needs to supply it in the in-memory config, a TOML file, a bundle or a CLI flag.

## In-scope requirements

- `RustLocateConfig` and `GoLocateConfig` gain `receivers: Mapping[str, str] = {}`, stored as a
  read-only proxy. Both key and value are non-empty strings with no whitespace; a bad entry is a
  named `ValueError`.
- `tenon.toml`: `[locate.receivers]` is read for a rust/go config and passed to the locate type; it
  is ignored for the other languages.
- `tenon provider migrate` bundle: `locate.receivers` is an object of strings, passed for rust/go; a
  non-object/non-string entry is a named bundle error.
- CLI `check`/`fix`: `--receiver KEY=VALUE` is repeatable; entries merge over the config (a flag
  wins on the same key); a malformed pair is a named error.
- The no-config `--sdk-package` fallback passes the flag map to a rust/go config.
- Export/typing: the mapping is on the two config types only; no change to `LocateConfig`/
  `TsLocateConfig`/`CSharpLocateConfig` in this slice.

## Out-of-scope

- Scanner evidence and chain logic (the other aspects).
- T12b language configs; a global `receivers` field on every config.

## Acceptance criteria

- **AC1 — Config.** A valid mapping loads read-only; a blank/whitespace key or value is a named
  `ValueError`.
- **AC2 — TOML.** `[locate.receivers]` reaches the rust/go config; a non-string entry is named.
- **AC3 — Bundle.** `locate.receivers` loads for rust/go; a non-object/non-string entry is a named
  bundle error (exit 2).
- **AC4 — CLI.** Repeatable `--receiver` reaches the config; a flag overrides a config key; a
  malformed pair is a named error; other languages ignore the flag.
- **AC5 — Fallback.** `--sdk-package` with `--language rust|go` and `--receiver` builds the mapping.
- **AC6 — Regression.** All prior tests green.

## Dependencies and sequencing

- First; `rust-receivers`/`go-receivers` consume it.
- Reuses `a_pairs`-style parsing, the config dispatch table and the bundle mapping helper.

## Open questions / risks

- The mapping is per language; a bundle for another language with the key is ignored (consistent
  with `package_name`).
- Keys are matched by the scanners; this aspect only validates shape.
