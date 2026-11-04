# PRD: PR writer (T5)

- **Slug:** `pr-writer`
- **Capability:** T5 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M1.3 in `docs/ROADMAP.md` (Phase 1)
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1–T4 are shipped. `detect` turns two OpenAPI documents into typed changes, `locate` finds the
affected calls, `propose` renders a diff, and `prove` applies that exact diff to a temporary copy and
runs the user's check. Then the copy is deleted. The product promise — a pull request that states
what was actually proven — has no implementation.

Without T5, M1.3 stays unstarted, the OSS on-ramp (`tenon fix`, M1.4) has no `--open-pr` target, and
the two real Phase 0 cases remain evidence scripts rather than something a user can receive. T5 is
the last mile between a proven diff and a reviewer.

The dangerous shortcuts are rejected here: pushing to the default branch, force-pushing over an
existing branch, opening a PR from the user's dirty checkout, calling an `UNVERIFIED` result
"verified", and exposing a merge path at all.

**For whom:** the developer whose integration Tenon repairs, the reviewer reading the stated proof
level, and M1.4 (`tenon fix --open-pr`).

## Goals & Success Metrics

1. **One call from proof to PR.** Given a `Proposal` and the `ProofResult` T4 returned for it,
   produce a branch, a commit and a PR whose title and body state the level that actually ran.
2. **Executable guardrails.** Never push to the default branch; never merge; never force-push; never
   modify the user's checkout. Each refusal is a named result, tested.
3. **Honest labels.** `TESTS_PASSED` opens a normal PR. `UNVERIFIED` refuses by default; an explicit
   opt-in opens a draft PR that names the cause and never claims the patch passed.
4. **Determinism.** The same proposal, proof and unanalyzed list produce byte-identical title, body,
   branch name and commit subject. No clock, no random id, no environment text in the draft.
5. **Offline tests.** Every remote operation sits behind an injectable adapter. `tests/` makes no
   network call and needs no GitHub credentials.
6. **Named non-results.** Every precondition failure returns a `PrRefusal`, never a traceback.

Measured by fixture repos, a local bare remote and fake adapters in `tests/pr/`, offline.

## User Personas & Scenarios

- **Developer with a passing proof.** Runs the pipeline, calls `write_pr`, receives a PR titled
  `[TESTS_PASSED] tenon: ...` whose body quotes the command, the baseline/after exit codes, the
  skipped sites and the unanalyzed subtrees.
- **Developer with an `UNVERIFIED` proof.** Gets `UNVERIFIED_NOT_ALLOWED` by default and a local
  suggestion. With `allow_unverified=True`, gets a draft PR stating the cause.
- **Reviewer.** Sees the level in the title, the exact command that ran, what Tenon refused to touch,
  and a plain statement of what the proof does not establish.
- **M1.4 CLI.** Calls `write_pr`; maps `OPENED` to success and `REFUSED` to a named error.

Scenario: the M0.3 Stripe rename. `proposal.diff` touches two files and `prove` returned
`TESTS_PASSED`. T5 clones the clean checkout, applies the same diff, commits, pushes
`tenon/renamed-payment_method_types-a1b2c3d4`, and opens a PR against the remote's default branch
with the proof section at the top.

## Requirements

### Must have

- **M1 — Inputs.** `write_pr(proposal: Proposal, proof: ProofResult, repo: str | Path, *,
  remote: Remote, base: str | None = None, allow_unverified: bool = False,
  unanalyzed: Sequence[Unanalyzed] = ()) -> PrResult`. No detect, locate, propose or prove work.
  `Proposal.diff` is the only patch T5 ships; `ProofResult` is the only proof T5 reports.
- **M2 — Preconditions.** Refuse before any remote write when: the path is not a git repository
  (`NOT_A_GIT_REPO`); `git status --porcelain` is non-empty, including untracked non-ignored files
  (`DIRTY_CHECKOUT`); the repository has no `origin` remote (`NO_REMOTE`); the default branch cannot
  be determined and no `base` was supplied (`UNKNOWN_DEFAULT_BRANCH`); the proposal has no edits
  (`NO_PATCH`). Refusals carry the command output that justified them. A remote that exists but
  cannot be queried for the branch is `REMOTE_CHECK_FAILED`, not a traceback.
