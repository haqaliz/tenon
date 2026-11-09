"""The installation lister and the authenticated temp clone, with no network."""

import json

import pytest

from tenon.pr.api import GitHubApi
from tenon.pr.installed import InstalledRepo, list_installation_repos

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
