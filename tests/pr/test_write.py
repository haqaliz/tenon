"""Write a proven proposal as a branch and PR without touching the user's tree."""

import hashlib
import inspect
import os
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from tenon.pr import render_pr
from tenon.pr.remote import GitGhRemote, RemoteError
from tenon.pr.write import write_pr
from tenon.propose import Edit, ProposalReason
from tenon.pr.result import PrRefusal, PrStatus
from tenon.prove import ProofCause, ProofLevel

from .conftest import FakeRemote


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


class InspectingRemote(FakeRemote):
    """Reads the commit in the disposable clone at the moment it is pushed."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.push_repo = None
        self.commit_subject = None
        self.commit_files = ()

    def push(self, repo, branch):
        self.push_repo = Path(repo)
        self.commit_subject = git(repo, "log", "-1", "--pretty=%s").strip()
        self.commit_files = tuple(
            git(repo, "show", "--pretty=", "--name-only", "HEAD").split()
        )
        super().push(repo, branch)


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


class FailingCheckRemote(FakeRemote):
    def branch_exists(self, repo, branch):
        super().branch_exists(repo, branch)
        raise RemoteError("could not reach origin")


# Spec AC1: a remote that cannot be queried is a named refusal, not a traceback.
def test_a_failed_branch_check_is_remote_check_failed(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = FailingCheckRemote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.REMOTE_CHECK_FAILED
    assert "could not reach origin" in result.detail
    assert [call[0] for call in remote.calls] == ["default_branch", "branch_exists"]


# Spec AC4/AC5: a successful run is isolated, clean and commits exactly the files.
def test_a_successful_run_commits_exactly_the_proposal_files(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    before = tree_hashes(repo_with_remote.work)
    remote = InspectingRemote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.status is PrStatus.OPENED
    assert result.refusal is None
    assert result.url == remote.url
    assert tree_hashes(repo_with_remote.work) == before
    assert git(repo_with_remote.work, "status", "--porcelain") == ""
    assert git(repo_with_remote.work, "branch", "--list", "tenon/*") == ""
    assert remote.push_repo != repo_with_remote.work
    assert remote.commit_subject == draft.commit_message
    assert remote.commit_files == a_rename_proposal.files


# Spec M6: the commit uses the source repository's configured identity, not the
# global one that a fresh clone would otherwise inherit.
def test_the_commit_uses_the_source_repository_identity(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    git(repo_with_remote.work, "config", "user.name", "Local Only")
    git(repo_with_remote.work, "config", "user.email", "local@example.test")
    draft = render_pr(a_rename_proposal, a_passed_proof)

    result = write_pr(
        a_rename_proposal,
        a_passed_proof,
        repo_with_remote.work,
        remote=LocalRemote(),
    )

    assert result.status is PrStatus.OPENED
    author = git(
        repo_with_remote.bare, "log", "-1", "--pretty=%an <%ae>", draft.branch
    ).strip()
    assert author == "Local Only <local@example.test>"


# Spec AC5: a garbage diff is PATCH_DID_NOT_APPLY and no commit is pushed.
def test_a_garbage_diff_is_patch_did_not_apply(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    garbage = replace(a_rename_proposal, diff="this is not a diff\n")
    before = tree_hashes(repo_with_remote.work)
    remote = a_fake_remote()

    result = write_pr(garbage, a_passed_proof, repo_with_remote.work, remote=remote)

    assert result.refusal is PrRefusal.PATCH_DID_NOT_APPLY
    assert remote.calls[-1][0] == "branch_exists"
    assert tree_hashes(repo_with_remote.work) == before
    assert git(repo_with_remote.work, "branch", "--list", "tenon/*") == ""


# Spec AC5: a file path that could escape the clone is a caller error.
@pytest.mark.parametrize("path", ["../x.py", "/tmp/x.py", "acme\\billing.py"])
def test_an_unsafe_file_path_raises_value_error(
    path, repo_with_remote, a_rename_proposal, a_passed_proof
):
    edit = replace(a_rename_proposal.edits[0], path=path)
    unsafe = replace(a_rename_proposal, edits=(edit,))

    with pytest.raises(ValueError):
        write_pr(unsafe, a_passed_proof, repo_with_remote.work, remote=a_fake_remote())


# Plan edge case: neither the source nor the clone has an identity, so git refuses.
def test_a_missing_git_identity_is_commit_failed(
    repo_with_remote, a_rename_proposal, a_passed_proof, monkeypatch, tmp_path
):
    git(repo_with_remote.work, "config", "--unset", "user.name")
    git(repo_with_remote.work, "config", "--unset", "user.email")
    config = tmp_path / "no-identity"
    config.write_text("[user]\n\tuseConfigOnly = true\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.COMMIT_FAILED
    assert result.detail
    assert remote.calls[-1][0] == "branch_exists"


# Spec AC4/plan edge case: a temp-dir failure is COPY_FAILED, never a traceback.
def test_a_temp_directory_failure_is_copy_failed(
    repo_with_remote, a_rename_proposal, a_passed_proof, monkeypatch
):
    def failing(*args, **kwargs):
        raise OSError("no temp space")

    monkeypatch.setattr(tempfile, "mkdtemp", failing)

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=a_fake_remote()
    )

    assert result.refusal is PrRefusal.COPY_FAILED
    assert "no temp space" in result.detail


class FailingPushRemote(FakeRemote):
    def push(self, repo, branch):
        super().push(repo, branch)
        raise RemoteError("rejected by remote")


class FailingPrRemote(FakeRemote):
    def create_pr(self, repo, **kwargs):
        super().create_pr(repo, **kwargs)
        raise RemoteError("gh: boom")


# Spec AC7: push and create_pr receive the rendered fields and the resolved base.
def test_push_then_pr_uses_the_rendered_fields(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    remote = a_fake_remote(default="main")

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.status is PrStatus.OPENED
    assert result.url == remote.url
    assert [call[0] for call in remote.calls] == [
        "default_branch",
        "branch_exists",
        "push",
        "create_pr",
    ]
    push = remote.calls[2]
    pr = remote.calls[3]
    assert push[2] == draft.branch
    assert pr[1] == push[1]
    assert pr[1] != repo_with_remote.work
    assert pr[2:] == (draft.branch, "main", draft.title, draft.body, False)


# Spec AC8: an explicit base wins and is never replaced by the remote default.
def test_an_explicit_base_reaches_the_pr(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = a_fake_remote(default="ignored")

    result = write_pr(
        a_rename_proposal,
        a_passed_proof,
        repo_with_remote.work,
        remote=remote,
        base="develop",
    )

    assert result.status is PrStatus.OPENED
    assert [call[0] for call in remote.calls] == [
        "branch_exists",
        "push",
        "create_pr",
    ]
    assert remote.calls[-1][3] == "develop"


# Spec AC2: opting in opens a draft PR whose body names the cause.
def test_allow_unverified_opens_a_draft_pr_naming_the_cause(
    repo_with_remote, a_rename_proposal, an_unverified_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        an_unverified_proof(cause=ProofCause.NO_TESTS_FOUND),
        repo_with_remote.work,
        remote=remote,
        allow_unverified=True,
    )

    assert result.status is PrStatus.OPENED
    pr = remote.calls[-1]
    assert pr[0] == "create_pr"
    assert pr[-1] is True
    assert "Cause: NO_TESTS_FOUND" in pr[5]
    assert "## Tenon proof: UNVERIFIED" in pr[5]


# Spec AC3: a build-only proof below the required tests is refused before any remote call.
def test_types_build_only_below_required_calls_no_remote(
    repo_with_remote, a_rename_proposal, a_proof_at
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_proof_at(ProofLevel.TYPES_BUILD_ONLY),
        repo_with_remote.work,
        remote=remote,
    )

    assert result.status is PrStatus.REFUSED
    assert result.refusal is PrRefusal.BELOW_REQUIRED_LEVEL
    assert "TESTS_PASSED" in result.detail
    assert "TYPES_BUILD_ONLY" in result.detail
    assert remote.calls == []


# Spec AC3: opting in below the requirement opens a draft PR.
def test_below_required_with_opt_in_opens_a_draft(
    repo_with_remote, a_rename_proposal, a_proof_at
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_proof_at(ProofLevel.TYPES_BUILD_ONLY),
        repo_with_remote.work,
        remote=remote,
        allow_below_required=True,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is True


# Spec AC1: a tests-passed proof at the required tests level opens a normal PR.
def test_tests_passed_at_required_opens_a_normal_pr(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_passed_proof,
        repo_with_remote.work,
        remote=remote,
        required=ProofLevel.TESTS_PASSED,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is False


# Spec AC1: a build-only proof at the required build level opens a normal PR.
def test_types_build_only_at_required_opens_a_normal_pr(
    repo_with_remote, a_rename_proposal, a_proof_at
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_proof_at(ProofLevel.TYPES_BUILD_ONLY),
        repo_with_remote.work,
        remote=remote,
        required=ProofLevel.TYPES_BUILD_ONLY,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is False


# Spec AC2: a stronger proof satisfies a weaker requirement with a normal PR.
def test_tests_passed_above_required_opens_a_normal_pr(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_passed_proof,
        repo_with_remote.work,
        remote=remote,
        required=ProofLevel.TYPES_BUILD_ONLY,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is False


# Spec AC4: an unverified proof opted in below the requirement opens a draft.
def test_unverified_with_allow_below_required_opens_a_draft(
    repo_with_remote, a_rename_proposal, an_unverified_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        an_unverified_proof(),
        repo_with_remote.work,
        remote=remote,
        allow_below_required=True,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is True


# Spec AC4: requiring UNVERIFIED still opens a draft, never a normal PR.
def test_unverified_at_required_is_still_a_draft(
    repo_with_remote, a_rename_proposal, an_unverified_proof
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        an_unverified_proof(),
        repo_with_remote.work,
        remote=remote,
        required=ProofLevel.UNVERIFIED,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is True


# Spec AC5: allow_unverified is the deprecated alias for allow_below_required.
def test_allow_unverified_is_an_alias_below_the_required_level(
    repo_with_remote, a_rename_proposal, a_proof_at
):
    remote = a_fake_remote()

    result = write_pr(
        a_rename_proposal,
        a_proof_at(ProofLevel.REPLAYED),
        repo_with_remote.work,
        remote=remote,
        allow_unverified=True,
    )

    assert result.status is PrStatus.OPENED
    assert remote.calls[-1][-1] is True


# Spec AC7: a rejected push is PUSH_FAILED and create_pr is never called.
def test_a_rejected_push_is_push_failed(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    remote = FailingPushRemote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.PUSH_FAILED
    assert "rejected by remote" in result.detail
    assert [call[0] for call in remote.calls][-1] == "push"


# Spec AC7: a failed PR says the branch was already pushed and cleans the clone.
def test_a_failed_pr_is_pr_failed_and_reports_the_pushed_branch(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    remote = FailingPrRemote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.refusal is PrRefusal.PR_FAILED
    assert "already pushed" in result.detail.lower()
    assert draft.branch in result.detail
    assert [call[0] for call in remote.calls][-1] == "create_pr"


class LocalRemote(GitGhRemote):
    """The real adapter against local git; only gh is replaced."""

    def __init__(self) -> None:
        super().__init__()
        self.pr = None

    def create_pr(self, repo, *, branch, base, title, body, draft):
        self.pr = {"repo": repo, "base": base, "title": title, "body": body}
        return "https://example.test/tenon/pull/1"


# Spec AC10/AC11: real git, local bare remote, no gh and no network.
def test_offline_end_to_end_with_the_real_git_adapter(
    repo_with_remote, a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    before = tree_hashes(repo_with_remote.work)
    remote = LocalRemote()

    result = write_pr(
        a_rename_proposal, a_passed_proof, repo_with_remote.work, remote=remote
    )

    assert result.status is PrStatus.OPENED
    assert result.url == "https://example.test/tenon/pull/1"
    assert remote.pr["base"] == "main"
    assert remote.pr["title"] == draft.title
    assert remote.pr["body"] == draft.body

    heads = subprocess.run(
        [
            "git",
            "ls-remote",
            "--heads",
            str(repo_with_remote.bare),
            draft.branch,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert draft.branch in heads
    assert (
        git(repo_with_remote.bare, "log", "-1", "--pretty=%s", draft.branch).strip()
        == draft.commit_message
    )
    assert (
        git(
            repo_with_remote.bare,
            "show",
            "--pretty=",
            "--name-only",
            draft.branch,
        ).split()
        == list(a_rename_proposal.files)
    )
    assert git(repo_with_remote.work, "branch", "--list", "tenon/*") == ""
    assert tree_hashes(repo_with_remote.work) == before


# Plan phase 4: the required-level arguments are public, with the shipped default
# and the deprecated alias intact.
def test_write_pr_exposes_the_required_level_with_safe_defaults():
    parameters = inspect.signature(write_pr).parameters

    assert parameters["required"].default is ProofLevel.TESTS_PASSED
    assert parameters["allow_below_required"].default is False
    assert parameters["allow_unverified"].default is False


# Plan phase 4: `tenon.pr` is the full public surface for the writer.
def test_package_exports_the_full_public_surface():
    from tenon.pr import (
        GitGhRemote,
        PrDraft,
        PrRefusal,
        PrResult,
        PrStatus,
        Remote,
        RemoteError,
        __all__,
        render_pr,
        write_pr,
    )

    assert __all__ == [
        "GitGhRemote",
        "PrDraft",
        "PrRefusal",
        "PrResult",
        "PrStatus",
        "Remote",
        "RemoteError",
        "render_pr",
        "write_pr",
    ]
    assert Remote.__name__ == "Remote"
    assert GitGhRemote.__name__ == "GitGhRemote"
    assert RemoteError.__name__ == "RemoteError"
    assert PrDraft.__name__ == "PrDraft"
    assert PrResult.__name__ == "PrResult"
    assert PrStatus.OPENED.value == "OPENED"
    assert PrRefusal.PR_FAILED.value == "PR_FAILED"
    assert callable(render_pr)
    assert callable(write_pr)
