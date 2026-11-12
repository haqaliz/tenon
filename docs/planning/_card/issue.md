# Card: release/v0.1.0

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** release
- **Capability:** **Release/consolidation** — the post-T13 checkpoint
- **Milestone:** after T13; the original roadmap ends at T11
- **State:** released v0.1.0 on 2026-11-13 (`CHANGELOG.md`, `docs/RELEASE.md`, annotated tag)
- **Branch:** `release/v0.1.0/aliz`
- **Worktree:** `.claude/worktrees/release-v0.1.0`

## Brief

The repo has shipped T1–T13: detection, five locators, proof, PR writer, provider bundles/local and
installed fan-out, a deployed service, and receiver tracking — 2,527 tests, offline. The package is
still `0.0.1`, there is no changelog, no runnable example and no packaging check.

This release slice:
- bumps the version and exposes `tenon --version`;
- writes a `CHANGELOG.md` (Keep a Changelog style) covering the shipped capabilities and their known
  limits;
- adds a runnable quickstart example (the committed proof-basic fixture + a bundle/spec pair) and an
  `examples/README.md`;
- builds the wheel/sdist and installs the wheel into a clean venv, checking the console script and
  `--version`;
- adds a release checklist (`docs/RELEASE.md`) and, if chosen, an annotated tag + GitHub release;
- updates the README/status surfaces to the release.

The hard rules do not change: no new runtime capability, no merge/default-branch behavior, no
secrets, offline checks only.

## Constraints carried in from the repo

- `pyproject.toml` is the version source; `_package_version()` reads the installed distribution.
- The committed fixtures (`tests/fixtures/repos/proof-basic`, specs) are the example base.
- `uv build`/a clean venv are local; no PyPI publish in this slice.
- The existing docs (`README`, `DEPLOYMENT`, `CAPABILITY_ROADMAP`) are the changelog source.

## Scope fence

Not this card: PyPI publish, a hosted docs site, new features, new locators/providers, version 1.0
semver guarantees unless chosen.
