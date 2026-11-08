# PRD: Provider local fan-out (T10c)

- **Slug:** `provider-fanout`
- **Capability:** T10 in `docs/technical/CAPABILITY_ROADMAP.md` — **third slice, local multi-repo fan-out**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, third slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T10b runs one migration bundle against one repo. A provider with several customers needs to run the
same bundle across many local checkouts, open a PR per repo, and see which repos passed — without a
service, database or webhook yet. Today that means a shell loop, a hand-written summary and no
machine-readable per-repo result.

T10c adds `tenon provider migrate --repos FILE` (alongside the existing single positional repo): the
file lists local checkouts, one per line; the bundle is loaded once; the shipped pipeline runs
sequentially per repo; `--open-pr` opens one PR per repo through `gh` or the T10a app remote; the
report is per repo (text or a fan-out JSON envelope). A missing/invalid repo is a per-repo failure,
not an abort; all repos are attempted.

Installed/hosted fan-out (GitHub App installation discovery, webhooks, a database, deployment) is
T10d. This slice is a local orchestration of the proven T10b/T5 path, not a service.

The dangerous shortcuts are rejected here: inventing a success for a repo that did not run, aborting
the whole fan-out on one bad path, counting a local check as a merge, and opening a PR below the
required proof level.

**For whom:** a provider running a migration across customer checkouts, a self-hoster, the customer
reviewing each PR, and T10d's installed fan-out.

## Goals & Success Metrics

1. **One list, one bundle.** `--repos FILE` lists local paths, one per line (blank lines and `#`
   comments ignored), resolved relative to the file; the bundle is loaded once.
2. **One PR per repo.** `--open-pr` opens a PR per repo with the same T5/T10a guardrails; the remote
   is constructed once and reused.
3. **Per-repo honesty.** Each repo has its own results, proof levels and exit; a missing/invalid repo
   is a named per-repo failure; a failed repo does not stop the others.
4. **A fan-out report.** Text is one block per repo plus a summary; JSON is a fan-out envelope with
   `provider`, `migration`, `repos:[{repo, results, summary, exit, error}]` and an overall summary.
5. **Exit codes.** 0 when every repo meets the requirement and every requested PR opened; 1 when any
   repo failed; 2 on usage/bundle/repos-file/global spec errors.
6. **No service.** No webhooks, installation discovery, database or deployment.

## User Personas & Scenarios

- **Provider.** Writes `repos.txt` (one checkout per line) next to the bundle, runs
  `tenon provider migrate --bundle ... --repos repos.txt --open-pr --remote app`; sees 48 passed,
  2 failed with named errors.
- **Self-hoster.** Uses `gh` for a local trial over three checkouts; no app key.
- **Customer/reviewer.** Gets the normal T5 PR per repo; the report is the provider's, not the PR's.
- **T10d.** Replaces the local list with installed repos from the app API; the per-repo result/report
  shape stays.

Scenario: two copies of the proof-basic repo; one bundle; both pass → exit 0, two `TESTS_PASSED`
results, two PRs with the fake remote. One path is a missing directory → that repo has
`error: not a directory`, the other still runs; the summary is 1 passed, 1 failed; exit 1.

## Requirements

### Must have

- **M1 — Repo list.** `--repos FILE`: UTF-8 text, one local path per line; blank lines and lines whose
  stripped form starts with `#` are ignored; paths are `expanduser`ed and resolved relative to the
  file's parent; a missing/unreadable file, a non-file, or an empty list is a `ValueError` (exit 2).
  The single positional `<repo>` and `--repos` are mutually exclusive; exactly one is required.
- **M2 — Fan-out.** Load the bundle and build the `CliConfig` once. Construct the remote once when
  `--open-pr` (gh/app). For each repo in file order: if the path is not a directory, record a
  per-repo failure `not a directory` and continue; otherwise run the shipped `_fix_results` with the
  bundle's specs/config and the same `--check`/`--require` overrides; collect the changes/results and
  the `fix_exit`.
- **M3 — Report.** Text: `repo: <path>` then the fix report (or `error: ...`), then a summary
  `repos: N, passed: X, failed: Y`. JSON:
  `{"command":"provider","provider":...,"migration":...,
  "repos":[{"repo":..., "results":[<fix items>], "summary":<fix summary>, "exit":0|1,
  "error":null|"..."}], "summary":{"repos":N,"passed":X,"failed":Y}}`; byte-stable.
- **M4 — Exit.** 0 iff every repo exit is 0; 1 if any repo exit is 1; 2 on usage/bundle/repos-file/
  global spec/config errors. A global spec refusal aborts before/at the first repo; the bundle's
  specs are shared.
- **M5 — PR/remote.** `--open-pr` per repo; the same T5 required-level gate, dirty-tree/default-
  branch/branch-exists refusals and no-merge stance; the app flags/env and `--allow-below-required`
  apply to every repo; the remote is constructed once and reused.
- **M6 — Single repo unchanged.** The positional-repo path behaves exactly as T10b; the fan-out is
  additive.
