"""The MCP locate wrapper: turn scan evidence into the shipped result."""

from pathlib import Path

from tenon.detect import Change

from .mcp_config import McpLocateConfig
from .mcp_scan import scan_mcp
from .result import LocateReason, LocateResult
from .resolve import _build


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
    return _build(change, reason=LocateReason.NO_SITES)
