"""The app remote: parse, read, push and open PRs with no process or network."""

import json
import os
import subprocess

import pytest

from tenon.pr.app import StaticToken
from tenon.pr.github_app import GitHubAppRemote
from tenon.pr.remote import RemoteError

API = "https://api.github.com"
TOKEN = "ghs_installation"
ORIGIN = "https://github.com/acme/widgets.git"


def a_completed(argv=("git",), returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


class FakeRunner:
    """Returns queued results and records every call, like subprocess.run."""

    def __init__(self, *responses, default=None):
        self.calls = []
        self.responses = list(responses)
        self.default = default if default is not None else a_completed()

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        response = self.responses.pop(0) if self.responses else self.default
        if isinstance(response, BaseException):
            raise response
        return response


class FakeTransport:
    """Records every call and returns queued ``(status, headers, body)``."""

    def __init__(self, *responses):
        self.calls = []
        self.responses = list(responses)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class CountingToken:
    def __init__(self, value=TOKEN):
        self.value = value
        self.calls = 0

    def token(self):
        self.calls += 1
        return self.value


def a_remote(*responses, origin=ORIGIN, token=TOKEN, provider=None):
    """The remote, its recording runner and transport."""
    runner = FakeRunner(default=a_completed(stdout=origin))
    transport = FakeTransport(*responses)
    remote = GitHubAppRemote(
        provider or StaticToken(token),
        transport=transport,
        runner=runner,
    )
    return remote, runner, transport


# Spec AC1: both GitHub origin forms, with and without ``.git``, parse.
@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/acme/widgets",
        "https://github.com/acme/widgets.git",
        "git@github.com:acme/widgets",
        "git@github.com:acme/widgets.git",
        "https://github.com/acme/widgets.git\n",
    ],
)
def test_a_github_origin_parses_to_owner_and_repo(origin, tmp_path):
    remote, runner, _ = a_remote(origin=origin)

    assert remote._owner_repo(tmp_path) == ("acme", "widgets")
    argv, kwargs = runner.calls[0]
    assert argv == ["git", "remote", "get-url", "origin"]
    assert kwargs["cwd"] == tmp_path


# Spec AC1: a non-GitHub, relative or incomplete URL is a RemoteError.
@pytest.mark.parametrize(
    "origin",
    [
        "https://gitlab.com/acme/widgets.git",
        "git@gitlab.com:acme/widgets.git",
        "../widgets",
        "/tmp/widgets",
        "file:///tmp/widgets",
        "https://github.com/acme",
    ],
)
def test_a_non_github_or_relative_origin_is_a_remote_error(origin, tmp_path):
    remote, _, _ = a_remote(origin=origin)

    with pytest.raises(RemoteError):
        remote._owner_repo(tmp_path)


# Spec AC1: a clone without a readable origin is a RemoteError.
def test_a_failed_origin_command_is_a_remote_error(tmp_path):
    remote, runner, _ = a_remote()
    runner.responses.append(a_completed(returncode=1, stderr="fatal: no such remote"))

    with pytest.raises(RemoteError) as raised:
        remote._owner_repo(tmp_path)

    assert "no such remote" in raised.value.detail


# Spec AC2: default_branch is one GET of the exact repo path with the bearer token.
def test_default_branch_reads_the_exact_repo_endpoint(tmp_path):
    remote, _, transport = a_remote(
        (200, {}, json.dumps({"default_branch": "main"}))
    )

    assert remote.default_branch(tmp_path) == "main"

    method, url, headers, body = transport.calls[0]
    assert method == "GET"
    assert url == f"{API}/repos/acme/widgets"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert body is None


# Spec AC2: a response without a default branch is a RemoteError, not a guess.
def test_a_missing_default_branch_is_a_remote_error(tmp_path):
    remote, _, _ = a_remote((200, {}, json.dumps({"name": "widgets"})))

    with pytest.raises(RemoteError):
        remote.default_branch(tmp_path)


# Spec AC2: the branch check uses the exact ref path; 200 means True.
def test_branch_exists_is_true_on_200(tmp_path):
    remote, _, transport = a_remote((200, {}, json.dumps({"ref": "refs/heads/x"})))

    assert remote.branch_exists(tmp_path, "tenon/x") is True
    assert (
        transport.calls[0][1]
        == f"{API}/repos/acme/widgets/git/ref/heads/tenon/x"
    )


