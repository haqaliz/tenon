# Spec: `pr-write` (T5 PR writer)

- **Feature:** `pr-writer`
- **PRD:** `docs/planning/pr-writer/prd.md` (§ Data Model, M1–M9, M12)
- **Boundary:** the only code that touches the repository and the host. Preconditions, clone, apply,
  commit, push, PR, cleanup. Rendering lives in `pr-render`; answer types in `pr-result`.

## Problem slice

T4 proved a diff in a copy that is deleted. T5 must ship that exact diff from a clean checkout, as a
branch and PR, without touching the user's tree, the default branch, or any merge path. This aspect is
where the guardrails stop being prose.

## In-scope requirements

- Public `write_pr(proposal, proof, repo, *, remote, base=None, allow_unverified=False,
  unanalyzed=()) -> PrResult`.
- **Precondition order** (first match wins, before any network call):
  1. `NOT_A_GIT_REPO` — `git rev-parse --is-inside-work-tree` fails.
  2. `NO_PATCH` — `proposal.edits` or `proposal.diff` is empty.
  3. `DIRTY_CHECKOUT` — `git status --porcelain` is non-empty (untracked non-ignored files count;
     ignored files do not).
  4. `NO_REMOTE` — `git remote get-url origin` fails.
  5. `UNVERIFIED_NOT_ALLOWED` — level is `UNVERIFIED` and `allow_unverified` is false.
  6. `UNKNOWN_DEFAULT_BRANCH` — `base` is absent and the remote reports no default.
  7. `DEFAULT_BRANCH` — the rendered branch equals the base.
  8. `BRANCH_EXISTS` — the remote already has the branch.
  9. `REMOTE_CHECK_FAILED` — the remote branch query itself fails; no clone or push follows.
- **Clone.** `tempfile.mkdtemp(prefix="tenon-pr-")`, then `git clone --no-hardlinks -- <repo> <copy>`.
  A clone or temp failure is `COPY_FAILED`. Delete the copy in `finally` on every path.
- **Apply.** `git apply -p1 -` with `proposal.diff` as stdin, `cwd=copy`, `shell=False`, timeout.
  Failure or timeout is `PATCH_DID_NOT_APPLY`. Validate every `proposal.files` path: relative, no
  `..`, no backslash, no absolute path; a violation is `ValueError` (a caller error, like T3).
- **Commit.** `git add -- <proposal.files>` then `git commit -m <draft.commit_message>`, passing the
  source repository's effective `user.name`/`user.email` with `-c` so a local-only identity is not
  replaced by the clone's global config. A failure is `COMMIT_FAILED`. Do not invent an identity.
- **Push.** `remote.push(copy, branch)`. The real adapter runs
  `git push --set-upstream origin <branch>` with `GIT_TERMINAL_PROMPT=0`; never `--force`, never the
  base branch. Failure is `PUSH_FAILED`.
- **PR.** `remote.create_pr(copy, branch=..., base=..., title=..., body=..., draft=...)`. The real
  adapter runs `gh pr create --base <base> --head <branch> --title <title> --body-file - [--draft]`
  with `GH_PROMPT_DISABLED=1` and the body on stdin; it returns the URL from the last non-empty
  stdout line. Failure or an unparseable URL is `PR_FAILED`.
- **Adapter protocol.** `Remote` with `default_branch(repo) -> str`, `branch_exists(repo, branch) ->
  bool`, `push(repo, branch) -> None`, `create_pr(...) -> str`. No merge, no force, no delete.
- **`GitGhRemote`.** `subprocess.run` with argument lists, `shell=False`, timeouts; missing binaries
  and non-zero exits become `RemoteError(detail)`, which `write_pr` maps to the operation's refusal.
  The default branch comes from `git symbolic-ref --short refs/remotes/origin/HEAD`, then
  `git ls-remote --symref origin HEAD`; both failing returns `""`.
- **Refusal detail.** Cap the failed command's combined output with `tenon.prove.tail` (last 20 lines,
  2,000 chars per line). No traceback escapes.

## Out-of-scope

- Rendering (`pr-render`), the proof run (T4), the CLI (M1.4).
- Merging, auto-merge, force-push, branch deletion, updating an existing PR.
- Forks, GitHub App/OAuth, token storage.
- Stashing or committing the user's work.

## Acceptance criteria

- **AC1 — Order and no side effects.** Each precondition above returns the named refusal; the
  user's tree has no new branch, commit, file or modified mtime, and no remote call is made when the
  refusal is before the network.
- **AC2 — Level gate.** `UNVERIFIED` without opt-in returns `UNVERIFIED_NOT_ALLOWED` with zero remote
  calls; with opt-in, the fake receives `draft=True` and the body names the cause.
- **AC3 — Clean tree.** One modified file → `DIRTY_CHECKOUT`; one untracked non-ignored file →
  `DIRTY_CHECKOUT`; an ignored file alone → the run proceeds.
- **AC4 — Isolation.** A successful run leaves the source tree byte-identical and `git status` clean,
  and removes every `tenon-pr-*` temp directory on success, refusal and exception.
- **AC5 — Diff.** A garbage diff → `PATCH_DID_NOT_APPLY`; the committed tree contains exactly
  `proposal.files`; the commit subject equals the draft's.
- **AC6 — Branch.** The fake sees the deterministic branch; an existing branch → `BRANCH_EXISTS`
  before cloning; no force-push path exists.
- **AC7 — Push and PR.** The fake records push then create_pr with the rendered title/body and the
  resolved base; the returned URL is in `PrResult.url`; `OPENED` has no refusal.
- **AC8 — Default branch.** Explicit `base` wins; `origin/HEAD` and `ls-remote` are covered by the
  adapter unit tests; an empty remote default with no `base` → `UNKNOWN_DEFAULT_BRANCH`; a fake
  default equal to the rendered branch → `DEFAULT_BRANCH`.
- **AC9 — Adapter argv.** `GitGhRemote` builds `git`/`gh` argument lists with no `merge`, no
  `--force`, the body on stdin, and the draft flag only for `UNVERIFIED`; a fake runner returns a URL.
- **AC10 — Real local git.** An offline integration test with a local bare remote proves
  `default_branch`, `branch_exists`, and `push` with the real adapter; `create_pr` is overridden to a
  fake, so no network.
- **AC11 — Offline.** `uv run pytest` needs no network, no GitHub credentials and no `gh` login.

## Dependencies and sequencing

- Depends on `pr-result` and `pr-render`.
- `tenon.prove.tail` for capped detail; `tenon.propose.Proposal`.
- Land last.

## Open questions / risks

- `gh` may be missing, unauthenticated or older than the `--draft` flag; all map to `PR_FAILED` with
  the tail.
- A push succeeds and the PR call fails: the branch remains on the remote. The refusal reports it;
  cleanup is a later card because deleting a remote branch is itself a mutating operation.
- A branch created by another actor between `branch_exists` and `push` fails the push; no force.
- A repo with submodules or LFS may clone without their content; the proof ran on a tree that had
  them. The clone is local and honest about what git tracks; a later card may add `--recurse-submodules`.
