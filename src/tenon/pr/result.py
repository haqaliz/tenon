"""The PR result contract: what was opened, or exactly why nothing was opened."""

import json
from dataclasses import dataclass
from enum import StrEnum

from tenon.prove import ProofLevel


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
    REMOTE_CHECK_FAILED = "REMOTE_CHECK_FAILED"
    UNVERIFIED_NOT_ALLOWED = "UNVERIFIED_NOT_ALLOWED"
    BELOW_REQUIRED_LEVEL = "BELOW_REQUIRED_LEVEL"
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


@dataclass(frozen=True, slots=True)
class PrResult:
    """The answer for one PR write: opened with a URL, or refused with a reason."""

    status: PrStatus
    level: ProofLevel
    draft: PrDraft
    url: str | None = None
    refusal: PrRefusal | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        status = self.status
        if not isinstance(status, PrStatus):
            status = PrStatus(status)
        level = self.level
        if not isinstance(level, ProofLevel):
            level = ProofLevel(level)
        refusal = self.refusal
        if refusal is not None and not isinstance(refusal, PrRefusal):
            refusal = PrRefusal(refusal)
        if status is PrStatus.OPENED:
            if not isinstance(self.url, str) or not self.url:
                raise ValueError("OPENED needs a non-empty url")
            if refusal is not None:
                raise ValueError("OPENED must not carry a refusal")
            if self.detail:
                raise ValueError("OPENED must not carry detail")
        else:
            if refusal is None:
                raise ValueError("REFUSED must carry a refusal")
            if self.url is not None:
                raise ValueError("REFUSED must not carry a url")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "refusal", refusal)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "level": self.level.value,
            "draft": self.draft.to_dict(),
            "url": self.url,
            "refusal": None if self.refusal is None else self.refusal.value,
            "detail": self.detail,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

