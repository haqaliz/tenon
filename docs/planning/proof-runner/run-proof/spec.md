# Spec: run-proof

**Slug:** `proof-runner` · **Aspect 3 of 3** · depends on `proof-result`, `working-copy`.

## Problem slice

The only module allowed to say `TESTS_PASSED`. It runs the user's command with a timeout, records
what happened, and orders the steps so a red baseline is never blamed on the patch. No diffing, no
proposing.

## In scope

- `run_check(command, cwd, kind, timeout) -> CheckResult`:
  - `subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout,
    shell=False, env=os.environ.copy())`;
  - on `TimeoutExpired`: kill the child (the helper does), `returncode=None`, `timed_out=True`,
    tails from the exception's `stdout`/`stderr` when present;
  - `FileNotFoundError` for the executable: return a `CheckResult` with `returncode=127`,
    `stderr_tail` naming the missing executable, not an exception. The caller maps it to
    `TESTS_FAILED_BEFORE` / `TESTS_FAILED_AFTER` — the command the user gave did not run.
- `prove(proposal, root, command, timeout=300.0) -> ProofResult`, first match wins:
  1. `command` is a `str` → `ValueError`; empty/`None` → `NO_TESTS_FOUND` (no copy).
  2. `proposal.edits` empty: `STALE_SITE` → `PATCH_DID_NOT_APPLY`, else `NO_PATCH_PROPOSED`.
  3. Copy the tree (failure → `COPY_FAILED`).
  4. Baseline check in the copy. Non-zero or timeout → `TESTS_FAILED_BEFORE` (`CHECK_TIMED_OUT` on
     timeout), `after=None`, `patch_applied=False`.
  5. Apply the diff (failure → `PATCH_DID_NOT_APPLY`, `after=None`).
  6. After check. Timeout → `CHECK_TIMED_OUT` (`patch_applied=True`); non-zero →
     `TESTS_FAILED_AFTER`; zero → `TESTS_PASSED`, `cause=None`.
  7. The copy is always removed before returning.
- `timeout=None` disables the limit? No: `timeout` must be a positive float; passing `None` is a
  `ValueError`. A zero/negative value is a `ValueError`.
- The result's `baseline`/`after` records echo the command tuple.

## Out of scope

- Copying or applying (aspect 2).
- Proof-result invariants (aspect 1).
- Retries, environment setup, installation, network.
- `--require` levels, `TYPES_BUILD_ONLY`, PR text.

## Acceptance criteria

1. End-to-end on `proof-basic`: T1 rename → T2 locate → T3 propose → `prove` with
   `[sys.executable, "-c", "import acme.billing"]` → `TESTS_PASSED`, `cause=None`,
   `patch_applied=True`, both checks `returncode == 0`.
2. A command exiting 1 on the baseline → `TESTS_FAILED_BEFORE`, `after=None`,
   `patch_applied=False`; the copy is gone.
3. A proposal whose patch breaks the import (fake proposer: `amount` → `1bad`) →
   `TESTS_FAILED_AFTER`, `patch_applied=True`.
4. A `Proposal` with a garbage diff → `PATCH_DID_NOT_APPLY`.
5. `command=[]` → `NO_TESTS_FOUND` without copying (a monkeypatched `copy_tree` raises if called).
6. `command="python -m pytest"` (a string) → `ValueError`.
7. A sleeping command with `timeout=0.2` → `CHECK_TIMED_OUT`; the child is not left running.
8. `proposal.reason=STALE_SITE`, no edits → `PATCH_DID_NOT_APPLY`; `NO_RULE` → `NO_PATCH_PROPOSED`.
9. A missing executable → `TESTS_FAILED_BEFORE` with `returncode=127`, no traceback.
10. The source tree's hashes are identical before and after every case above (one shared fixture
    platform test).
11. `to_json()` is byte-stable across `PYTHONHASHSEED` for the same `ProofResult`.
12. A copy failure (root deleted between build and prove, or monkeypatched `copytree` raising
    `OSError`) → `COPY_FAILED`, no traceback.

## Dependencies & sequencing

Last. Needs aspects 1 and 2.

## Open questions

- Should a missing executable be `NO_TESTS_FOUND` instead of a failed baseline? No: a command was
  given and did not run; `returncode=127` plus the message is more useful, and the cause stays
  `TESTS_FAILED_BEFORE`. Revisit if it confuses PR readers.
- Should the baseline be skipped when the user opts in (`--no-baseline`)? Not this card; the
  baseline is the honesty guarantee.
