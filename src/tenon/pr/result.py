"""The PR result contract: what was opened, or exactly why nothing was opened."""

import json
from dataclasses import dataclass
from enum import StrEnum


class PrStatus(StrEnum):
    """The two answers a PR write can give."""

    OPENED = "OPENED"
    REFUSED = "REFUSED"


class PrRefusal(StrEnum):
    """Why nothing was opened. The closed vocabulary from the aspect spec."""

    NOT_A_GIT_REPO = "NOT_A_GIT_REPO"
    DIRTY_CHECKOUT = "DIRTY_CHECKOUT"
    NO_REMOTE = "NO_REMOTE"
    UNKNOWN_DEFAULT_BRANCH = "UNKNOWN_DEFAULT_BRANCH"
    NO_PATCH = "NO_PATCH"
    DEFAULT_BRANCH = "DEFAULT_BRANCH"
    BRANCH_EXISTS = "BRANCH_EXISTS"
    UNVERIFIED_NOT_ALLOWED = "UNVERIFIED_NOT_ALLOWED"
    PATCH_DID_NOT_APPLY = "PATCH_DID_NOT_APPLY"
    COPY_FAILED = "COPY_FAILED"
    COMMIT_FAILED = "COMMIT_FAILED"
    PUSH_FAILED = "PUSH_FAILED"
    PR_FAILED = "PR_FAILED"


@dataclass(frozen=True, slots=True)
class PrDraft:
    """The deterministic text a PR write would ship."""

    title: str
    body: str
    branch: str
    commit_message: str

    def __post_init__(self) -> None:
        for name in ("title", "body", "branch", "commit_message"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string: {value!r}")

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "body": self.body,
            "branch": self.branch,
            "commit_message": self.commit_message,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

