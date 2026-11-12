# Spec: `release-version` (v0.1.0)

- **Feature:** `release-v0.1.0`
- **PRD:** `docs/planning/release-v0.1.0/prd.md` (§ M1, M2, M4–M6)
- **Boundary:** the version/lock, `--version`, `CHANGELOG.md`, `docs/RELEASE.md`, the release-check
  script and their tests. No examples.

## In-scope requirements

- `pyproject.toml` `version = "0.1.0"`; `uv lock`/`uv sync` so the installed `tenonhq` metadata is
  0.1.0; `tenon --version` prints `tenon 0.1.0`.
- `CHANGELOG.md` (Keep a Changelog, SemVer, a pre-1.0 note): `Unreleased` plus
  `[0.1.0] - 2026-11-13` with Added/Changed/Fixed/Known limits covering T1–T13.
- `docs/RELEASE.md`: the checklist (tests, sync, version, build, clean-venv install, changelog, tag,
  GitHub release, verify) and the exact commands.
- `scripts/release_check.sh`: a repeatable local check (`uv sync`, pytest, `uv build`, a temp venv
  install of the wheel, `tenon --version`/`check --help`, cleanup) with `set -euo pipefail`.
- Tests: the pyproject version, the changelog heading, the installed `--version` output, and the
  script's executable/shebang; the full suite green.

## Out-of-scope

- The example files, the tag/GitHub release (post-merge), PyPI.

## Acceptance criteria

- **AC1 — Version.** pyproject/lock/metadata are 0.1.0; `tenon --version` is `tenon 0.1.0`.
- **AC2 — Changelog.** The 0.1.0 section exists, lists the shipped capabilities/fixes and the known
  limits, and is suitable as the release body.
- **AC3 — Checklist.** `docs/RELEASE.md` covers every step with copy-paste commands.
- **AC4 — Script.** `scripts/release_check.sh` is executable and runs the build/install smoke.
- **AC5 — Tests/regression.** The version/changelog tests pass; all prior tests stay green.
