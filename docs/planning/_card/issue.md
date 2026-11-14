# Card: release/v0.2.0

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** release
- **Capability:** **Release/consolidation** — v0.2.0
- **Milestone:** after T12d; the second tagged release
- **State:** v0.2.0 shipped 2026-11-14 (`CHANGELOG.md`, `docs/RELEASE.md`, annotated tag)
- **Branch:** `release/v0.2.0/aliz`
- **Worktree:** `.claude/worktrees/release-v0.2.0`

## Brief

Since v0.1.0 the repo shipped three `Unreleased` features: webhook-triggered runs (T10f),
annotated return-type receiver inference (T12c) and typed-parameter receiver inference (T12d). This
release moves them into `0.2.0`, bumps the package, runs the release check (tests, wheel/sdist,
clean-venv install), and publishes an annotated `v0.2.0` tag and GitHub release.

No new runtime behavior; no PyPI publication; the service stays self-hosted.

## Scope fence

Not this card: new features, CI/PyPI publication, cross-file inference, a hosted deployment.
