"""Certainty policy: the one place scan evidence becomes a locate answer.

Every rule that could turn a guess into a certainty lives here, in rule order.
The scanner reports rootedness and dynamics; this module decides which hits are
``certain`` and which remain ``ambiguous`` groups with a named reason.

Aggregation note: any non-empty ``ambiguous`` list maps to the
``AMBIGUOUS_CALL_SITE`` cause in ``docs/technical/ARCHITECTURE.md``. T2 emits the
finer reasons and never that aggregate string itself.
"""

from typing import Iterable, Sequence

from tenon.detect import Change

from .query import Query
from .result import (
    AmbiguityReason,
    AmbiguousGroup,
    LocateConfig,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
)
from .scan import DynamicKind, Hit, ScanResult

_FIELD_SHAPES = (SiteShape.KEYWORD, SiteShape.DICT_KEY)


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
    if query.scope == "operation":
        return _resolve_operation(change, query, scan_result)
    return _build(change, reason=LocateReason.NO_SITES)


def _resolve_operation(
    change: Change, query: Query, scan_result: ScanResult
) -> LocateResult:
    """Rules for an endpoint or a field under one operation."""
    if query.origin == "none":
        return _build(change, reason=LocateReason.OPERATION_NOT_MAPPED)
    calls = _operation_calls(query, scan_result)
    if len(calls) >= 2:
        group = AmbiguousGroup(
            AmbiguityReason.MULTIPLE_CANDIDATES,
            _operation_symbol(query),
            _unique(
                _site(hit) for hits in calls.values() for hit in hits
            ),
        )
        return _build(change, groups=(group,))
    if not calls:
        groups = _getattr_groups(_candidate_leaves(query), scan_result)
        if groups:
            return _build(change, groups=groups)
        return _build(change, reason=LocateReason.NO_SITES)

    (chain, call_hits), = calls.items()
    certain: list[Site] = []
    groups: list[AmbiguousGroup] = []
    if query.field_name is None:
        certain.extend(_site(hit) for hit in call_hits)
    else:
        certain.extend(_site(hit) for hit in _field_hits(query, scan_result, chain))
        if query.field_presence == "must_be_added":
            certain.extend(_site(hit) for hit in call_hits)
        elif query.field_presence == "must_exist":
            star_kwargs = _star_kwargs_call_sites(call_hits, scan_result)
            if star_kwargs:
                groups.append(
                    AmbiguousGroup(
                        AmbiguityReason.DYNAMIC_KWARGS,
                        query.field_name,
                        tuple(_site(hit) for hit in star_kwargs),
                    )
                )
            getattr_group = _getattr_group(query.field_name, scan_result)
            if getattr_group is not None:
                groups.append(getattr_group)
        alias_group = _alias_group(query.field_name, scan_result)
        if alias_group is not None:
            groups.append(alias_group)
    if not certain and not groups:
        return _build(change, reason=LocateReason.NO_SITES)
    return _build(change, certain=certain, groups=groups)


def _operation_calls(
    query: Query, scan_result: ScanResult
) -> dict[tuple[str, ...], tuple[Hit, ...]]:
    """Rooted call hits per candidate operation chain, in candidate order."""
    resolved: dict[tuple[str, ...], tuple[Hit, ...]] = {}
    for candidate in query.operation_candidates:
        chain = tuple(candidate.split("."))
        hits = tuple(
            hit
            for hit in scan_result.hits
            if hit.shape is SiteShape.CALL and hit.rooted and hit.chain == chain
        )
        if hits:
            resolved[chain] = hits
    return resolved


def _field_hits(
    query: Query, scan_result: ScanResult, chain: tuple[str, ...]
) -> tuple[Hit, ...]:
    """Rooted field evidence on the resolved call, and only there."""
    return tuple(
        hit
        for hit in scan_result.hits
        if hit.rooted
        and hit.shape in _FIELD_SHAPES
        and hit.symbol == query.field_name
        and hit.chain == chain
    )


def _star_kwargs_call_sites(
    call_hits: Sequence[Hit], scan_result: ScanResult
) -> tuple[Hit, ...]:
    """Resolved calls in a file where a rooted ``**kwargs`` was seen."""
    files = {
        dynamic.path
        for dynamic in scan_result.dynamics
        if dynamic.kind is DynamicKind.STAR_KWARGS
    }
    return tuple(hit for hit in call_hits if hit.path in files)


def _candidate_leaves(query: Query) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(candidate.rpartition(".")[2] for candidate in query.operation_candidates)
    )


def _operation_symbol(query: Query) -> str:
    if query.field_name is not None:
        return query.field_name
    if query.operation_candidates:
        return query.operation_candidates[0]
    return query.path or ""


def _getattr_groups(
    symbols: Iterable[str], scan_result: ScanResult
) -> tuple[AmbiguousGroup, ...]:
    groups = (_getattr_group(symbol, scan_result) for symbol in symbols)
    return tuple(group for group in groups if group is not None)


def _getattr_group(symbol: str, scan_result: ScanResult) -> AmbiguousGroup | None:
    sites = _dynamic_sites(symbol, DynamicKind.GETATTR, scan_result)
    if not sites:
        return None
    return AmbiguousGroup(AmbiguityReason.DYNAMIC_GETATTR, symbol, sites)


def _alias_group(symbol: str, scan_result: ScanResult) -> AmbiguousGroup | None:
    sites = _dynamic_sites(symbol, DynamicKind.ALIAS_CHAIN, scan_result)
    if not sites:
        return None
    return AmbiguousGroup(AmbiguityReason.ALIAS_CHAIN, symbol, sites)


def _dynamic_sites(
    symbol: str, kind: DynamicKind, scan_result: ScanResult
) -> tuple[Site, ...]:
    return _unique(
        Site(dynamic.path, dynamic.line, dynamic.column, SiteShape.ATTRIBUTE, symbol)
        for dynamic in scan_result.dynamics
        if dynamic.kind is kind and dynamic.symbol == symbol
    )


def _site(hit: Hit) -> Site:
    return Site(hit.path, hit.line, hit.column, hit.shape, hit.symbol, hit.line_text)


def _unique(sites: Iterable[Site]) -> tuple[Site, ...]:
    """Merge candidates by location so one site is never listed twice."""
    seen: dict[tuple[str, int, int, str, str], Site] = {}
    for site in sites:
        seen.setdefault(_site_key(site), site)
    return tuple(seen.values())


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
