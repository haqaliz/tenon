# PRD: Proof runner (T4)

- **Slug:** `proof-runner`
- **Capability:** T4 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M1.2 in `docs/ROADMAP.md` (Phase 1)
- **Status:** approved for implementation on 2026-10-29
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1 says what changed, T2 where it hurts, and T3 proposes a diff. None of them runs anything. Without
T4 the product is a plausible patch generator, which `CLAUDE.md` forbids: only execution may decide
that a fix is verified. T4 is also the last capability needed before the Phase 0 gate (M0.3), where a
real API change must produce a patch that passes a real check.

The dangerous shortcuts are obvious and all rejected here: applying to the user's checkout, running
the user's checks in the original tree, treating a green run after a patch as proof without knowing
the baseline was green, and calling a run "verified" when the command never existed.

**For whom:** T5 (writes the proof level into the PR), M1.4 (exit codes) and the developer reading
why a fix is only a flagged suggestion.

## Goals & Success Metrics

1. **Isolation.** Every check runs in a fresh temporary copy. The source tree's file contents and
   mtimes are identical before and after `prove()`.
2. **Baseline first.** The check runs in the copy before the patch. A red baseline is
   `TESTS_FAILED_BEFORE`, never blamed on the patch, and the patch is not applied.
3. **Execution decides.** `TESTS_PASSED` only when the baseline exited 0, the patch applied, and the
   patched check exited 0. Every other path is `UNVERIFIED` with one named cause.
4. **Named non-results.** `NO_PATCH_PROPOSED`, `PATCH_DID_NOT_APPLY`, `NO_TESTS_FOUND`,
   `TESTS_FAILED_BEFORE`, `TESTS_FAILED_AFTER`, `CHECK_TIMED_OUT`, `COPY_FAILED`.
5. **No more than was run.** This card emits only `TESTS_PASSED` and `UNVERIFIED`; the rest of the
   ladder is T7.
6. **Deterministic shape.** Same inputs produce the same level, cause and ordered check records;
   output tails are capped. Wall-clock durations are not recorded.

Measured by fixture repositories and a real subprocess in `tests/prove/`, offline.

## User Personas & Scenarios

- **T5 PR writer.** "Tell me the strongest thing that actually ran, or the reason nothing did, so the
  PR can say exactly that."
- **Developer.** Sees `UNVERIFIED — TESTS_FAILED_BEFORE` and understands the repo was already red.
- **M1.4 CLI.** Maps `level` to exit code (`TESTS_PASSED` → 0, `UNVERIFIED` → 1).

Scenario: a rename proposal on a fixture repo. Baseline `python check.py` exits 0. The diff applies.
The patched check exits 0. Result: `TESTS_PASSED`. If the same repo's baseline exits 1, the result is
`UNVERIFIED / TESTS_FAILED_BEFORE` and the diff is never applied.

## Requirements

### Must have

- **M1 — Inputs.** `prove(proposal: Proposal, root: str | Path, command: Sequence[str], timeout:
  float = 300.0) -> ProofResult`. No diffing, no locating, no spec access.
- **M2 — Isolated copy.** Copy `root` to a fresh temporary directory, skipping `.git`, `.venv`,
  `venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `build`,
  `dist` and dot-directories at any level. Delete the copy before returning, on every path.
- **M3 — Baseline.** Run `command` in the copy with `cwd=copy`. Non-zero → `TESTS_FAILED_BEFORE`,
  no patch applied, `after` is `None`. Timeout → `CHECK_TIMED_OUT`.
- **M4 — Apply the shipped diff.** Apply `proposal.diff` with `git apply -p1 -` (stdin, `cwd=copy`).
  Failure → `PATCH_DID_NOT_APPLY`. Never use the structured edits as a shortcut: the PR will ship the
  diff, so the diff is what gets proven.
- **M5 — Post-patch check.** Non-zero after a green baseline → `TESTS_FAILED_AFTER`. Timeout →
  `CHECK_TIMED_OUT`. Zero → `TESTS_PASSED`.
- **M6 — Preconditions.** `proposal.edits` empty and `proposal.reason is STALE_SITE` →
  `PATCH_DID_NOT_APPLY`; any other empty proposal → `NO_PATCH_PROPOSED`. Empty command →
  `NO_TESTS_FOUND` before any copy. A command that is a string is a `ValueError` (no shell).
- **M7 — Check record.** `CheckResult(kind, command, returncode, timed_out, stdout_tail,
  stderr_tail)`, tails capped at the last 20 lines each. Timeout kills the child process.
- **M8 — Result.** `ProofResult(level, cause, baseline, after, patch_applied)` with
  `level: TESTS_PASSED | UNVERIFIED`; `cause` set iff `UNVERIFIED`; `to_dict()/to_json()` byte-stable
  in shape and ordering.
- **M9 — Never write the source.** No path under `root` is opened for writing; the copy is the only
  writable tree. A copy failure is `COPY_FAILED`, not a traceback.
- **M10 — No shell, no model.** `subprocess.run` with an argument list, `shell=False`; `git apply`
  is the only other process. No network calls by Tenon itself.

### Should have

- **S1 — Tails are useful.** `stdout_tail`/`stderr_tail` are the last 20 non-empty-preserving lines,
  each truncated to 2,000 characters, so a PR body can quote the failure.
- **S2 — `command` is echoed** on every check so the PR can say what ran.

### Nice to have

- **N1 — `patch_path` list** in the result, from `proposal.files`; skipped if it adds nothing.

## Data Model

```
ProofLevel    TESTS_PASSED | UNVERIFIED
ProofCause    NO_PATCH_PROPOSED | PATCH_DID_NOT_APPLY | NO_TESTS_FOUND
              TESTS_FAILED_BEFORE | TESTS_FAILED_AFTER | CHECK_TIMED_OUT | COPY_FAILED

