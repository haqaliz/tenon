# PRD: Release v0.1.0 (consolidation)

- **Slug:** `release-v0.1.0`
- **Capability:** **Release/consolidation** — the post-T13 checkpoint
- **Milestone:** after T13; the original roadmap ends at T11
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

The repo has shipped T1–T13: change detection, five locators, patch proposals, the proof ladder, the
PR writer, MCP/probe, the benchmark corpus, the provider layer (app remote, bundles, local/installed
fan-out, the service), deployment/resilience, and receiver tracking — 2,527 tests, offline. But the
package is still `0.0.1`, there is no changelog, no runnable example, no release checklist and no
packaging check. A newcomer cannot tell what shipped or run a first success; an operator cannot see a
version.

This release slice consolidates the work as **v0.1.0**:
- bump the version and expose `tenon --version`;
- write a `CHANGELOG.md` covering every shipped capability and its known limits;
- add a runnable quickstart using the committed `proof-basic` fixture and an example bundle/spec pair;
- build the wheel/sdist and install the wheel into a clean venv, checking `tenon --version` and
  `tenon check --help`;
- add a release checklist (`docs/RELEASE.md`) and, after the merge, an annotated `v0.1.0` tag and a
  GitHub release.

No runtime behavior changes; the release is honest about the pre-1.0 limits.

**For whom:** the maintainer cutting the release, a newcomer running a first check/fix, an operator
checking the version, and a provider receiving a tagged bundle-capable tool.

## Goals & Success Metrics

1. **A version.** `pyproject.toml`/the wheel are `0.1.0`; `tenon --version` prints `tenon 0.1.0`.
2. **A changelog.** `CHANGELOG.md` (Keep a Changelog) lists the 0.1.0 Added/Changed/Fixed and known
   limits; it is the GitHub release body.
3. **A first success.** `examples/quickstart/` + `examples/README.md` run the check, fix and provider
   bundle on the committed fixture with copy-paste commands.
4. **A packaging check.** `uv build` succeeds; the wheel installs into a clean venv; `tenon
   --version`/`check --help` work there.
5. **A checklist.** `docs/RELEASE.md` covers version/lock/tests/build/install/tag/release/verify.
6. **Offline tests.** The version/changelog/example invariants are asserted; no network/PyPI.

## Requirements

### Must have

- **M1 — Version.** `pyproject.toml` `version = "0.1.0"` and `uv.lock` refreshed; the installed
  `tenonhq` metadata is `0.1.0`; `tenon --version` prints `tenon 0.1.0`.
- **M2 — Changelog.** `CHANGELOG.md` with an `Unreleased` section and `## [0.1.0] - 2026-11-13`:
  Added (core, MCP/probe/corpus, provider layer/service/deployment/resilience, Rust/Go/C#,
  receiver tracking), Changed, Fixed, and a Known limits summary. SemVer/pre-1.0 note.
- **M3 — Examples.** `examples/quickstart/` with `old.yaml`, `new.yaml` and `bundle.json` (the
  `proof-basic` `amount` -> `amount_cents` rename, `sdk_package: acme.client`, the check
  `["python3","-c","import acme.billing"]`); `examples/README.md` with the check, fix and
  `provider migrate` commands and expected output. The bundle loads via `load_bundle`.
- **M4 — Packaging.** A `docs/RELEASE.md` checklist and a local verification: `uv build`, a clean venv
  install of the wheel, `tenon --version`/`check --help`; the sdist/wheel names include 0.1.0.
- **M5 — Release.** After the PR merges: an annotated `v0.1.0` tag on master, a GitHub release whose
  body is the 0.1.0 changelog section, and the README version/changelog links.
- **M6 — Tests.** `pyproject` version, the changelog heading, the example bundle/specs, and the
  `--version` output (installed metadata) are asserted; the full suite stays green.

### Should have

- **S1 — One source of truth.** The version lives in `pyproject.toml`; no hard-coded duplicate.
- **S2 — Copy-paste commands.** The example commands work from the repo root with `uv run`.
- **S3 — Honest notes.** The changelog names the pre-1.0 limits (no 1.0 API promise; the service is
  self-hosted/Compose; pre-1.0).

### Nice to have

- **N1 — A docs site**; later.
- **N2 — PyPI publish/signing**; needs credentials; later.
- **N3 — A CI release workflow**; later.

## Risks & Open Questions

- **Installed metadata vs source.** `tenon --version` reads the installed distribution; after the
  version bump the env must be synced/reinstalled. The checklist says `uv sync`/clean install.
- **The tag/release are post-merge.** They are not in the PR; the maintainer creates them on master
  after the merge (this slice records the exact commands).
- **Example drift.** The fixture/spec pair can drift; a test loads the bundle and the specs.
- **Pre-1.0.** 0.1.0 explicitly does not promise API stability; the changelog says so.
- **Open question — should the GitHub release include the wheel?** Not in this slice; `uv build`
  artifacts are local. A later CI release can attach them.
- **Open question — should the version badge replace the status badge?** Add a version badge next to
  the status; keep the status list.

## Out of Scope

- PyPI publish, a docs site, CI release automation, new features/locators/providers.
- A 1.0 API-stability promise.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `release-version` | Version bump, lock, `--version`, `CHANGELOG.md`, `docs/RELEASE.md`, the version/changelog tests. No examples. |
| `release-examples` | `examples/quickstart`, `examples/README.md`, the example/bundle tests, README links. No version/tag. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The work shipped but is not packaged, discoverable or versioned. |
| User understanding | 🟢 | Maintainer/newcomer/operator/provider; the first-success commands are concrete. |
| Success metrics | 🟢 | Version, changelog, quickstart, build/install, checklist, tag/release. |
| Scope clarity | 🟢 | Consolidation only; no new runtime behavior. |
| Edge cases & risks | 🟡 | Metadata sync, example drift and post-merge tag steps are real; documented/tested. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Docs/config/examples + `uv build`; no new dependency. |
| Go-to-market | 🟢 | The first tagged, runnable release of the whole capability set. |

**Areas to strengthen before sharing:** the wheel is not published; the release is a tag/GitHub
release with local build verification. That is the honest 0.1.0, not a PyPI launch.

**The question I would want answered before greenlighting this:** *Does `tenon --version` show 0.1.0
from a clean install?* The answer this card records: the checklist builds the wheel in a clean venv
and checks it; the installed metadata is the single source, and the test asserts the synced value.
