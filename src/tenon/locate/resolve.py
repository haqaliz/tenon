"""Certainty policy: the one place scan evidence becomes a locate answer.

Every rule that could turn a guess into a certainty lives here, in rule order.
The scanner reports rootedness and dynamics; this module decides which hits are
``certain`` and which remain ``ambiguous`` groups with a named reason.

Aggregation note: any non-empty ``ambiguous`` list maps to the
``AMBIGUOUS_CALL_SITE`` cause in ``docs/technical/ARCHITECTURE.md``. T2 emits the
finer reasons and never that aggregate string itself.
"""

from typing import Sequence

from tenon.detect import Change

from .query import Query
from .result import (
    AmbiguousGroup,
    LocateConfig,
    LocateReason,
    LocateResult,
    Site,
)
from .scan import ScanResult


def resolve(
    change: Change,
    query: Query,
    scan_result: ScanResult,
    config: LocateConfig,
) -> LocateResult:
    """Apply the rule table to one query and its scan evidence."""
    if query.reason is not None:
        return _build(change, reason=query.reason)
    if not scan_result.modules:
        return _build(change, reason=LocateReason.NO_SDK_IMPORT)
    if query.scope == "operation" and query.origin == "none":
        return _build(change, reason=LocateReason.OPERATION_NOT_MAPPED)
    return _build(change, reason=LocateReason.NO_SITES)


def _build(
    change: Change,
    *,
    certain: Sequence[Site] = (),
    groups: Sequence[AmbiguousGroup] = (),
    reason: LocateReason | None = None,
) -> LocateResult:
    """Construct a result, refusing to call the same site certain and doubtful."""
    certain = tuple(certain)
    groups = tuple(groups)
    certain_keys = {_site_key(site) for site in certain}
    for group in groups:
        if any(_site_key(candidate) in certain_keys for candidate in group.candidates):
            raise AssertionError("a site cannot be certain and a candidate")
    return LocateResult(change=change, certain=certain, ambiguous=groups, reason=reason)


def _site_key(site: Site) -> tuple[str, int, int, str, str]:
    return (site.path, site.line, site.column, site.shape.value, site.symbol)
