"""The MCP locate wrapper: turn scan evidence into the shipped result."""

from pathlib import Path

from tenon.detect import Change, ChangeKind

from .mcp_config import McpLocateConfig
from .mcp_scan import McpHit, McpScan, scan_mcp
from .result import (
    AmbiguityReason,
    AmbiguousGroup,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
)
from .resolve import _build, _unique
from .scan import DynamicKind

_FIELD_SHAPES = (SiteShape.KEYWORD, SiteShape.DICT_KEY)
_CALL_ONLY_KINDS = frozenset(
    {
        ChangeKind.ENDPOINT_REMOVED,
        ChangeKind.ENDPOINT_ADDED,
        ChangeKind.ADDITIONAL_PROPERTIES_CHANGED,
    }
)
_SUPPORTED_KINDS = _CALL_ONLY_KINDS | {
    ChangeKind.PROPERTY_REMOVED,
    ChangeKind.PROPERTY_ADDED,
    ChangeKind.PROPERTY_REQUIRED_ADDED,
    ChangeKind.PROPERTY_TYPE_CHANGED,
    ChangeKind.RENAMED,
    ChangeKind.ENUM_NARROWED,
}


def locate_mcp(
    change: Change, root: str | Path, config: McpLocateConfig
) -> LocateResult:
    """Locate one MCP tool change, or name why it cannot be located."""
    # Spec AC5: only a tool-scoped change with a tool name is this locator's.
    if change.location.method != "tool" or not change.location.path:
        return _build(change, reason=LocateReason.UNSUPPORTED_CHANGE_KIND)
    scan = scan_mcp(root, config.client_package)
    if not scan.modules:
        return _build(change, reason=LocateReason.NO_SDK_IMPORT)
    if change.kind not in _SUPPORTED_KINDS:
        return _build(change, reason=LocateReason.UNSUPPORTED_CHANGE_KIND)

    tool = change.location.path
    field = _field_name(change)
    must_be_added = (
        change.kind is ChangeKind.PROPERTY_REQUIRED_ADDED and field is not None
    )
    matches = tuple(hit for hit in scan.hits if hit.tool == tool)
    rooted_calls = tuple(
        hit
        for hit in matches
        if hit.shape is SiteShape.CALL and hit.rooted
    )
    rooted_keys = tuple(
        hit
        for hit in matches
        if field is not None
        and hit.rooted
        and hit.shape in _FIELD_SHAPES
        and hit.symbol == field
    )
    if field is None:
        certain = tuple(_site(hit) for hit in rooted_calls)
    elif rooted_keys:
        certain = tuple(_site(hit) for hit in rooted_keys)
    elif must_be_added:
        # Spec AC3: a missing required key sends the reader to the call to add it.
        certain = tuple(_site(hit) for hit in rooted_calls)
    else:
        certain = ()
    groups = _groups(scan, tool, field, must_be_added, rooted_calls, rooted_keys)
    if not certain and not groups:
        return _build(change, reason=LocateReason.NO_SITES)
    return _build(change, certain=certain, groups=groups)


def _groups(
    scan: McpScan,
    tool: str,
    field: str | None,
    must_be_added: bool,
    rooted_calls: tuple[McpHit, ...],
    rooted_keys: tuple[McpHit, ...],
) -> tuple[AmbiguousGroup, ...]:
    """Every construct that could hide the changed tool or key."""
    groups: list[AmbiguousGroup] = []
    # Spec AC4: a variable tool name can only be a candidate call.
    getattr_calls = _getattr_call_sites(scan)
    if getattr_calls:
        groups.append(
            AmbiguousGroup(
                AmbiguityReason.DYNAMIC_GETATTR, field or tool, getattr_calls
            )
        )
    # The call is already certain when a missing required key is added there.
    if field is not None and not (must_be_added and not rooted_keys):
        groups.extend(_kwargs_groups(scan, tool, field, rooted_calls))
    groups.extend(_receiver_groups(scan, tool, field))
    return tuple(groups)


def _getattr_call_sites(scan: McpScan) -> tuple[Site, ...]:
    if not any(
        dynamic.kind is DynamicKind.GETATTR for dynamic in scan.dynamics
    ):
        return ()
    return _unique(
        _site(hit)
        for hit in scan.hits
        if hit.shape is SiteShape.CALL and hit.tool is None
    )


def _kwargs_groups(
    scan: McpScan,
    tool: str,
    field: str,
    rooted_calls: tuple[McpHit, ...],
) -> tuple[AmbiguousGroup, ...]:
    """A payload this scan cannot see through, per file it appeared in."""
    paths = {
        dynamic.path
        for dynamic in scan.dynamics
        if dynamic.kind is DynamicKind.STAR_KWARGS and dynamic.tool == tool
    }
    sites = _unique(_site(hit) for hit in rooted_calls if hit.path in paths)
    if not sites:
        return ()
    return (AmbiguousGroup(AmbiguityReason.DYNAMIC_KWARGS, field, sites),)


def _receiver_groups(
    scan: McpScan, tool: str, field: str | None
) -> tuple[AmbiguousGroup, ...]:
    """Unrooted matching calls, split by whether an alias explains them.

    shortcut: an alias is associated per file because McpHit has no receiver
    name; add the receiver to the scan when a real repo needs per-call precision.
    """
    aliased_paths = {
        dynamic.path
        for dynamic in scan.dynamics
        if dynamic.kind is DynamicKind.ALIAS_CHAIN
    }
    key_hits = (
        ()
        if field is None
        else tuple(
            hit
            for hit in scan.hits
            if hit.tool == tool
            and not hit.rooted
            and hit.shape in _FIELD_SHAPES
            and hit.symbol == field
        )
    )
    groups: list[AmbiguousGroup] = []
    for reason, aliased in (
        (AmbiguityReason.ALIAS_CHAIN, True),
        (AmbiguityReason.UNROOTED_RECEIVER, False),
    ):
        candidates = _unique(
            [
                *(
                    _site(hit)
                    for hit in scan.hits
                    if hit.shape is SiteShape.CALL
                    and hit.tool == tool
                    and not hit.rooted
                    and (hit.path in aliased_paths) == aliased
                ),
                *(
                    _site(hit)
                    for hit in key_hits
                    if (hit.path in aliased_paths) == aliased
                ),
            ]
        )
        if candidates:
            groups.append(
                AmbiguousGroup(reason, field or tool, candidates)
            )
    return tuple(groups)


def _field_name(change: Change) -> str | None:
    """The argument name the change is about, or None for a call-site change."""
    if change.kind in _CALL_ONLY_KINDS or "/outputSchema" in change.location.pointer:
        return None
    if change.kind is ChangeKind.PROPERTY_REMOVED:
        return _payload_name(change.before)
    if change.kind is ChangeKind.PROPERTY_ADDED:
        return _payload_name(change.after)
    if change.kind is ChangeKind.PROPERTY_REQUIRED_ADDED:
        return _payload_name(change.after) or _payload_name(change.before)
    if change.kind is ChangeKind.PROPERTY_TYPE_CHANGED:
        return _payload_name(change.before) or _payload_name(change.after)
    if change.kind is ChangeKind.RENAMED:
        return change.before if isinstance(change.before, str) else None
    if change.kind is ChangeKind.ENUM_NARROWED:
        return _payload_name(change.before)
    return None


def _payload_name(payload: object) -> str | None:
    if isinstance(payload, dict):
        name = payload.get("name")
        return name if isinstance(name, str) else None
    return None


def _site(hit: McpHit) -> Site:
    return Site(hit.path, hit.line, hit.column, hit.shape, hit.symbol, hit.line_text)
