"""The host seam: default branch, branch existence, push and PR creation.

No merge, no force and no delete: every operation here only adds a branch or a
pull request. The concrete adapter lands with the push and PR phases.
"""

from pathlib import Path
from typing import Protocol


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
