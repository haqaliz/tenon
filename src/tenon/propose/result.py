"""The proposal result contract: edits, skipped sites and named reasons.

A proposer is duck-typed, not a base class: any callable with the signature
``propose(change, located, root) -> tuple[Edit, ...]``. There is no runtime
``Proposer`` type; assembly belongs to the caller of the rule.
"""

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


@dataclass(frozen=True, slots=True)
class Skipped:
    """A located site the proposal refuses to touch, and why."""

    site: Site
    reason: SkipReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, SkipReason):
            object.__setattr__(self, "reason", SkipReason(self.reason))


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
        edits = tuple(self.edits)
        object.__setattr__(self, "edits", edits)
        object.__setattr__(self, "skipped", tuple(self.skipped))
        object.__setattr__(self, "files", tuple(sorted({edit.path for edit in edits})))
