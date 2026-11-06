"""The MCP locate wrapper: turn scan evidence into the shipped result."""

from pathlib import Path

from tenon.detect import Change, ChangeKind

from .mcp_config import McpLocateConfig
from .mcp_scan import McpHit, scan_mcp
from .result import LocateReason, LocateResult, Site, SiteShape
from .resolve import _build

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
    if field is None:
        certain = tuple(_site(hit) for hit in rooted_calls)
    else:
        keys = tuple(
            _site(hit)
            for hit in matches
            if hit.rooted and hit.shape in _FIELD_SHAPES and hit.symbol == field
        )
        # Spec AC3: a missing required key sends the reader to the call to add it.
        certain = keys if keys or not must_be_added else tuple(
            _site(hit) for hit in rooted_calls
        )
    if not certain:
        return _build(change, reason=LocateReason.NO_SITES)
    return _build(change, certain=certain)


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
