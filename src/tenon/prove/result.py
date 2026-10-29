"""The proof result contract: what ran, what it returned, and why nothing proved it."""

import json
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

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "command": list(self.command),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass(frozen=True, slots=True)
class ProofResult:
    """The verdict for one proposal: a passed check or one named reason nothing proved."""

    level: ProofLevel
    cause: ProofCause | None = None
    baseline: CheckResult | None = None
    after: CheckResult | None = None
    patch_applied: bool = False

    def __post_init__(self) -> None:
        level = self.level
        if not isinstance(level, ProofLevel):
            level = ProofLevel(level)
        cause = self.cause
        if cause is not None and not isinstance(cause, ProofCause):
            cause = ProofCause(cause)
        if level is ProofLevel.TESTS_PASSED:
            if cause is not None:
                raise ValueError("TESTS_PASSED must not carry a cause")
            if self.after is None or self.after.returncode != 0 or self.after.timed_out:
                raise ValueError("TESTS_PASSED needs a green after check")
            if not self.patch_applied:
                raise ValueError("TESTS_PASSED needs an applied patch")
        elif cause is None:
            raise ValueError("UNVERIFIED must carry a cause")
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "cause", cause)

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level.value,
            "cause": None if self.cause is None else self.cause.value,
            "baseline": None if self.baseline is None else self.baseline.to_dict(),
            "after": None if self.after is None else self.after.to_dict(),
            "patch_applied": self.patch_applied,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )


def tail(text: str, lines: int = 20, chars: int = 2000) -> str:
    """The last ``lines`` lines, each cut to ``chars`` characters, no trailing newline."""
    kept = text.splitlines()[-lines:] if lines > 0 else []
    return "\n".join(line[:chars] for line in kept)