- **M7 — Tests.** Repos-file parsing (comments/blank/relative/empty/missing); two fixture repo copies
  both pass; one missing repo fails while the other passes; the fan-out JSON/text; two fake PRs with
  one remote; the app remote constructed once; the overrides; a bad file/bundle exits 2; the existing
  commands green. Offline.
- **M8 — No service.** No webhooks, installation discovery, database, concurrency or deployment.

### Should have

- **S1 — Deterministic order.** File order is the report/PR order; no sorting.
- **S2 — Per-repo error text** is a capped, named message, never a traceback.
- **S3 — `--json` errors** are one object, as in the other commands.

### Nice to have

- **N1 — `--parallel N`**; a later card; sequential is deterministic and simpler.
- **N2 — Installed repo discovery**; T10d.
- **N3 — A per-repo outcome written to the T9 corpus**; a later integration.

## Data Model

```
RepoList = tuple[Path, ...]          # parsed --repos file

ProviderRepoResult
  repo: str
  results: tuple[FixResult, ...]
  exit: int                         # 0 or 1
  error: str | None                 # "not a directory" / a capped per-repo error

ProviderFanoutReport
  provider, migration: str
  repos: tuple[ProviderRepoResult, ...]
  summary: {repos, passed, failed}
```

The per-repo `results`/`summary` reuse the shipped fix items; no new proof/PR type.

## API Contract

```python
from tenon.provider import load_repos

repos = load_repos("repos.txt")     # tuple[Path, ...]
```

CLI:

```sh
tenon provider migrate --bundle stripe-v2500-v2596.json --repos repos.txt \
  --open-pr --remote app --app-id 123 --app-installation-id 456 --app-private-key app.pem
```

No service, no webhooks, no database.

## Technical Considerations

- **Why a file, not repeated flags.** A provider generates a customer list; one path per line is easy
  to produce, diff and keep next to the bundle. Relative paths make the directory portable.
- **Why sequential.** Deterministic order, one remote/token, simple partial-failure reporting. A
  `--parallel` is a later optimization with a different reporting/rate-limit story.
- **Why continue on a bad repo.** A provider wants the full pass/fail list; one typo should not hide
  the other 49. A missing path is a per-repo failure (exit 1), not a usage error (exit 2); a bad
  *list file* or bundle is a usage error.
- **Why one remote.** The app token is minted once and reused; `gh` auth is process-wide. The T5
  writer still clones/commits/pushes per repo.
- **Why no service.** Installation discovery, webhooks, a database and deployment are T10d; the
  per-repo result shape is designed to survive that replacement.
- **Global vs per-repo errors.** The bundle/spec/config is shared; a spec refusal aborts the run
  (exit 2). A repo path or a repo-specific proof/PR failure is per-repo (exit 1). The distinction is
  deliberate.

## Risks & Open Questions

- **Partial failure.** Some PRs may open before a later repo fails; no rollback. The report names
  every repo/PR; a later card can add a rollback/retry policy.
- **Sequential time.** N repos × (copy + checks + PR) can be slow; `--parallel` is a later card.
- **Token lifetime.** A long fan-out may outlive the installation token; this card mints once per
  run. A later card can refresh.
- **No installed discovery.** The provider must have local checkouts; T10d discovers installed repos
  via the app API.
- **The bundle is trusted local input.** Paths/commands are operator-chosen; not a sandbox.
- **Open question — should a missing repo be exit 1 or 2?** Exit 1 (a per-repo failure) so the
  summary stays complete; the list/bundle itself is exit 2.
- **Open question — should the fan-out write to the T9 corpus?** Not in this card; the report is the
  artifact. A later integration can record per-repo outcomes.

## Out of Scope

- Installed/hosted fan-out, webhooks, installation discovery, a database, deployment.
- Parallelism, retries, rollback.
- Provider branding in the PR body.
- T11 languages; new proof levels; new proposer rules.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `provider-repos` | `load_repos` (comments/blank/relative/expanduser/errors) and the repo-list type. No CLI/pipeline. |
| `provider-fanout` | The `--repos` command, the per-repo loop, the remote reuse, the text/JSON fan-out report, exit codes, docs/tests. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | T10b is one repo; a provider has many customers; a service is later. |
| User understanding | 🟢 | Provider/self-hoster/customer/T10d; the repo list and summary are concrete. |
| Success metrics | 🟢 | Repo list, per-repo result, fan-out envelope, exit codes, offline tests. |
| Scope clarity | 🟢 | Local list only; installed/hosted/parallel excluded. |
| Edge cases & risks | 🟡 | Partial PRs, sequential time and token lifetime are real operational edges. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses T10b/T5 and stdlib; no new dependency. |
| Go-to-market | 🟢 | The first multi-customer provider flow; T10d is the hosted version. |

**Areas to strengthen before sharing:** the fan-out is sequential and has no rollback; a provider
running 50 repos may want parallelism and a retry policy. The per-repo report is the honest first
step.

**The question I would want answered before greenlighting this:** *If repo 3 of 50 fails after repos
1-2 opened PRs, what does the provider do?* The answer this card records: the report names every
repo and PR, the exit is 1, and the provider retries/fixes manually; no automatic rollback in this
slice.
