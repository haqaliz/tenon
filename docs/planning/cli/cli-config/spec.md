# Spec: `cli-config` (M1.4 CLI)

- **Feature:** `cli`
- **PRD:** `docs/planning/cli/prd.md` (§ M7, Data Model)
- **Boundary:** resolve `tenon.toml` and CLI overrides into one `CliConfig`. No pipeline calls, no
  rendering, no I/O beyond reading the config file.

## Problem slice

Every command needs the same three answers before it can run: which SDK package and endpoint
mappings locate should use, what check command to prove with, and what level counts as success. The
answers can come from a repository file or flags, and flags must win without ambiguity.

## In-scope requirements

- `CliConfig`: `locate: LocateConfig`, `command: tuple[str, ...] = ()`,
  `require: ProofLevel = TESTS_PASSED`, `breaking_only: bool = False`. Frozen, slots.
- `load_cli_config(path) -> CliConfig`:
  - Parse the file once with `tomllib`; a parse error is a `ValueError` naming the file.
  - `[locate]` is required with `sdk_package`; delegate to the shipped `LocateConfig` validation.
  - `[tenon]` is optional. `command` must be an array of non-empty strings (a bare string is a named
    error); `require` must be `TESTS_PASSED` or `UNVERIFIED` (a future level names T7); `breaking_only`
    must be a bool. Unknown keys are ignored.
- `overrides(config, *, sdk_package, operations, fields, command, require, breaking_only)`:
  - `--operation`/`--field` are `KEY=VALUE` strings, split on the first `=`; a missing `=` or empty
    key/value is a `ValueError`. They merge over the config table, flags winning.
  - `--check` is one shell-like string split with `shlex.split`; no shell. Empty/blank is a
    `ValueError`.
  - `--require` replaces the config value; `--breaking-only/--no-breaking-only` replaces only when
    the flag was supplied (`None` means keep the config).
- `resolve_config_path(repo, explicit)`: `explicit` if supplied; otherwise `<repo>/tenon.toml` if it
  exists; otherwise `None` (defaults, with `sdk_package` required from a flag).
- Defaults when no file exists: empty mappings, no command, `TESTS_PASSED`, `breaking_only=False`.

## Out-of-scope

- Running detect/locate/propose/prove/pr.
- Rendering text or JSON.
- Global or home-directory config; environment-variable config.
- A config writer or schema migration.

## Acceptance criteria

- **AC1 — Defaults.** A minimal file with `[locate] sdk_package = "stripe"` loads with an empty
  command, `TESTS_PASSED`, `breaking_only=False`, and empty mappings.
- **AC2 — Full file.** `[locate.operations]`, `[locate.fields]` and `[tenon]` `command`,
  `require`, `breaking_only` all load and round-trip into `CliConfig`.
- **AC3 — Validation.** A missing `[locate]`, missing `sdk_package`, a non-array `command`, an empty
  command element, a non-bool `breaking_only`, and an unknown `require` value each raise `ValueError`
  with a message naming the key; the future-level message names T7.
- **AC4 — Overrides.** `--sdk-package` replaces; `--operation`/`--field` merge and win; `--check`
  replaces and is `shlex`-split; `--require` replaces; `--breaking-only` sets true and
  `--no-breaking-only` sets false over a true config.
- **AC5 — Bad overrides.** `--operation missing-equals`, `--operation =x`, `--check ""` raise
  `ValueError`.
- **AC6 — Path resolution.** Explicit wins; `<repo>/tenon.toml` is found when present; absent returns
  `None`; a missing `sdk_package` from both config and flags is a `ValueError`.
- **AC7 — No pipeline.** Importing and calling this aspect never imports or calls `diff`, `locate`,
  `propose`, `prove` or `write_pr`.

## Dependencies and sequencing

- Depends on `tenon.locate.LocateConfig` and `tenon.prove.ProofLevel` (shipped).
- First CLI aspect.

## Open questions / risks

- `tomllib` error messages differ by Python version; wrap them with a stable prefix and the path.
- `[tenon].command` as an array is strict; a user who writes a string gets a named error rather than
  a silent `shlex`.
- Unknown keys are ignored so a future `[tenon]` key does not break older CLIs.
