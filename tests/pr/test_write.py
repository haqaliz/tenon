"""Write a proven proposal as a branch and PR without touching the user's tree."""

import hashlib
import os
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from tenon.pr import render_pr
from tenon.pr.write import write_pr
from tenon.propose import ProposalReason
from tenon.pr.result import PrRefusal, PrStatus
from tenon.prove import ProofLevel

from .conftest import FakeRemote


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def tree_hashes(root):
    root = Path(root)
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


@pytest.fixture(autouse=True)
def pr_tempdir(tmp_path, monkeypatch):
    """Every temporary clone lands in tmp_path and is gone after the test."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    yield

    assert list(Path(tmp_path).glob("tenon-pr-*")) == []


@pytest.fixture(autouse=True)
def a_git_identity(tmp_path, monkeypatch):
    """A known identity for commits in the disposable clone."""
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Tenon Tests\n\temail = tenon@example.test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


def a_fake_remote(**kwargs):
    return FakeRemote(**kwargs)


def an_empty_proposal(proposal):
    return replace(proposal, edits=(), diff="", reason=ProposalReason.NO_RULE)


# Spec AC1: a plain directory is not a git repository and makes no remote call.
def test_a_plain_directory_is_not_a_git_repo(
    tmp_path, a_rename_proposal, a_passed_proof
):
    plain = tmp_path / "plain"
    plain.mkdir()
    remote = a_fake_remote()

    result = write_pr(a_rename_proposal, a_passed_proof, plain, remote=remote)

    assert result.status is PrStatus.REFUSED
    assert result.refusal is PrRefusal.NOT_A_GIT_REPO
    assert result.level is ProofLevel.TESTS_PASSED
    assert result.draft == render_pr(a_rename_proposal, a_passed_proof)
    assert remote.calls == []


# Spec AC1: an empty proposal has no patch and needs no remote call.
def test_an_empty_proposal_is_no_patch(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = a_fake_remote()

    result = write_pr(
        an_empty_proposal(a_rename_proposal),
        a_passed_proof,
        repo_with_remote.work,
        remote=remote,
    )

    assert result.refusal is PrRefusal.NO_PATCH
    assert remote.calls == []


# Spec AC3: one modified tracked file refuses before any remote call.
def test_a_modified_file_is_a_dirty_checkout(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    billing = repo_with_remote.work / "acme" / "billing.py"
    billing.write_text(billing.read_text(encoding="utf-8") + "\n# edit\n")
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.DIRTY_CHECKOUT
    assert "billing.py" in result.detail
    assert remote.calls == []


# Spec AC3: one untracked, non-ignored file refuses before any remote call.
def test_an_untracked_file_is_a_dirty_checkout(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    (repo_with_remote.work / "notes.txt").write_text("notes\n", encoding="utf-8")
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.DIRTY_CHECKOUT
    assert "notes.txt" in result.detail
    assert remote.calls == []


# Spec AC3: an ignored file alone passes the dirty gate and reaches the remote.
def test_an_ignored_file_alone_proceeds(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    (repo_with_remote.work / ".gitignore").write_text("*.log\n", encoding="utf-8")
    git(repo_with_remote.work, "add", ".gitignore")
    git(repo_with_remote.work, "commit", "-m", "ignore logs")
    (repo_with_remote.work / "debug.log").write_text("noise\n", encoding="utf-8")
    remote = a_fake_remote(default="")

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.UNKNOWN_DEFAULT_BRANCH
    assert remote.calls == [("default_branch", repo_with_remote.work)]


# Spec AC1: no origin remote is NO_REMOTE and no remote adapter call is made.
def test_a_repository_without_origin_is_no_remote(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    git(repo_with_remote.work, "remote", "remove", "origin")
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.NO_REMOTE
    assert remote.calls == []


# Spec AC2: UNVERIFIED without opt-in refuses with zero remote calls.
def test_unverified_without_opt_in_calls_no_remote(
    repo_with_remote, a_rename_proposal, an_unverified_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        an_unverified_proof(),
        repo_with_remote.work,
        remote=remote,
    )

    assert result.refusal is PrRefusal.UNVERIFIED_NOT_ALLOWED
    assert result.level is ProofLevel.UNVERIFIED
    assert remote.calls == []


# Spec AC8: an empty remote default with no base is UNKNOWN_DEFAULT_BRANCH.
def test_an_unknown_default_branch_is_named(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = a_fake_remote(default="")

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.UNKNOWN_DEFAULT_BRANCH
    assert remote.calls == [("default_branch", repo_with_remote.work)]


# Spec AC8: an explicit base wins and is never replaced by the remote default.
def test_an_explicit_base_is_used_without_asking_the_remote(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    remote = a_fake_remote(default="main")

    result = write_pr(
        a_rename_proposal,
        a_passed_proof,
        repo_with_remote.work,
        remote=remote,
        base=draft.branch,
    )

    assert result.refusal is PrRefusal.DEFAULT_BRANCH
    assert remote.calls == []


# Spec AC8: a rendered branch equal to the base is DEFAULT_BRANCH, no clone.
def test_the_default_branch_is_refused(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    remote = a_fake_remote(default=draft.branch)

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.DEFAULT_BRANCH
    assert remote.calls == [("default_branch", repo_with_remote.work)]


# Spec AC6: an existing branch refuses before cloning, with no push.
def test_an_existing_branch_is_refused_before_cloning(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    remote = a_fake_remote(default="main", existing=True)
    before = tree_hashes(repo_with_remote.work)

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.BRANCH_EXISTS
    assert remote.calls == [
        ("default_branch", repo_with_remote.work),
        ("branch_exists", repo_with_remote.work, draft.branch),
    ]
    assert tree_hashes(repo_with_remote.work) == before
