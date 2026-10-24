"""The typed change record: the unit every downstream stage consumes."""

import copy
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

# JSON Pointer in URI-fragment form, as every PRD example writes it: "#/paths/~1users".
_POINTER = re.compile(r"#(?:/(?:[^~]|~[01])*)*")


class ChangeKind(StrEnum):
    """The closed taxonomy from PRD M2. Adding one is a contract change."""

    ENDPOINT_REMOVED = "endpoint_removed"
    ENDPOINT_ADDED = "endpoint_added"
    PARAMETER_REMOVED = "parameter_removed"
    PARAMETER_REQUIRED_ADDED = "parameter_required_added"
    PARAMETER_TYPE_CHANGED = "parameter_type_changed"
    PROPERTY_REMOVED = "property_removed"
    PROPERTY_ADDED = "property_added"
    PROPERTY_REQUIRED_ADDED = "property_required_added"
    PROPERTY_TYPE_CHANGED = "property_type_changed"
    ENUM_NARROWED = "enum_narrowed"
    SCHEMA_REMOVED = "schema_removed"
    SCHEMA_ADDED = "schema_added"
    RENAMED = "renamed"


@dataclass(frozen=True, slots=True)
class Location:
    """Where the change lives in the new document.

    ``pointer`` addresses the enclosing container, since a removed item does not
    exist in the new document.
    """

    pointer: str
    method: str | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        if not _POINTER.fullmatch(self.pointer):
            raise ValueError(f"not an RFC 6901 fragment pointer: {self.pointer!r}")

    def to_dict(self) -> dict[str, object]:
        return {"method": self.method, "path": self.path, "pointer": self.pointer}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Location":
        return cls(method=data["method"], path=data["path"], pointer=str(data["pointer"]))


@dataclass(frozen=True, slots=True)
class Change:
    """One detected change. No patch, no severity, no prose: T3 owns those."""

    kind: ChangeKind
    location: Location
    before: Any = None
    after: Any = None
    breaking: bool = False
    confidence: Literal["certain", "inferred"] = "certain"

    def __post_init__(self) -> None:
        # A caller mutating the dict it passed in must not alter a built record.
        object.__setattr__(self, "before", copy.deepcopy(self.before))
        object.__setattr__(self, "after", copy.deepcopy(self.after))

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "location": self.location.to_dict(),
            "before": copy.deepcopy(self.before),
            "after": copy.deepcopy(self.after),
            "breaking": self.breaking,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Change":
        return cls(
            kind=ChangeKind(data["kind"]),
            location=Location.from_dict(data["location"]),
            before=data["before"],
            after=data["after"],
            breaking=bool(data["breaking"]),
            confidence=data["confidence"],
        )


class RefusalCode(StrEnum):
    """The closed refusal vocabulary from PRD M7."""

    NOT_A_SPEC = "NOT_A_SPEC"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNPARSEABLE = "UNPARSEABLE"
    UNRESOLVED_REF = "UNRESOLVED_REF"
    EXTERNAL_REF = "EXTERNAL_REF"
    UNSUPPORTED_COMPOSITION = "UNSUPPORTED_COMPOSITION"


class SpecRefusal(Exception):
    """A named refusal. The only error ``load``/``diff`` may raise for bad input.

    ``pointer`` is None for UNPARSEABLE, whose line/column lives in ``message``.
    """

    def __init__(
        self, code: RefusalCode, pointer: str | None = None, *, message: str
    ) -> None:
        if not isinstance(code, RefusalCode):
            raise TypeError(f"code must be a RefusalCode, got {code!r}")
        if pointer is not None and not _POINTER.fullmatch(pointer):
            raise ValueError(f"not an RFC 6901 fragment pointer: {pointer!r}")
        self.code = code
        self.pointer = pointer
        self.message = message
        super().__init__(self._render())

    def _render(self) -> str:
        where = f" at {self.pointer}" if self.pointer is not None else ""
        return f"{self.code.value}{where}: {self.message}"
