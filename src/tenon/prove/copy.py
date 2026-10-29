"""Copy a repository without VCS or cache state, then apply the shipped diff."""

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .result import ProofCause

# `.github` is skipped by the dot-directory rule: checks do not need CI config.
SKIPPED = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)


class CopyError(Exception):
    """The tree could not be copied; the caller maps it to ``COPY_FAILED``."""

    def __init__(self, cause: ProofCause, message: str) -> None:
        super().__init__(f"{cause.value}: {message}")
        self.cause = cause
        self.message = message


def _ignore(directory: str, names: list[str]) -> set[str]:
    """Drop the skip list and every dot-directory, keeping dot-files."""
    return {
        name
        for name in names
        if name in SKIPPED
        or (name.startswith(".") and os.path.isdir(os.path.join(directory, name)))
    }


def copy_tree(root: str | Path, dest: str | Path) -> None:
    """Copy ``root`` to ``dest``, skipping VCS, caches, build output and dot-dirs."""
    try:
        shutil.copytree(root, dest, symlinks=True, ignore=_ignore)
    except OSError as exc:
        raise CopyError(
            ProofCause.COPY_FAILED, f"could not copy {root}: {exc}"
        ) from exc


@contextmanager
def isolated_copy(root: str | Path) -> Iterator[Path]:
    """Yield a temporary copy of ``root``; delete it on success and on error."""
    with tempfile.TemporaryDirectory(prefix="tenon-prove-") as tmp:
        dest = Path(tmp) / "repo"
        copy_tree(root, dest)
        yield dest


def apply_diff(copy: str | Path, diff: str) -> bool:
    """Apply ``diff`` inside ``copy``; a missing ``git`` is a quiet failure.

    ``-p1`` strips the ``a/`` / ``b/`` prefixes T3 emits. No ``--unsafe-paths``:
    a diff path escaping the copy is git's own rejection to make.
    """
    if not diff:
        return True
    try:
        result = subprocess.run(
            ["git", "apply", "-p1", "-"],
            cwd=copy,
            input=diff,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0
