# Spec: working-copy

**Slug:** `proof-runner` · **Aspect 2 of 3** · depends on `proof-result` for the causes it raises.

## Problem slice

Two isolation guarantees in one module: the user's tree is never written, and the thing applied is
the exact diff T5 will ship. No command execution here; this aspect only produces a prepared copy or
a named failure.

## In scope

- `copy_tree(root, dest)`: `shutil.copytree` with an ignore callable that drops, at any depth:
  `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.mypy_cache`,
  `.ruff_cache`, `build`, `dist`, and any directory starting with `.`. Symlinks are copied as
  symlinks (`symlinks=True`), not followed.
- `apply_diff(copy, diff) -> bool`: `subprocess.run(["git", "apply", "-p1", "-"], cwd=copy,
  input=diff, text=True, capture_output=True, timeout=60)`. Return `returncode == 0`. A missing
  `git` (`FileNotFoundError`) returns `False`; an empty diff returns `True` without running.
- `isolated_copy(root)` context manager: creates a `TemporaryDirectory`, copies, yields the path,
  always removes. A copy failure raises `CopyError(cause=COPY_FAILED, message)`; the caller maps it.
- Safety: no function here opens a file under `root` for writing. The copy is the only writable
  location.
- A diff path escaping the copy is rejected by `git apply` itself (it refuses `..` by default); the
  runner does not add `--unsafe-paths`.

## Out of scope

- Running the user's command, timeouts, tails.
- Deciding `TESTS_PASSED`.
- Installing dependencies or making the copy runnable.

## Acceptance criteria

1. Copying a fixture with `.git`, `.venv`, `__pycache__` and `node_modules` yields a copy containing
   none of them, while `.github/` is also dropped (dot-directory rule) — document that `.github` is
   not needed for checks.
2. A symlinked file inside the root is copied as a symlink, not resolved.
3. Copying a non-existent root raises `CopyError` with `cause=COPY_FAILED`; no temp directory is
   left behind.
4. A real T3 diff applies to a copy of `sdk-basic` and the file contains `amount_cents`; a garbage
   diff returns `False` and leaves the copy unchanged.
5. An empty diff returns `True` and changes nothing.
6. The source tree's file hashes are identical before and after a copy-and-apply cycle.
7. The temporary directory is removed after both success and failure (probe with a recorded path).
8. `git` missing from `PATH` returns `False`, never raises (monkeypatch `subprocess.run` to raise
   `FileNotFoundError`).

## Dependencies & sequencing

After `proof-result`; parallel with `run-proof` in principle, but `prove()` needs both.

## Open questions

- Should `.github` be preserved? No: checks do not need it, and copying it invites workflows that
  reference repository context. Documented in the skip list.
