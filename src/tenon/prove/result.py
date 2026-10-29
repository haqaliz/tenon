"""The proof result contract: what ran, what it returned, and why nothing proved it."""

from dataclasses import dataclass
from enum import StrEnum


class ProofLevel(StrEnum):
    """The strongest statement this card can make. The rest of the ladder is T7."""

    TESTS_PASSED = "TESTS_PASSED"
    UNVERIFIED = "UNVERIFIED"


class ProofCause(StrEnum):
    """Why no check proved the patch. The closed vocabulary from PRD M8."""

    NO_PATCH_PROPOSED = "NO_PATCH_PROPOSED"
    PATCH_DID_NOT_APPLY = "PATCH_DID_NOT_APPLY"
    NO_TESTS_FOUND = "NO_TESTS_FOUND"
    TESTS_FAILED_BEFORE = "TESTS_FAILED_BEFORE"
    TESTS_FAILED_AFTER = "TESTS_FAILED_AFTER"
    CHECK_TIMED_OUT = "CHECK_TIMED_OUT"
    COPY_FAILED = "COPY_FAILED"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One command run in the copy, before or after the patch."""

    kind: str
    command: tuple[str, ...]
    returncode: int | None
    timed_out: bool
    stdout_tail: str = ""
    stderr_tail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("baseline", "after"):
            raise ValueError(f"kind must be baseline or after: {self.kind!r}")
        object.__setattr__(self, "command", tuple(self.command))


def tail(text: str, lines: int = 20, chars: int = 2000) -> str:
    """The last ``lines`` lines, each cut to ``chars`` characters, no trailing newline."""
    kept = text.splitlines()[-lines:] if lines > 0 else []
    return "\n".join(line[:chars] for line in kept)