- **M3 — Default branch guard.** Determine the base from `base` if supplied, otherwise from
  `origin/HEAD` (falling back to `git ls-remote --symref origin HEAD`). If the branch to push equals
  the base, refuse `DEFAULT_BRANCH` and make no commit, push or PR call.
- **M4 — Deterministic branch.** `tenon/<slug>-<8 hex>`, where the slug is a sanitised summary of the
  change (kind, before, after; lower-case, non-alphanumerics collapsed to `-`, truncated) and the hex
  is the first eight characters of `sha256(diff)`. The branch is never the base branch.
- **M5 — Isolated clone.** Clone the clean checkout to a temporary directory (`git clone
  --no-hardlinks`), apply `proposal.diff` with `git apply -p1 -`, commit exactly `proposal.files`, and
  delete the clone on every path. The user's checkout is never written.
- **M6 — Commit.** Subject `tenon: <summary>` (the title without the level prefix). Read the source
  repository's effective git identity and pass it to the commit in the clone; do not rely on the
  clone inheriting local config, and do not invent a bot identity. A patch that does not apply
  in the clone is `PATCH_DID_NOT_APPLY`, regardless of `allow_unverified`.
- **M7 — Push.** Push only the new branch with `--set-upstream`; never `--force`, never the base
  branch. A refused push is `PUSH_FAILED` with the tail. An existing local or remote branch is
  `BRANCH_EXISTS`; T5 does not update or force an existing branch.
- **M8 — PR.** Create the PR through the `Remote` adapter with the rendered title and body. The
  default base is the remote's default branch. `TESTS_PASSED` → normal PR. `UNVERIFIED` →
  `UNVERIFIED_NOT_ALLOWED` unless `allow_unverified=True`, in which case the PR is a draft and the
  body names the cause. A failed PR call is `PR_FAILED` with the tail.
- **M9 — No merge.** Neither the public API nor the adapter protocol has a merge operation. The
  adapter never invokes `gh pr merge` or any equivalent.
- **M10 — Title and body.** Title: `[<LEVEL>] tenon: <summary>`. Body carries, in order: the level
  (and cause when `UNVERIFIED`); the change record (kind, location, before, after, breaking,
  confidence); the check command; baseline and after exit codes; touched files; skipped sites with
  reasons; supplied unanalyzed subtrees with reasons; a fixed "what this proves" paragraph. The full
  diff is not duplicated in the body; GitHub shows it.
- **M11 — Determinism.** `render_pr` is pure and byte-stable. The PR URL is the only
  remote-dependent output and is not part of the draft.
- **M12 — Adapter seam.** A `Remote` protocol (`default_branch`, `branch_exists`, `push`,
  `create_pr`). `GitGhRemote` is the real implementation: `git` and `gh` via `subprocess.run` with
  argument lists, `shell=False`, timeouts, and no token handling. Tests use a fake; the real adapter
  is never constructed by the test suite.
- **M13 — Serialization.** `PrDraft` and `PrResult` expose `to_dict()` / `to_json()`, byte-stable.

### Should have

- **S1 — `render_pr` public.** M1.4 can preview the title, body and branch without touching a remote;
  a dry run is a renderer call.
- **S2 — Skipped-site detail.** Each skipped entry names the path, line, symbol and reason, so the
  reviewer can inspect what Tenon would not edit.
- **S3 — Unanalyzed detail.** Each unanalyzed pointer and reason is listed when the caller supplies
  `DiffResult.unanalyzed`; T5 does not block a PR on it in this card.
- **S4 — Failure tails.** Refusals quote the last lines of the command that failed, capped the same
  way T4 caps check output.

### Nice to have

- **N1 — PR label.** A `tenon` label when the adapter supports it; skipped if it adds a failure path.
- **N2 — Commit trailer.** `Tenon-Proof: <LEVEL>` in the commit body; skipped if it complicates the
  identity rules.

## Data Model

