# Card: feat/provider-fanout

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer and GitHub App (hosted)** — third slice: **local multi-repo
  fan-out** (`docs/technical/CAPABILITY_ROADMAP.md:16`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), third slice
- **State:** shipped 2026-11-09 (`src/tenon/provider/repos.py`, CLI; 1,774 tests)
- **Branch:** `feat/provider-fanout/aliz`
- **Worktree:** `.claude/worktrees/feat-provider-fanout`

## Brief

T10b runs one migration bundle against one repo. A provider with several customers needs to run the
same bundle across many local checkouts, open a PR per repo, and see which repos passed — without a
service, database or webhook yet.

T10c adds `tenon provider migrate --repos FILE` (alongside the existing single positional repo):
- the file lists local checkout paths, one per line, relative to the file;
- the bundle is loaded once, the pipeline runs sequentially per repo, and `--open-pr` opens one PR
  per repo through `gh` or the T10a app remote;
- the report is per repo (text) or a provider fan-out JSON envelope; the exit is 0 when every repo
  meets the requirement and every requested PR opened, 1 when any repo failed, 2 on usage/bundle/list
  errors;
- a missing/invalid repo is a per-repo failure, not an abort; all repos are attempted by default.

Installed/hosted fan-out (GitHub App installation discovery, webhooks, a database, deployment) is
T10d. No service in this slice.

The hard rules do not change: the same bundle/pipeline/guardrails per repo; no merge/default
branch/force; no provider branding; the bundle is trusted local input, not a sandbox; the order is
deterministic and the JSON byte-stable.

## Constraints carried in from the repo

- T10b's `MigrationBundle`/`load_bundle`, `_fix_results`, `_remote` and the provider envelope are the
  seams to reuse; no new pipeline.
- T5/T10a's PR gate and guardrails apply per repo.
- `CLAUDE.md` §1–5: execution decides, honest levels, no merge/default branch, no egress.
- Offline tests: fixture repo copies and bundles; no network/live GitHub.

## Scope fence

Not this card: installed/hosted fan-out, webhooks, a database, deployment, provider branding, T11.
