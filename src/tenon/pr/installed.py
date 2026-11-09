"""Discover the app installation's repositories and clone them with its token."""

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .api import GitHubApi, GitHubApiError
from .github_app import CREDENTIAL_HELPER
from .remote import RemoteError

_ENDPOINT = "/installation/repositories"
_PAGE_CAP = 100


@dataclass(frozen=True, slots=True)
class InstalledRepo:
    """One repository in the installation, named for the report and cloned by URL."""

    full_name: str
    clone_url: str

    def __post_init__(self) -> None:
        for value in (self.full_name, self.clone_url):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("installed repo fields must be non-empty strings")


def _listing(payload: dict, page: int) -> list:
    items = payload.get("repositories")
    if not isinstance(items, list):
        raise GitHubApiError(
            f"GET {_ENDPOINT} page {page} returned no repositories list"
        )
    return items


def _installed(item, page: int) -> InstalledRepo | None:
    if not isinstance(item, dict):
        raise GitHubApiError(
            f"GET {_ENDPOINT} page {page} has a repository that is not an object"
        )
    archived = item.get("archived")
    if not isinstance(archived, bool):
        raise GitHubApiError(
            f"GET {_ENDPOINT} page {page} has a non-bool archived flag"
        )
    values = {}
    for field in ("full_name", "clone_url"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise GitHubApiError(
                f"GET {_ENDPOINT} page {page} has a blank {field}"
            )
        values[field] = value
    if archived:
        return None
    return InstalledRepo(values["full_name"], values["clone_url"])


def list_installation_repos(
    api: GitHubApi, token: str, *, per_page: int = 100
) -> tuple[InstalledRepo, ...]:
    repos = []
    for page in range(1, _PAGE_CAP + 1):
        payload = api.request(
            "GET",
            f"{_ENDPOINT}?per_page={per_page}&page={page}",
            token,
        )
        batch = _listing(payload, page)
        for item in batch:
            repo = _installed(item, page)
            if repo is not None:
                repos.append(repo)
        if len(batch) < per_page:
            return tuple(repos)
    raise GitHubApiError(
        f"GET {_ENDPOINT} did not finish within {_PAGE_CAP} pages"
    )


@contextmanager
def clone_repo(
    repo: InstalledRepo,
    token: str,
    *,
    runner=None,
    timeout: float = 30,
) -> Iterator[Path]:
    """Clone ``repo`` into a temp dir with the token in the child env only."""
    try:
        tmp = Path(tempfile.mkdtemp(prefix="tenon-installed-"))
    except OSError as exc:
        raise RemoteError(
            f"could not clone {repo.full_name}: {type(exc).__name__}"
        ) from exc
    try:
        try:
            completed = (runner or subprocess.run)(
                [
                    "git",
                    "-c",
                    # A helper is a config value, so the -c argument needs its key.
                    f"credential.helper={CREDENTIAL_HELPER}",
                    "clone",
                    "--depth",
                    "1",
                    "--",
                    repo.clone_url,
                    str(tmp),
                ],
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout,
                env={
                    **os.environ,
                    "TENON_GITHUB_TOKEN": token,
                    "GIT_TERMINAL_PROMPT": "0",
                },
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise RemoteError(
                f"could not clone {repo.full_name}: {type(exc).__name__}"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            if token:
                detail = detail.replace(token, "***")
            message = f"could not clone {repo.full_name}"
            raise RemoteError(f"{message}: {detail}" if detail else message)
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