CheckResult
  kind: "baseline" | "after"
  command: tuple[str, ...]
  returncode: int | None      # None on timeout
  timed_out: bool
  stdout_tail: str
  stderr_tail: str

ProofResult
  level: ProofLevel
  cause: ProofCause | None
  baseline: CheckResult | None
  after: CheckResult | None
  patch_applied: bool
  to_dict() / to_json()
```

Deliberately absent: a duration, a score, a "confidence", a merge decision, and any cause that
implies the patch is good when no check ran.

## API Contract

```python
from tenon.prove import prove, ProofLevel

result = prove(
    proposal,
    "path/to/repo",
    command=["python", "-m", "pytest", "-q"],
    timeout=300.0,
)
result.level     # ProofLevel.TESTS_PASSED | ProofLevel.UNVERIFIED
result.cause     # None | ProofCause.TESTS_FAILED_BEFORE | ...
result.baseline  # CheckResult | None
result.after     # CheckResult | None
result.to_json() # byte-stable
```

No CLI, no exit codes (M1.4), no branch or PR work.

## Technical Considerations

- **Why a copy, not a git worktree.** The user's repo may have uncommitted changes, and `git
  worktree` would not carry them. A filesystem copy is honest and simple; the cost is I/O, bounded
  by the skip list.
- **Why `git apply` and not the edit list.** T3's diff is the artifact T5 will ship. Proving the
  edits and shipping a diff would leave a gap; the runner applies exactly what will be proposed.
- **Environment.** The command runs with the caller's environment and `cwd=copy`. A project that
  relies on a venv inside the repo must pass an absolute interpreter path or a command that creates
  its own environment; the skip list keeps `.venv` out on purpose.
- **Timeout.** `subprocess.run(timeout=...)` raises `TimeoutExpired`; kill the child and record
  `timed_out=True`, `returncode=None`.
- **Determinism.** `to_json()` ordering is canonical; the tails reflect the check, which is by nature
  environment-dependent. That is the point: the level is an observation, not an assertion.

## Risks & Open Questions

- **R1 (repos without tests).** `NO_TESTS_FOUND` and a red baseline are first-class. Mitigation: T7's
  weaker levels; not this card.
- **R2 (verified but still breaks production).** `TESTS_PASSED` means exactly "the command you gave
  returned 0 before and after the patch". The PR must quote the command. T5 owns that wording.
- **Copy cost and fidelity.** Symlinked venvs, submodules, generated data and absolute paths inside
  test fixtures can break in a copy. Mitigation: the skip list, named `COPY_FAILED`, and a PRD note
  that the command must be runnable in a plain copy.
- **Arbitrary code execution.** The user's command is code from the repository. Tenon runs it only
  when asked, in a copy; it is not a sandbox. Documented, not solved.
- **Open question — should the baseline command be the same as the post-patch command?** Yes in this
  card. A separate baseline command is a T7 concern.

## Out of Scope

- `CHARACTERIZED`, `REPLAYED`, `TYPES_BUILD_ONLY` and the `--require` ladder (T7).
- PR creation, branch names, commit messages (T5).
- CLI and exit codes (M1.4).
- Sandboxing, containers, resource limits beyond a timeout.
- Installing dependencies, creating a venv, or network setup.
- Retrying flaky checks.
- Locating or proposing anything.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `proof-result` | `ProofLevel`, `ProofCause`, `CheckResult`, `ProofResult`, invariants, tails, JSON. No subprocess, no copy. |
| `working-copy` | Copy with the skip list, `git apply` the diff, cleanup on every path, `COPY_FAILED`/`PATCH_DID_NOT_APPLY`. No command execution. |
| `run-proof` | `run_check` with timeout and tails; `prove()` orchestration, baseline-first ordering, cause mapping. |