```
PrRefusal
  NOT_A_GIT_REPO | DIRTY_CHECKOUT | NO_REMOTE | UNKNOWN_DEFAULT_BRANCH | NO_PATCH
  DEFAULT_BRANCH | BRANCH_EXISTS | REMOTE_CHECK_FAILED | UNVERIFIED_NOT_ALLOWED
  PATCH_DID_NOT_APPLY | COPY_FAILED | COMMIT_FAILED | PUSH_FAILED | PR_FAILED

PrDraft
  title: str                 # "[<LEVEL>] tenon: <summary>"
  body: str                  # deterministic markdown
  branch: str                # "tenon/<slug>-<8 hex>"
  commit_message: str        # "tenon: <summary>"
  to_dict() / to_json()

PrResult
  status: OPENED | REFUSED
  level: ProofLevel
  draft: PrDraft
  url: str | None            # OPENED only
  refusal: PrRefusal | None  # REFUSED only
  detail: str                # command tail for a refusal, "" otherwise
  to_dict() / to_json()

Remote (protocol)
  default_branch(repo: Path) -> str
  branch_exists(repo: Path, branch: str) -> bool
  push(repo: Path, branch: str) -> None
  create_pr(repo: Path, *, branch: str, base: str, title: str, body: str,
            draft: bool) -> str
```

Deliberately absent: a merge method, a force option, a fork option, a model prompt, a re-run of the
check, and any duration or score.

## API Contract

```python
from tenon.propose import propose
from tenon.prove import prove
from tenon.pr import GitGhRemote, write_pr

proposal = propose(change, located, "path/to/repo")
proof = prove(proposal, "path/to/repo", ["python", "-m", "pytest", "-q"])

result = write_pr(
    proposal,
    proof,
    "path/to/repo",
    remote=GitGhRemote(),
    allow_unverified=False,
    unanalyzed=diff_result.unanalyzed,
)
result.status    # OPENED | REFUSED
result.level     # TESTS_PASSED | UNVERIFIED
result.url       # PR URL when OPENED
result.refusal   # DIRTY_CHECKOUT | DEFAULT_BRANCH | ... when REFUSED
result.to_json() # byte-stable
```

No CLI, no exit codes, no merge.

## Technical Considerations

- **Why clone, not the user's checkout.** T4 established the isolation discipline; a PR branch must
  not appear in the user's working tree. A local clone also gives a real commit history and the
  configured remote, which a filesystem copy lacks.
- **Why the clean-tree precondition.** T4 proves the working tree, including uncommitted and
  untracked files. A PR ships a commit. If the tree is dirty, the proven code and the shipped commit
  can differ; refusing is the honest choice. Ignored files (`.env`, `.venv`) do not make a tree dirty.
- **Why `git apply` and not the edit list.** As in T4: the diff is the artifact the PR ships, so the
  diff is what gets applied. T5 re-applies it rather than reusing T4's deleted copy.
- **Why `gh`.** It uses the user's existing authentication, handles the PR API and draft state, and
  keeps token handling out of Tenon. Behind the `Remote` protocol it is replaceable.
- **Default branch detection.** `origin/HEAD` is set by clone; when it is missing,
  `git ls-remote --symref origin HEAD` asks the remote. If both fail and no `base` is supplied, the
  writer refuses rather than guessing `main` or `master`.
- **Branch hash.** Hashing the diff gives a stable, collision-resistant suffix. A re-run on the same
  diff and change produces the same branch; the second run refuses `BRANCH_EXISTS` instead of
  force-pushing. A changed diff produces a new branch.
- **Honest wording.** `TESTS_PASSED` means "the command you gave returned 0 before and after the
  patch, in an isolated copy". The body says that and no more. The caller chooses the command, so T5
  cannot know whether it was a focused subset.
- **Unanalyzed subtrees.** T1 records them; `Proposal` does not carry them. T5 accepts the list
  explicitly so T1's honesty survives to the reviewer, without changing T1 or T4.
- **No code egress by Tenon.** Only the final branch and PR are pushed, to the remote the user
  configured. No model is called. The user's existing `gh` credentials authorize the write.

## Acceptance tests (for `tech-plan`)

1. **Renderer golden.** A `TESTS_PASSED` proposal renders a byte-stable title `[TESTS_PASSED]
   tenon: ...` and a body containing the command, both exit codes, the change record, files, skipped
   sites and unanalyzed pointers; the full diff is absent.
2. **UNVERIFIED gate.** Default call → `UNVERIFIED_NOT_ALLOWED` with zero remote calls; with
   `allow_unverified=True` → draft PR whose body names the cause and never says the patch passed.
3. **Default-branch guard.** A draft whose branch equals the base → `DEFAULT_BRANCH`, no commit,
   push or PR call.
4. **Dirty checkout.** One uncommitted edit and one untracked file → `DIRTY_CHECKOUT`, no remote
   call; ignored files alone do not refuse.
5. **Isolation.** The user's checkout contents and `git status` are unchanged after a successful
   run; the clone is deleted on success and on failure.
