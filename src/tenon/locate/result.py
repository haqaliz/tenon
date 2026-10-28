"""The locate result contract: sites, ambiguity groups and named reasons."""

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from tenon.detect import Change

_PACKAGE = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")


class SiteShape(StrEnum):
    """How the matched name appears in source. The closed set from PRD M5."""

    CALL = "call"
    KEYWORD = "keyword"
    DICT_KEY = "dict_key"
    ATTRIBUTE = "attribute"


class LocateReason(StrEnum):
    """Why a result has no sites. The closed vocabulary from PRD M7."""

    UNSUPPORTED_CHANGE_KIND = "UNSUPPORTED_CHANGE_KIND"
    NO_SDK_IMPORT = "NO_SDK_IMPORT"
    OPERATION_NOT_MAPPED = "OPERATION_NOT_MAPPED"
    NO_SITES = "NO_SITES"


class AmbiguityReason(StrEnum):
    """Why a group of sites cannot be called certain. PRD M6."""

    DYNAMIC_KWARGS = "DYNAMIC_KWARGS"
    DYNAMIC_GETATTR = "DYNAMIC_GETATTR"
    ALIAS_CHAIN = "ALIAS_CHAIN"
    UNROOTED_RECEIVER = "UNROOTED_RECEIVER"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    UNMAPPED_SYMBOL = "UNMAPPED_SYMBOL"


@dataclass(frozen=True, slots=True)
class Site:
    """One place in the repository a name was found."""

    path: str
    line: int
    column: int
    shape: SiteShape
    symbol: str
    line_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shape, SiteShape):
            object.__setattr__(self, "shape", SiteShape(self.shape))

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "shape": self.shape.value,
            "symbol": self.symbol,
            "line_text": self.line_text,
        }


def _site_key(site: Site) -> tuple[str, int, int, str, str]:
    return (site.path, site.line, site.column, site.symbol, site.shape.value)


@dataclass(frozen=True, slots=True)
class AmbiguousGroup:
    """Sites sharing one reason for doubt. Never resolved by the locator."""

    reason: AmbiguityReason
    symbol: str
    candidates: Sequence[Site]

    def __post_init__(self) -> None:
        if not isinstance(self.reason, AmbiguityReason):
            object.__setattr__(self, "reason", AmbiguityReason(self.reason))
        candidates = tuple(self.candidates)
        if not candidates:
            raise ValueError("an ambiguous group needs at least one candidate")
        object.__setattr__(self, "candidates", tuple(sorted(candidates, key=_site_key)))

    def to_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason.value,
            "symbol": self.symbol,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class LocateResult:
    """The answer for one change: certain sites, ambiguity groups, or a reason."""

    change: Change
    certain: Sequence[Site]
    ambiguous: Sequence[AmbiguousGroup]
    reason: LocateReason | None = None

    def __post_init__(self) -> None:
        reason = self.reason
        if reason is not None and not isinstance(reason, LocateReason):
            reason = LocateReason(reason)
        certain = tuple(sorted(self.certain, key=_site_key))
        ambiguous = tuple(
            sorted(self.ambiguous, key=lambda group: (group.reason.value, group.symbol))
        )
        if reason is None and not certain and not ambiguous:
            raise ValueError("an empty result must carry a reason")
        if reason is not None and (certain or ambiguous):
            raise ValueError("a result with sites must not carry a reason")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "certain", certain)
        object.__setattr__(self, "ambiguous", ambiguous)

    def to_dict(self) -> dict[str, object]:
        return {
            "change": self.change.to_dict(),
            "certain": [site.to_dict() for site in self.certain],
            "ambiguous": [group.to_dict() for group in self.ambiguous],
            "reason": None if self.reason is None else self.reason.value,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )


@dataclass(frozen=True, slots=True)
class LocateConfig:
    """The in-memory API; ``tenon.toml`` is only a convenience."""

    sdk_package: str
    operations: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PACKAGE.fullmatch(self.sdk_package):
            raise ValueError(
                f"sdk_package must be a dotted Python identifier: {self.sdk_package!r}"
            )
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