# Spec AC2: a 404 means the branch does not exist.
def test_branch_exists_is_false_on_404(tmp_path):
    remote, _, _ = a_remote((404, {}, json.dumps({"message": "Not Found"})))

    assert remote.branch_exists(tmp_path, "tenon/x") is False


# Spec AC2: any other API failure is a RemoteError, never a branch decision.
def test_a_failed_branch_check_is_a_remote_error(tmp_path):
    remote, _, _ = a_remote((500, {}, json.dumps({"message": "boom"})))

    with pytest.raises(RemoteError) as raised:
        remote.branch_exists(tmp_path, "tenon/x")

    assert "HTTP 500" in raised.value.detail


# Spec AC6: one installation token per remote instance, reused by every call.
def test_the_installation_token_is_minted_once(tmp_path):
    provider = CountingToken()
    remote, _, transport = a_remote(
        (200, {}, json.dumps({"default_branch": "main"})),
        (200, {}, json.dumps({"ref": "refs/heads/x"})),
        provider=provider,
    )

    remote.default_branch(tmp_path)
    remote.branch_exists(tmp_path, "tenon/x")

    assert provider.calls == 1
    assert [call[2]["Authorization"] for call in transport.calls] == [
        f"Bearer {TOKEN}",
        f"Bearer {TOKEN}",
    ]


# Spec AC6: a mint failure is a RemoteError and no request is made.
def test_a_token_mint_failure_is_a_remote_error(tmp_path):
    class FailingToken:
        def token(self):
            raise RemoteError("mint failed")

    remote, _, transport = a_remote(provider=FailingToken())

    with pytest.raises(RemoteError) as raised:
        remote.default_branch(tmp_path)

    assert raised.value.detail == "mint failed"
    assert transport.calls == []


# Spec AC6: an unexpected provider failure is still a RemoteError, with no
# provider message copied into the detail.
def test_an_unexpected_token_failure_is_a_remote_error(tmp_path):
    class FailingToken:
        def token(self):
            raise OSError("down")

    remote, _, transport = a_remote(provider=FailingToken())

    with pytest.raises(RemoteError) as raised:
        remote.default_branch(tmp_path)

    assert "OSError" in raised.value.detail
    assert "down" not in raised.value.detail
    assert transport.calls == []


HELPER = (
    '!f() { echo "username=x-access-token"; '
    'echo "password=$TENON_GITHUB_TOKEN"; }; f'
)


# Spec AC3/AC7: push is exactly one git command with the credential helper and
# the branch, no token in argv, no force, and the token only in the env.
def test_push_builds_the_exact_argv_and_env(tmp_path):
    remote, runner, _ = a_remote()

    remote.push(tmp_path, "tenon/x")

    argv, kwargs = runner.calls[0]
    assert argv == ["git", "-c", HELPER, "push", "origin", "tenon/x"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 30
    assert kwargs["env"]["TENON_GITHUB_TOKEN"] == TOKEN
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["PATH"] == os.environ["PATH"]
    assert TOKEN not in " ".join(argv)
    assert "--force" not in argv
    assert "-f" not in argv
    assert "merge" not in argv


# Spec AC3: a non-zero push is a RemoteError carrying the stderr tail.
def test_a_push_failure_is_a_remote_error_with_the_stderr_tail(tmp_path):
    remote, runner, _ = a_remote()
    runner.responses.append(
        a_completed(returncode=1, stderr="fatal: could not push\n")
    )

    with pytest.raises(RemoteError) as raised:
        remote.push(tmp_path, "tenon/x")

    assert "fatal: could not push" in raised.value.detail


# Spec AC4/AC7: the token in the git output is redacted, never returned.
def test_a_push_failure_redacts_the_token(tmp_path):
    remote, runner, _ = a_remote()
    runner.responses.append(
        a_completed(
            returncode=1,
            stderr=(
                "fatal: unable to access "
                f"https://x-access-token:{TOKEN}@github.com/acme/widgets.git\n"
            ),
        )
    )

    with pytest.raises(RemoteError) as raised:
        remote.push(tmp_path, "tenon/x")

    assert TOKEN not in raised.value.detail
    assert "***" in raised.value.detail
