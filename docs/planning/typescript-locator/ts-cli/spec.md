# Spec: `ts-cli` (T6)

- **Feature:** `typescript-locator`
- **PRD:** `docs/planning/typescript-locator/prd.md` (§ M12)
- **Boundary:** the CLI language switch and dispatch. No new locator logic, no new proof logic.

## Problem slice

A locator nobody can reach is not shipped. The CLI already owns config, `check`/`fix` and exit codes;
this aspect adds the language dimension without duplicating the pipeline.

## In-scope requirements

- `CliConfig` adds `language: Literal["python", "ts"]` (default `"python"`); `locate` becomes
  `LocateConfig | TsLocateConfig`.
- `load_cli_config(path, language: str | None = None)`:
  - `[locate] language` (`"python"` or `"ts"`) is the default; the `language` argument overrides it.
  - For `python`, build `LocateConfig` (the shipped validation).
  - For `ts`, build `TsLocateConfig` (npm package validation; same `operations`/`fields` tables).
  - `[tenon]` keys are unchanged; an unknown language is a `ValueError`.
- `overrides(...)` takes `language: str | None`; a language change rebuilds the config type. If the
  existing package is invalid for the new language and no `--sdk-package` is given, raise a named
  `ValueError`; the CLI maps it to exit 2.
- `main` adds `--language python|ts` to both subcommands (default `None` = use the file). Pass it to
  `load_cli_config` and `overrides`.
- `check`/`fix` dispatch: `locate_ts(change, repo, config.locate)` when `config.language == "ts"`,
  otherwise `locate(...)`. `propose`, `prove`, `write_pr` are untouched.
- Tests:
  - `check --language ts` on a TS fixture: exit 1, text names the site, JSON has the same envelope.
  - `[locate] language = "ts"` works without the flag; `--language python` overrides it.
  - A Python repo still exits 1/0 as before (no regression).
  - `fix --language ts` with a monkeypatched `prove` returning `TESTS_PASSED`: the diff is rendered,
    `locate_ts` ran, the checkout is unchanged. T4's real proof is unchanged and tested separately.
  - An invalid package/language combination exits 2 with a named message, no traceback.
  - `tenon.toml` `[locate] language` and `[locate.operations]` work together.

## Out-of-scope

- New proof behavior, `node_modules` copy policy, JSX props, tsconfig aliases.
- `tenon probe`, T7 levels.
- A separate `tenon check-ts` command.

## Acceptance criteria

- **AC1 — Default.** No flag and no `language` key → Python, all existing CLI tests green.
- **AC2 — Config.** `[locate] language = "ts"` loads a `TsLocateConfig`; `--language` overrides;
  `[locate.operations]`/`[locate.fields]` still apply.
- **AC3 — Check.** A TS fixture with a certain site exits 1; text and JSON name the site; a clean TS
  repo exits 0.
- **AC4 — Fix.** The TS config reaches `locate_ts`; `propose` produces the diff; a faked
  `TESTS_PASSED` proof renders; the check command is passed through unchanged.
- **AC5 — Errors.** An invalid language, an npm-invalid package with `--language ts`, and a missing
  package exit 2 with a named message; `--json` emits the error envelope.
- **AC6 — Offline.** No Node/`gh`/network call in the CLI tests; the TS analysis is pure Python.

## Dependencies and sequencing

- Depends on `ts-locate` and the shipped CLI.
- Last.

## Open questions / risks

- The `CliConfig` type union touches the T5-era tests that pin `__all__`/fields; update them
  deliberately.
- A real TS `fix` with `npm test` still hits T4's `node_modules` copy policy; documented, not solved.
- `--language ts` with a `tenon.toml` written for Python needs `--sdk-package` or a file edit; the
  error names the mismatch.
