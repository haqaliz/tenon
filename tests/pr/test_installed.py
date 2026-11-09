"""The installation lister and the authenticated temp clone, with no network."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tenon.pr.api import GitHubApi, GitHubApiError
from tenon.pr.github_app import CREDENTIAL_HELPER
from tenon.pr.installed import InstalledRepo, clone_repo, list_installation_repos
from tenon.pr.remote import RemoteError

API = "https://api.github.com"
TOKEN = "ghs_test"


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


def a_repo(full_name, *, archived=False, clone_url=None):
    return {
        "full_name": full_name,
        "clone_url": clone_url or f"https://github.com/{full_name}.git",
        "archived": archived,
    }


def a_page(*repos):
    return (
        200,
        {},
        json.dumps({"total_count": len(repos), "repositories": list(repos)}),
    )


def a_lister(*responses):
    transport = FakeTransport(*responses)
    return GitHubApi(transport=transport), transport


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


# Spec AC1: one page returns the repos in order with full_name/clone_url.
def test_one_page_lists_the_repositories_in_order():
    api, transport = a_lister(a_page(a_repo("acme/one"), a_repo("acme/two")))

    repos = list_installation_repos(api, TOKEN)

    assert repos == (
        InstalledRepo("acme/one", "https://github.com/acme/one.git"),
        InstalledRepo("acme/two", "https://github.com/acme/two.git"),
    )
    assert len(transport.calls) == 1


# Spec AC1: the lister is one GET of the exact endpoint with the token.
def test_the_listing_request_is_the_exact_endpoint():
    api, transport = a_lister(a_page())

    list_installation_repos(api, TOKEN, per_page=2)

    method, url, headers, body = transport.calls[0]
    assert method == "GET"
    assert url == f"{API}/installation/repositories?per_page=2&page=1"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert body is None


# Spec AC2: a full page continues to the next until a short page.
def test_two_full_pages_are_both_read():
    api, transport = a_lister(
        a_page(a_repo("acme/one"), a_repo("acme/two")),
        a_page(a_repo("acme/three")),
    )

    repos = list_installation_repos(api, TOKEN, per_page=2)

    assert [repo.full_name for repo in repos] == [
        "acme/one",
        "acme/two",
        "acme/three",
    ]
    assert [call[1] for call in transport.calls] == [
        f"{API}/installation/repositories?per_page=2&page=1",
        f"{API}/installation/repositories?per_page=2&page=2",
    ]


# Spec AC2: an empty page stops the walk.
def test_an_empty_page_stops_the_walk():
    api, transport = a_lister(
        a_page(a_repo("acme/one"), a_repo("acme/two")),
        a_page(),
    )

    repos = list_installation_repos(api, TOKEN, per_page=2)

    assert [repo.full_name for repo in repos] == ["acme/one", "acme/two"]
    assert len(transport.calls) == 2


# Spec AC3: archived repos are skipped and the rest keep API order.
def test_archived_repositories_are_skipped_in_order():
    api, _ = a_lister(
        a_page(
            a_repo("acme/one"),
            a_repo("acme/old", archived=True),
            a_repo("acme/two"),
        )
    )

    repos = list_installation_repos(api, TOKEN)

    assert [repo.full_name for repo in repos] == ["acme/one", "acme/two"]


# Spec AC7: the same pages produce the same tuple, with no clock or network.
def test_the_same_pages_produce_the_same_tuple():
    responses = (
        a_page(a_repo("acme/one"), a_repo("acme/two")),
        a_page(a_repo("acme/three")),
    )
    first, _ = a_lister(*responses)
    second, _ = a_lister(*responses)

    assert list_installation_repos(first, TOKEN, per_page=2) == (
        list_installation_repos(second, TOKEN, per_page=2)
    )


# Spec AC4: a page without a repositories list is a named GitHubApiError.
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"repositories": None},
        {"repositories": {}},
        {"repositories": "nope"},
    ],
)
def test_a_missing_or_non_list_repositories_is_a_named_error(payload):
    api, _ = a_lister((200, {}, json.dumps(payload)))

    with pytest.raises(GitHubApiError):
        list_installation_repos(api, TOKEN)


# Spec AC4: a listing item that is not an object is a named GitHubApiError.
@pytest.mark.parametrize("item", ["acme/one", ["acme/one"], None])
def test_a_listing_item_that_is_not_an_object_is_a_named_error(item):
    api, _ = a_lister(
        (200, {}, json.dumps({"total_count": 1, "repositories": [item]}))
    )

    with pytest.raises(GitHubApiError):
        list_installation_repos(api, TOKEN)


# Spec AC4: a non-bool archived flag is a named GitHubApiError.
@pytest.mark.parametrize("archived", [0, 1, "false", None])
def test_a_listing_with_a_non_bool_archived_is_a_named_error(archived):
    item = a_repo("acme/one")
    item["archived"] = archived
    api, _ = a_lister(
        (200, {}, json.dumps({"total_count": 1, "repositories": [item]}))
    )

    with pytest.raises(GitHubApiError):
        list_installation_repos(api, TOKEN)


# Spec AC4: a blank full_name or clone_url is a named GitHubApiError.
@pytest.mark.parametrize("field", ["full_name", "clone_url"])
@pytest.mark.parametrize("value", ["", "  ", None])
def test_a_listing_with_a_blank_field_is_a_named_error(field, value):
    item = a_repo("acme/one")
    item[field] = value
    api, _ = a_lister(
        (200, {}, json.dumps({"total_count": 1, "repositories": [item]}))
    )

    with pytest.raises(GitHubApiError) as raised:
        list_installation_repos(api, TOKEN)

    assert field in raised.value.detail


# Spec AC4: an API failure stays the named GitHubApiError with its status.
def test_a_listing_api_error_is_a_named_github_api_error():
    api, _ = a_lister((500, {}, json.dumps({"message": "boom"})))

    with pytest.raises(GitHubApiError) as raised:
        list_installation_repos(api, TOKEN)

    assert raised.value.status == 500
    assert "boom" in raised.value.detail


# Spec AC2: 100 full pages without a short one is a named error, not a loop.
def test_the_page_cap_is_a_named_error():
    full_page = a_page(a_repo("acme/one"), a_repo("acme/two"))
    api, transport = a_lister(*([full_page] * 100))

    with pytest.raises(GitHubApiError) as raised:
        list_installation_repos(api, TOKEN, per_page=2)

    assert len(transport.calls) == 100
    assert "100" in raised.value.detail


# Spec AC1: InstalledRepo keeps exactly two non-empty strings.
@pytest.mark.parametrize(
    "full_name, clone_url",
    [
        ("", "https://github.com/acme/one.git"),
        ("  ", "https://github.com/acme/one.git"),
        ("acme/one", ""),
        ("acme/one", "  "),
        (None, "https://github.com/acme/one.git"),
        ("acme/one", None),
    ],
)
def test_an_installed_repo_refuses_blank_fields(full_name, clone_url):
    with pytest.raises(ValueError):
        InstalledRepo(full_name, clone_url)


# Spec AC5: a real clone lands the fixture files and is removed on exit.
def test_a_real_clone_lands_the_repo_and_is_removed_on_exit(repo_with_remote):
    repo = InstalledRepo("acme/widgets", str(repo_with_remote.work))

    with clone_repo(repo, TOKEN) as checkout:
        assert checkout.name.startswith("tenon-installed-")
        assert (checkout / "acme" / "client.py").is_file()
        assert (checkout / ".git").is_dir()

    assert not checkout.exists()


# Spec AC5/AC6: the argv carries the helper and URL, never the token; the token
# is only in the child env.
def test_the_clone_argv_and_env_carry_no_token_in_argv():
    runner = FakeRunner()
    repo = InstalledRepo("acme/widgets", "https://github.com/acme/widgets.git")

    with clone_repo(repo, TOKEN, runner=runner) as checkout:
        argv, kwargs = runner.calls[0]
        assert argv == [
            "git",
            "-c",
            f"credential.helper={CREDENTIAL_HELPER}",
            "clone",
            "--depth",
            "1",
            "--",
            repo.clone_url,
            str(checkout),
        ]
        assert TOKEN not in " ".join(argv)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 30
        assert kwargs["env"]["TENON_GITHUB_TOKEN"] == TOKEN
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["env"]["PATH"] == os.environ["PATH"]


# Spec AC6: a failing clone names the repo and removes the temp dir.
def test_a_failing_clone_names_the_repo_and_removes_the_dir():
    runner = FakeRunner(
        a_completed(returncode=128, stderr="fatal: repository not found\n")
    )
    repo = InstalledRepo("acme/widgets", "https://github.com/acme/widgets.git")

    with pytest.raises(RemoteError) as raised:
        with clone_repo(repo, TOKEN, runner=runner):
            pass

    argv, _ = runner.calls[0]
    assert repo.full_name in raised.value.detail
    assert "repository not found" in raised.value.detail
    assert not Path(argv[-1]).exists()


# Spec AC6: a missing clone URL is a named RemoteError and the dir is removed.
def test_a_missing_clone_url_is_a_named_error_and_removes_the_dir(
    tmp_path, monkeypatch
):
    created = []

    def a_mkdtemp(prefix):
        path = tmp_path / f"{prefix}{len(created)}"
        path.mkdir()
        created.append(path)
        return str(path)

    monkeypatch.setattr("tenon.pr.installed.tempfile.mkdtemp", a_mkdtemp)
    repo = InstalledRepo("acme/widgets", str(tmp_path / "missing"))

    with pytest.raises(RemoteError) as raised:
        with clone_repo(repo, TOKEN):
            pass

    assert repo.full_name in raised.value.detail
    assert created and not created[0].exists()


# Spec AC6: the token in the git stderr is scrubbed, never returned.
def test_a_clone_failure_scrubs_the_token():
    runner = FakeRunner(
        a_completed(
            returncode=128,
            stderr=(
                "fatal: unable to access "
                f"'https://x-access-token:{TOKEN}@github.com/acme/widgets.git'\n"
            ),
        )
    )
    repo = InstalledRepo("acme/widgets", "https://github.com/acme/widgets.git")

    with pytest.raises(RemoteError) as raised:
        with clone_repo(repo, TOKEN, runner=runner):
            pass

    assert TOKEN not in raised.value.detail
    assert "***" in raised.value.detail


# Spec AC6: a timeout or OSError is a named RemoteError and still cleans up.
@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired(["git"], 30), OSError("boom")],
    ids=["timeout", "oserror"],
)
def test_a_clone_that_cannot_run_is_a_named_error(failure):
    runner = FakeRunner(failure)
    repo = InstalledRepo("acme/widgets", "https://github.com/acme/widgets.git")

    with pytest.raises(RemoteError) as raised:
        with clone_repo(repo, TOKEN, runner=runner):
            pass

    argv, _ = runner.calls[0]
    assert repo.full_name in raised.value.detail
    assert not Path(argv[-1]).exists()
