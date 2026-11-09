"""Discover the app installation's repositories and clone them with its token."""

from dataclasses import dataclass

from .api import GitHubApi


@dataclass(frozen=True, slots=True)
class InstalledRepo:
    """One repository in the installation, named for the report and cloned by URL."""

    full_name: str
    clone_url: str

    def __post_init__(self) -> None:
        for value in (self.full_name, self.clone_url):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("installed repo fields must be non-empty strings")


def list_installation_repos(
    api: GitHubApi, token: str, *, per_page: int = 100
) -> tuple[InstalledRepo, ...]:
    repos = []
    page = 1
    while True:
        payload = api.request(
            "GET",
            f"/installation/repositories?per_page={per_page}&page={page}",
            token,
        )
        batch = payload["repositories"]
        for item in batch:
            if item["archived"]:
                continue
            repos.append(InstalledRepo(item["full_name"], item["clone_url"]))
        if len(batch) < per_page:
            return tuple(repos)
        page += 1