6. **Branch and commit.** The branch name is deterministic for the same diff; the commit contains
   exactly `proposal.files`; an existing branch → `BRANCH_EXISTS`, never a force push.
7. **Adapter.** The fake records the base, draft flag, title and body; `GitGhRemote` builds the
   expected `git`/`gh` argument lists with no `merge` and no `--force`.
8. **Preconditions.** Not a git repo → `NOT_A_GIT_REPO`; no origin → `NO_REMOTE`; unknown default and
   no base → `UNKNOWN_DEFAULT_BRANCH`; empty proposal → `NO_PATCH`.
9. **Offline.** `uv run pytest` passes with no network and no GitHub credentials.

## Risks & Open Questions

- **R2 (a verified PR still breaks production).** `TESTS_PASSED` is a statement about one command, not
  about production. Mitigation: the title carries the level and the body quotes the command and its
  limits. T5 cannot make a weak check strong.
- **R1 (repos without tests).** T5 inherits T4's `UNVERIFIED` causes. The default refusal keeps an
  unproven patch out of the PR list; the opt-in draft keeps it visible without overclaiming.
- **R6 (code egress).** Opening a PR pushes code to the user's configured remote. Tenon itself sends
  nothing to a model or a Tenon service; the adapter is opt-in and uses the user's credentials.
- **Dirty trees are common.** A strict refusal may block a user mid-work. This is deliberate: the
  proof was against the working tree, and the PR ships a commit. A later card may offer a stashing or
  commit-first flow; not this one.
- **`gh` availability and version.** A missing or unauthenticated `gh` becomes `PR_FAILED` with the
  tail. The adapter requires `git` in all cases.
- **Open question — PR body escaping.** Paths and symbols are wrapped in backticks; a symbol containing
  a backtick could break rendering. The renderer should escape or refuse; decide in the aspect spec.
- **Open question — multiple changes.** One PR per proposal in this card. A multi-change PR needs a
  conflict and body-composition policy; later.
- **Open question — fork remotes.** Same-repository branches only. Fork-based contribution needs a
  different base and head; later.
- **Open question — branch cleanup.** A failed PR after a successful push leaves the branch. T5
  reports it in the refusal; deleting the remote branch is a mutating cleanup that needs its own
  guardrail; later.

## Out of Scope

- The CLI and exit codes (`tenon check` / `tenon fix`, M1.4).
- Merging, auto-merge, force-pushing, branch deletion, or updating an existing PR.
- Fork-based PRs, hosted GitHub App auth, OAuth, token storage.
- Re-running checks or changing the proof contract (T4).
- New proposer rules, T7 proof levels, T6 TS/JS, T8 MCP/probe.
- Committing the user's uncommitted work or stashing on their behalf.
- Multiple proposals or multiple changes in one PR.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `pr-result` | `PrRefusal`, `PrDraft`, `PrResult`, invariants, JSON. No subprocess, no filesystem. |
| `pr-render` | Deterministic title, body, branch slug and hash, commit message, escaping. Pure: `Proposal` + `ProofResult` + unanalyzed in, `PrDraft` out. |
| `pr-write` | Preconditions, default-branch detection, clone/apply/commit/push, `Remote` protocol, `GitGhRemote`, refusal mapping, cleanup. No rendering. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The gap is concrete: a proven diff with no delivery. |
| User understanding | 🟡 | The user is the developer and the reviewer; no external user has run T5 yet. |
| Success metrics | 🟢 | Testable guardrails and a deterministic draft; offline suite. |
| Scope clarity | 🟢 | One PR per proposal; CLI, merge, forks and T7 excluded. |
| Edge cases & risks | 🟡 | Dirty trees, `gh` availability and post-push PR failure are real operational edges. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | `git` and `gh` are present; the adapter seam keeps tests offline. |
| Go-to-market | — | Internal capability; M1.4 exposes it. |

**Areas to strengthen before sharing:** the dirty-tree refusal is the one a user will hit first, and
the post-push PR failure leaves a branch behind. Both are documented rather than solved.

**The question I would want answered before greenlighting this:** *If the PR title says
`[TESTS_PASSED]` but the developer's check was a focused subset that passes before the patch, what
stops a reviewer from reading it as a production guarantee?* The answer this card records: the body
quotes the exact command and states the limit; the label is only as strong as the check the user
chose, and T5 never upgrades it.
