"""The proposal result contract: edits, skipped sites and named reasons.

A proposer is duck-typed, not a base class: any callable with the signature
``propose(change, located, root) -> tuple[Edit, ...]``. There is no runtime
``Proposer`` type; assembly belongs to the caller of the rule.
"""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence

from tenon.detect import Change
from tenon.locate import Site, SiteShape


class SkipReason(StrEnum):
    """Why a site is not edited. Ambiguity reasons keep their exact spellings."""

    DYNAMIC_KWARGS = "DYNAMIC_KWARGS"
    DYNAMIC_GETATTR = "DYNAMIC_GETATTR"
    ALIAS_CHAIN = "ALIAS_CHAIN"
    UNROOTED_RECEIVER = "UNROOTED_RECEIVER"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    UNMAPPED_SYMBOL = "UNMAPPED_SYMBOL"
    SHAPE_NOT_EDITABLE = "SHAPE_NOT_EDITABLE"
    STALE_SITE = "STALE_SITE"


class ProposalReason(StrEnum):
    """Why a proposal carries no edits. Set only when ``edits`` is empty."""

    NO_RULE = "NO_RULE"
    NO_CERTAIN_SITES = "NO_CERTAIN_SITES"
    NO_EDITABLE_SITES = "NO_EDITABLE_SITES"
    STALE_SITE = "STALE_SITE"


@dataclass(frozen=True, slots=True)
class Edit:
    """One exact replacement proposed for one located site."""

    path: str
    line: int
    column: int
    shape: SiteShape
    old: str
    new: str

    def __post_init__(self) -> None:
        if not isinstance(self.shape, SiteShape):
            object.__setattr__(self, "shape", SiteShape(self.shape))

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "shape": self.shape.value,
            "old": self.old,
            "new": self.new,
        }


def _edit_key(edit: Edit) -> tuple[str, int, int, str, str]:
    return (edit.path, edit.line, edit.column, edit.shape.value, edit.old)


@dataclass(frozen=True, slots=True)
class Skipped:
    """A located site the proposal refuses to touch, and why."""

    site: Site
    reason: SkipReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, SkipReason):
            object.__setattr__(self, "reason", SkipReason(self.reason))

    def to_dict(self) -> dict[str, object]:
        return {"site": self.site.to_dict(), "reason": self.reason.value}


def _skipped_key(entry: Skipped) -> tuple[str, int, int, str]:
    return (
        entry.site.path,
        entry.site.line,
        entry.site.column,
        entry.reason.value,
    )


@dataclass(frozen=True, slots=True)
class Proposal:
    """The answer for one change: edits, skipped sites, or a named reason."""

    change: Change
    edits: Sequence[Edit]
    skipped: Sequence[Skipped]
    diff: str
    reason: ProposalReason | None = None
    files: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        reason = self.reason
        if reason is not None and not isinstance(reason, ProposalReason):
            reason = ProposalReason(reason)
        edits = tuple(sorted(self.edits, key=_edit_key))
        if edits and reason is not None:
            raise ValueError("a proposal with edits must not carry a reason")
        if not edits and reason is None:
            raise ValueError("an empty proposal must carry a reason")
        if edits and not self.diff:
            raise ValueError("a proposal with edits must carry a diff")
        if not edits and self.diff:
            raise ValueError("an empty proposal must not carry a diff")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "edits", edits)
        object.__setattr__(
            self, "skipped", tuple(sorted(self.skipped, key=_skipped_key))
        )
        object.__setattr__(self, "files", tuple(sorted({edit.path for edit in edits})))

    def to_dict(self) -> dict[str, object]:
        return {
            "change": self.change.to_dict(),
            "edits": [edit.to_dict() for edit in self.edits],
            "skipped": [entry.to_dict() for entry in self.skipped],
            "files": list(self.files),
            "diff": self.diff,
            "reason": None if self.reason is None else self.reason.value,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
