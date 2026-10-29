# Spec: proof-result

**Slug:** `proof-runner` · **Aspect 1 of 3** · builds first, everything depends on it.

## Problem slice

The proof level is the product's promise, so its shape is defined before anything runs: what a check
record holds, which causes exist, and the invariant that forbids "verified" without a green after
check. No subprocess, no filesystem.

## In scope

- `ProofLevel`: `TESTS_PASSED`, `UNVERIFIED` only. The rest of the ladder is T7; adding them now
  would imply they can be reached.
- `ProofCause`: `NO_PATCH_PROPOSED`, `PATCH_DID_NOT_APPLY`, `NO_TESTS_FOUND`,
  `TESTS_FAILED_BEFORE`, `TESTS_FAILED_AFTER`, `CHECK_TIMED_OUT`, `COPY_FAILED`.
- `CheckResult`: `kind` (`baseline|after`), `command: tuple[str, ...]`, `returncode: int | None`,
  `timed_out: bool`, `stdout_tail: str`, `stderr_tail: str`. Frozen, slots.
- `ProofResult`: `level`, `cause`, `baseline: CheckResult | None`, `after: CheckResult | None`,
  `patch_applied: bool`.
  - Invariant: `level is TESTS_PASSED` iff `cause is None` and `after is not None` and
    `after.returncode == 0` and `not after.timed_out` and `patch_applied`.
  - `level is UNVERIFIED` iff `cause is not None`.
- `CheckResult` tail helper: `tail(text, lines=20, chars=2000)` keeps the last 20 lines, each
  truncated to 2,000 characters, joined with `\n`, no trailing newline.
- `to_dict()/to_json()`: JSON-safe, `sort_keys`, byte-stable for the same values.

## Out of scope

- Running processes, copying trees, applying diffs.
- Deciding the cause from a run (aspect 3).
- PR text, exit codes, durations, scores.

## Acceptance criteria

1. Every `ProofLevel` and `ProofCause` value constructs and round-trips through `to_dict()`.
2. A `TESTS_PASSED` result with `cause` set raises `ValueError`; with `after=None`, `patch_applied`,
   `False`, or a non-zero `after` raises too.
3. An `UNVERIFIED` result with `cause=None` raises.
4. `UNVERIFIED` with `baseline=None` and `after=None` is valid (e.g. `NO_TESTS_FOUND`).
5. `to_json()` is byte-identical across `PYTHONHASHSEED` values and contains only JSON primitives.
6. `tail` keeps the last N lines, truncates long lines, and returns `""` for empty input.
7. `CheckResult(timed_out=True, returncode=None)` is valid; `timed_out=True` with a return code is
   allowed (the process may have exited while being killed) and must not be normalised silently.

## Dependencies & sequencing

None. First.

## Open questions

- Should `ProofResult` carry the command at the top level as well as per check? The baseline and
  after commands are identical in this card; duplicating them is harmless and keeps each record
  self-contained.
