"""The PR result contract: what was opened, or exactly why nothing was opened."""

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
