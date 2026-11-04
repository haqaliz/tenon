"""The real adapter builds git/gh arguments; no process and no network runs."""

import os
import subprocess

import pytest

from tenon.pr.remote import GitGhRemote, RemoteError
from tenon.prove import tail


def a_completed(argv=("git",), returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


class FakeRunner:
    """Returns queued results and records every call, like subprocess.run."""

    def __init__(self, *responses):
        self.calls = []
        self.responses = list(responses)

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        response = self.responses.pop(0) if self.responses else a_completed()
        if isinstance(response, BaseException):
            raise response
        return response


# Spec AC9: push is exactly one git command, never forced and never a merge.
def test_push_builds_the_exact_argv_and_env(tmp_path):
    runner = FakeRunner(a_completed())

    GitGhRemote(runner=runner).push(tmp_path, "tenon/renamed-x-12345678")

    argv, kwargs = runner.calls[0]
    assert argv == ["git", "push", "--set-upstream", "origin", "tenon/renamed-x-12345678"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 60
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["PATH"] == os.environ["PATH"]
    assert "--force" not in argv
    assert "merge" not in argv


# Spec AC9: a non-zero push is a RemoteError carrying the capped combined output.
def test_push_rejects_a_non_zero_exit_with_the_capped_tail(tmp_path):
    stderr = "\n".join(f"fatal line {number}" for number in range(1, 26))
    runner = FakeRunner(a_completed(returncode=1, stderr=stderr))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).push(tmp_path, "tenon/x")

    assert raised.value.detail == tail(stderr)
    assert "fatal line 25" in raised.value.detail
    assert "fatal line 5" not in raised.value.detail


# Spec AC9: a long line is capped like every other failure tail.
def test_a_remote_error_caps_a_long_line(tmp_path):
    line = "x" * 3000
    runner = FakeRunner(a_completed(returncode=1, stdout=line))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).push(tmp_path, "tenon/x")

    assert len(raised.value.detail.splitlines()[0]) == 2000


# Spec AC3/AC9: a missing binary is a RemoteError, never an OSError.
def test_a_missing_binary_is_a_remote_error(tmp_path):
    runner = FakeRunner(FileNotFoundError("gh"))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).create_pr(
            tmp_path,
            branch="tenon/x",
            base="main",
            title="[TESTS_PASSED] tenon: x",
            body="body\n",
            draft=False,
        )

    assert "gh" in raised.value.detail


# Spec AC9: a timeout is a RemoteError with a detail.
def test_a_timeout_is_a_remote_error(tmp_path):
    runner = FakeRunner(subprocess.TimeoutExpired(["git", "push"], 60))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).push(tmp_path, "tenon/x")

    assert raised.value.detail


# Spec AC9: create_pr builds the exact argv, sends the body on stdin and no draft.
def test_create_pr_builds_the_exact_argv_and_stdin(tmp_path):
    runner = FakeRunner(
        a_completed(stdout="warning: something\nhttps://github.com/o/r/pull/9\n\n")
    )
    body = "## Tenon proof: TESTS_PASSED\n\nbody\n"

    url = GitGhRemote(runner=runner).create_pr(
        tmp_path,
        branch="tenon/x",
        base="main",
        title="[TESTS_PASSED] tenon: x",
        body=body,
        draft=False,
    )

    argv, kwargs = runner.calls[0]
    assert url == "https://github.com/o/r/pull/9"
    assert argv == [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "tenon/x",
        "--title",
        "[TESTS_PASSED] tenon: x",
        "--body-file",
        "-",
    ]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["input"] == body
    assert kwargs["env"]["GH_PROMPT_DISABLED"] == "1"
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 60
    assert "--draft" not in argv
    assert "merge" not in argv


# Spec AC2/AC9: only an unverified proof asks for a draft PR.
def test_create_pr_adds_the_draft_flag_only_when_asked(tmp_path):
    runner = FakeRunner(a_completed(stdout="https://github.com/o/r/pull/9\n"))

    GitGhRemote(runner=runner).create_pr(
        tmp_path,
        branch="tenon/x",
        base="main",
        title="[UNVERIFIED] tenon: x",
        body="body\n",
        draft=True,
    )

    assert runner.calls[0][0][-1] == "--draft"


# Spec AC9: a non-zero gh is a RemoteError with the tail.
def test_create_pr_rejects_a_non_zero_exit(tmp_path):
    runner = FakeRunner(
        a_completed(returncode=1, stderr="gh: not logged in\n", stdout="")
    )

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).create_pr(
            tmp_path,
            branch="tenon/x",
            base="main",
            title="[TESTS_PASSED] tenon: x",
            body="body\n",
            draft=False,
        )

    assert "not logged in" in raised.value.detail


# Spec AC9: a stdout line that is not a URL cannot become PrResult.url.
def test_create_pr_rejects_an_unparseable_url(tmp_path):
    runner = FakeRunner(a_completed(stdout="opened something\n"))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).create_pr(
            tmp_path,
            branch="tenon/x",
            base="main",
            title="[TESTS_PASSED] tenon: x",
            body="body\n",
            draft=False,
        )

    assert "opened something" in raised.value.detail


# Spec AC8: origin/HEAD is the first and cheapest default-branch source.
def test_default_branch_reads_origin_head(tmp_path):
    runner = FakeRunner(a_completed(stdout="origin/main\n"))

    assert GitGhRemote(runner=runner).default_branch(tmp_path) == "main"
    assert runner.calls[0][0] == [
        "git",
        "symbolic-ref",
        "--short",
        "refs/remotes/origin/HEAD",
    ]


# Spec AC8: when origin/HEAD is absent, ls-remote --symref answers.
def test_default_branch_falls_back_to_ls_remote(tmp_path):
    runner = FakeRunner(
        a_completed(returncode=1, stderr="fatal: no such ref"),
        a_completed(
            stdout="ref: refs/heads/trunk\tHEAD\n8badf00d\tHEAD\n"
        ),
    )

    assert GitGhRemote(runner=runner).default_branch(tmp_path) == "trunk"
    assert runner.calls[1][0] == ["git", "ls-remote", "--symref", "origin", "HEAD"]


# Spec AC8: both failures return the empty string, not a guessed branch.
def test_default_branch_is_empty_when_both_sources_fail(tmp_path):
    runner = FakeRunner(
        a_completed(returncode=1),
        a_completed(returncode=2),
    )

    assert GitGhRemote(runner=runner).default_branch(tmp_path) == ""


# Spec AC6: exit 0 means the branch exists; exit 2 means it does not.
def test_branch_exists_maps_git_exit_codes(tmp_path):
    runner = FakeRunner(a_completed(returncode=0))
    assert GitGhRemote(runner=runner).branch_exists(tmp_path, "tenon/x") is True
    assert runner.calls[0][0] == [
        "git",
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        "tenon/x",
    ]

    runner = FakeRunner(a_completed(returncode=2))
    assert GitGhRemote(runner=runner).branch_exists(tmp_path, "tenon/x") is False


# Spec AC6: any other exit is a RemoteError, never a silent branch decision.
def test_branch_exists_rejects_any_other_exit(tmp_path):
    runner = FakeRunner(a_completed(returncode=1, stderr="fatal: no remote"))

    with pytest.raises(RemoteError) as raised:
        GitGhRemote(runner=runner).branch_exists(tmp_path, "tenon/x")

    assert "no remote" in raised.value.detail
