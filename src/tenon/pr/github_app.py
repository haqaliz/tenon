"""The GitHub App remote: the host seam under an installation identity."""

import re
import subprocess
from pathlib import Path

from .api import GitHubApi, GitHubApiError
from .remote import RemoteError

_ORIGIN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)([^/\s]+)/([^/\s]+?)(?:\.git)?$"
)


class GitHubAppRemote:
    """The four host operations as the app; the token never enters argv."""

    def __init__(
        self,
        token_provider,
        api_url: str = "https://api.github.com",
        transport=None,
        runner=None,
        timeout: float = 30,
    ) -> None:
        self._token_provider = token_provider
        self._api = GitHubApi(api_url=api_url, transport=transport, timeout=timeout)
        self._runner = runner or subprocess.run
        self._timeout = timeout
        self._installation_token: str | None = None

    def _token(self) -> str:
        if self._installation_token is None:
            try:
                self._installation_token = self._token_provider.token()
            except RemoteError:
                raise
            except Exception as exc:
                raise RemoteError(
                    f"could not mint the installation token: {type(exc).__name__}"
                ) from exc
        return self._installation_token

    def _invoke(self, argv, *, repo: str | Path) -> subprocess.CompletedProcess:
        try:
            return self._runner(
                list(argv),
                cwd=repo,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteError(str(exc)) from exc
        except OSError as exc:
            raise RemoteError(str(exc)) from exc

    def _owner_repo(self, repo: str | Path) -> tuple[str, str]:
        completed = self._invoke(["git", "remote", "get-url", "origin"], repo=repo)
        if completed.returncode != 0:
            raise RemoteError(
                completed.stderr or completed.stdout or "no origin remote"
            )
        match = _ORIGIN.match(completed.stdout.strip())
        if match is None:
            raise RemoteError("origin is not a GitHub HTTPS or SSH URL")
        return match.group(1), match.group(2)

    def default_branch(self, repo: str | Path) -> str:
        owner, name = self._owner_repo(repo)
        payload = self._api.request("GET", f"/repos/{owner}/{name}", self._token())
        branch = payload.get("default_branch")
        if not isinstance(branch, str) or not branch:
            raise RemoteError(f"{owner}/{name} has no default branch")
        return branch

    def branch_exists(self, repo: str | Path, branch: str) -> bool:
        owner, name = self._owner_repo(repo)
        try:
            self._api.request(
                "GET",
                f"/repos/{owner}/{name}/git/ref/heads/{branch}",
                self._token(),
            )
        except GitHubApiError as exc:
            if exc.status == 404:
                return False
            raise
        return True
