"""Isolated copies: the skip list, symlinks, cleanup and copy failures."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from tenon.prove import CopyError, ProofCause, copy_tree, isolated_copy

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
COPY_DOT = FIXTURES / "copy-dot"

SKIPPED = [
    ".git",
    ".git/config",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".github",
    "sub/.git",
    "sub/.hidden",
]


def a_dotted_root(tmp_path):
    """The committed fixture plus the nested repositories Git cannot track."""
    root = tmp_path / "source"
    shutil.copytree(COPY_DOT, root, symlinks=True)
    (root / ".git").mkdir()
    (root / ".git/config").write_text("[core]\n", encoding="utf-8")
    (root / "sub/.git").write_text("gitdir: ../.git/modules/sub\n", encoding="utf-8")
    return root


# Spec AC1: the copy keeps ordinary files and drops build/VCS/cache state.
def test_copy_tree_keeps_ordinary_files(tmp_path):
    dest = tmp_path / "copy"

    copy_tree(COPY_DOT, dest)

    assert (dest / "keep.py").read_text(encoding="utf-8") == 'print("kept")\n'
    assert (dest / "sub/keep.py").is_file()


# Spec AC1: `.github` is dropped by the dot-directory rule.
@pytest.mark.parametrize("name", SKIPPED)
def test_copy_tree_drops_every_skipped_entry(tmp_path, name):
    root = a_dotted_root(tmp_path)
    dest = tmp_path / "copy"

    copy_tree(root, dest)

    assert not (dest / name).exists(), name


# Spec AC1 / task: dot-files are not dot-directories.
def test_copy_tree_keeps_env_but_drops_github(tmp_path):
    root = a_dotted_root(tmp_path)
    dest = tmp_path / "copy"

    copy_tree(root, dest)

    assert (dest / ".env").read_text(encoding="utf-8") == "TENON_FIXTURE=1\n"
    assert (dest / ".gitignore").is_file()
    assert not (dest / ".github").exists()


# Spec AC2: a symlink stays a link, with the same target.
def test_copy_tree_keeps_a_symlink_as_a_link(tmp_path):
    dest = tmp_path / "copy"

    copy_tree(COPY_DOT, dest)

    link = dest / "link.py"
    assert link.is_symlink()
    assert os.readlink(link) == "keep.py"
    assert link.read_text(encoding="utf-8") == 'print("kept")\n'


# Spec AC7: cleanup after a normal exit.
def test_isolated_copy_removes_the_copy_after_normal_exit():
    with isolated_copy(COPY_DOT) as copy:
        assert (copy / "keep.py").is_file()
        recorded = copy

    assert not recorded.exists()


# Spec AC7: cleanup when the caller's body raises.
def test_isolated_copy_removes_the_copy_after_an_exception():
    with pytest.raises(RuntimeError, match="boom"):
        with isolated_copy(COPY_DOT) as copy:
            recorded = copy
            raise RuntimeError("boom")

    assert not recorded.exists()


# Spec AC3: a missing root is a named failure, and leaves no temp directory.
def test_isolated_copy_of_a_missing_root_raises_copy_error(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    with pytest.raises(CopyError) as caught:
        with isolated_copy(tmp_path / "missing"):
            pass

    assert caught.value.cause is ProofCause.COPY_FAILED
    assert "missing" in str(caught.value)
    assert list(tmp_path.glob("tenon-prove-*")) == []


def test_copying_a_file_as_the_root_raises_copy_error(tmp_path):
    source = tmp_path / "file.py"
    source.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(CopyError) as caught:
        copy_tree(source, tmp_path / "copy")

    assert caught.value.cause is ProofCause.COPY_FAILED


def test_copy_error_str_renders_the_cause_and_message():
    error = CopyError(ProofCause.COPY_FAILED, "root is missing")

    assert error.cause is ProofCause.COPY_FAILED
    assert error.message == "root is missing"
    assert "COPY_FAILED" in str(error)
    assert "root is missing" in str(error)
