"""The host seam: default branch, branch existence, push and PR creation.

No merge, no force and no delete: every operation here only adds a branch or a
pull request.
"""

import os
import subprocess
from pathlib import Path
from typing import Protocol

from tenon.prove import tail


class RemoteError(Exception):
    """One host operation failed; the writer maps it to that operation."""

    def __init__(self, detail: str) -> None:
        self.detail = tail(detail)
        super().__init__(self.detail)


class Remote(Protocol):
    """The four host operations the writer needs, and nothing more."""

    def default_branch(self, repo: str | Path) -> str: ...

    def branch_exists(self, repo: str | Path, branch: str) -> bool: ...

    def push(self, repo: str | Path, branch: str) -> None: ...

    def create_pr(
        self,
        repo: str | Path,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
        draft: bool,
    ) -> str: ...


def _output(completed: subprocess.CompletedProcess) -> str:
    return "\n".join(
        part for part in (completed.stdout, completed.stderr) if part
    )


class GitGhRemote:
    """Run the user's own ``git`` and ``gh``; never prompt, never force."""

    def __init__(self, runner=subprocess.run, timeout: float = 60) -> None:
        self._runner = runner
        self._timeout = timeout

    def _invoke(
        self,
        argv,
        *,
        repo: str | Path,
        input: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        try:
            return self._runner(
                list(argv),
                cwd=repo,
                input=input,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
                env={**os.environ, **(env or {})},
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteError(str(exc)) from exc
        except OSError as exc:
            raise RemoteError(str(exc)) from exc

    def default_branch(self, repo: str | Path) -> str:
        try:
            direct = self._invoke(
                ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                repo=repo,
            )
        except RemoteError:
            direct = None
        if direct is not None and direct.returncode == 0:
            name = direct.stdout.strip()
            if name.startswith("origin/"):
                name = name[len("origin/") :]
            if name:
                return name

        try:
            remote = self._invoke(
                ["git", "ls-remote", "--symref", "origin", "HEAD"], repo=repo
            )
        except RemoteError:
            return ""
        if remote.returncode != 0:
            return ""
        prefix = "ref: refs/heads/"
        for line in remote.stdout.splitlines():
            if line.startswith(prefix):
                name, _, head = line[len(prefix) :].partition("\t")
                if name and head == "HEAD":
                    return name
        return ""

    def branch_exists(self, repo: str | Path, branch: str) -> bool:
        completed = self._invoke(
            ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
            repo=repo,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 2:
            return False
        raise RemoteError(_output(completed))

    def push(self, repo: str | Path, branch: str) -> None:
        completed = self._invoke(
            ["git", "push", "--set-upstream", "origin", branch],
            repo=repo,
            env={"GIT_TERMINAL_PROMPT": "0"},
        )
        if completed.returncode != 0:
            raise RemoteError(_output(completed))

    def create_pr(
        self,
        repo: str | Path,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
        draft: bool,
    ) -> str:
        argv = [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        if draft:
            argv.append("--draft")
        completed = self._invoke(
            argv,
            repo=repo,
            input=body,
            env={"GH_PROMPT_DISABLED": "1"},
        )
        if completed.returncode != 0:
            raise RemoteError(_output(completed))
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        url = lines[-1] if lines else ""
        if not url.startswith("http"):
            raise RemoteError(_output(completed) or "gh did not print a PR URL")
        return url
