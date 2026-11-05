# Spec: `cli-run` (M1.4 CLI)

- **Feature:** `cli`
- **PRD:** `docs/planning/cli/prd.md` (§ M1–M6, M11, M12)
- **Boundary:** the `argparse` surface, `check`/`fix` orchestration, the `main` entry point, the
  console script and `python -m tenon`. It composes shipped stages; it does not reimplement them.

## Problem slice

The stages exist and the report functions know how to present them. This aspect connects the two:
parse the user's intent, load the specs and config, run the stages in order, hand the results to the
report, and return the exit code. It is also the only place that constructs `GitGhRemote`, and only
when `--open-pr` is asked for.

## In-scope requirements

- `main(argv: Sequence[str] | None = None, *, remote: Remote | None = None) -> int`.
  - `argparse` with `prog="tenon"`, required subcommands `check` and `fix`.
  - Common: `repo`, `--old`, `--new`, `--config`, `--sdk-package`, `--operation` (append),
    `--field` (append), `--breaking-only/--no-breaking-only` (`BooleanOptionalAction`, default
    `None`), `--json`.
  - `fix` extra: `--check`, `--require` (custom type accepting only the two shipped levels),
    `--open-pr`, `--allow-unverified`.
  - `--version` and `--help` return 0; argparse usage errors return 2; no `sys.exit` inside `main`.
- **Config resolution.** `resolve_config_path(repo, args.config)`; load if present, otherwise
  defaults; apply `cli-config.overrides`. A missing `sdk_package` is a usage error (exit 2).
- **`check` flow.** `load(old)` → `load(new)` → `diff` → filter `breaking` → `locate` per change →
  `render_check_text/json` → `check_exit`.
- **`fix` flow.** Same detect/filter. Per change: `locate` → `propose` → `prove(proposal, repo,
  config.command)`. If `--open-pr`: `write_pr(proposal, proof, repo, remote=remote or
  GitGhRemote(), allow_unverified=args.allow_unverified, unanalyzed=diff_result.unanalyzed)`;
  otherwise `pr=None`. Render → `fix_exit`.
- **Errors.** `SpecRefusal` → kind `spec`, exit 2; config `ValueError`/`TOMLDecodeError` → `config`,
  exit 2; `FileNotFoundError`/`OSError` → `config`, exit 2; unexpected `Exception` → `internal`,
  exit 1. With `--json`, the error envelope goes to stdout; otherwise stderr. No traceback.
- **Entry points.** `src/tenon/cli/__init__.py` exports `main`; `src/tenon/__main__.py` calls
  `main()` under `SystemExit`; `pyproject.toml` adds `tenon = "tenon.cli:main"`.
- **Injection.** `remote` is optional and only used with `--open-pr`. Tests pass a fake; the real
  adapter is never constructed without the flag.

## Out-of-scope

- New pipeline stages or rules.
- Applying a diff to the checkout; merging.
- `tenon probe`, T6/T7/T8.
- A timeout flag, a model proposer flag, a release/version scheme beyond `--version`.

## Acceptance criteria

- **AC1 — Help and version.** `main(["--help"])`, `main(["check", "--help"])`,
  `main(["fix", "--help"])`, `main(["--version"])` return 0; no subcommand returns 2.
- **AC2 — Check happy path.** A fixture repo with one certain site: exit 1, text names the site;
  `--json` is one object with the expected keys; a clean repo with no site exits 0.
- **AC3 — Check unanalyzable.** A repo without the SDK import exits 1 and names `NO_SDK_IMPORT` in
  text and JSON.
- **AC4 — Fix local.** A passing check: exit 0, the diff and `Proof: TESTS_PASSED` are printed, the
  fixture checkout is byte-identical, and no PR code runs.
- **AC5 — Fix unverified.** No check command: `UNVERIFIED (NO_TESTS_FOUND)` and exit 1;
  `--require UNVERIFIED` exits 0; `--json` carries the cause.
- **AC6 — Fix open-pr.** A fake `write_pr` and remote are used; `TESTS_PASSED` → one `OPENED` result,
  exit 0; an `UNVERIFIED` proof without `--allow-unverified` makes no `write_pr` call and exits 1;
  with `--allow-unverified` and `--require UNVERIFIED`, the fake sees `allow_unverified=True` (the
  draft flag itself is T5's tested contract, not the CLI's).
- **AC7 — Config and overrides.** `[locate]`/`[tenon]` defaults apply; `--sdk-package`, `--operation`,
  `--check`, `--require` and `--breaking-only` override; a missing `tenon.toml` plus `--sdk-package`
  works; neither is exit 2.
- **AC8 — Bad input.** A bad TOML, a missing spec, a spec refusal and an unknown `--require` each
  exit 2 with a named message and no traceback; with `--json`, one error object on stdout.
- **AC9 — Module and console.** `python -m tenon --help` exits 0 as a subprocess; the
  `[project.scripts]` entry is present and `uv run tenon --help` is the smoke check.
- **AC10 — Offline and deterministic.** The suite makes no network call and constructs no
  `GitGhRemote` unless `--open-pr` is used; JSON is byte-stable across hash seeds.
- **AC11 — No checkout writes.** `fix` and `fix --open-pr` with a fake remote leave the fixture tree
  and `git status` unchanged; the writer's own isolation is already tested, not re-proven here.

## Dependencies and sequencing

- Depends on `cli-config`, `cli-report`, and all shipped stages.
- Land last.
- Use `tests/fixtures/repos/proof-basic` and a temporary copy with a `tenon.toml`; reuse the OLD/NEW
  spec pair from the proof tests, not a network fetch.

## Open questions / risks

- Per-change `locate` scans are slow on a large diff; `--breaking-only` is the only mitigation in
  this card.
- `fix --open-pr` with several proposals can open several PRs; a refusal after some opened is
  reported per result, with no rollback.
- `argparse` writes help/errors to stdout/stderr itself; `main` returns the code but does not
  reformat those messages.
- A real `tenon` console-script test depends on the installed entry point; the suite uses
  `python -m tenon` for the subprocess check and leaves `uv run tenon` as a manual smoke.
