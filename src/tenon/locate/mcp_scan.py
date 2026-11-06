"""Read-only AST scan for MCP client tool calls.

The scan reports evidence only: which receiver, which literal tool and which
argument keys, plus the constructs it cannot see through. Whether a call is
certain is decided elsewhere.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .result import SiteShape
from .scan import DynamicKind, _read, _reachable


@dataclass(frozen=True, slots=True)
class McpHit:
    """One ``call_tool`` call or one argument key."""

    path: str
    line: int
    column: int
    shape: SiteShape
    symbol: str
    tool: str | None
    rooted: bool
    line_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shape, SiteShape):
            object.__setattr__(self, "shape", SiteShape(self.shape))


@dataclass(frozen=True, slots=True)
class McpDynamic:
    """A tool name or an argument shape the scan cannot see through."""

    path: str
    line: int
    column: int
    kind: DynamicKind
    tool: str | None
    symbol: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DynamicKind):
            object.__setattr__(self, "kind", DynamicKind(self.kind))


def _hit_key(hit: McpHit) -> tuple:
    return (
        hit.path,
        hit.line,
        hit.column,
        hit.shape.value,
        hit.symbol,
        hit.tool or "",
        hit.rooted,
        hit.line_text or "",
    )


def _dynamic_key(dynamic: McpDynamic) -> tuple:
    return (
        dynamic.path,
        dynamic.line,
        dynamic.column,
        dynamic.kind.value,
        dynamic.tool or "",
        dynamic.symbol or "",
    )


@dataclass(frozen=True, slots=True)
class McpScan:
    """Everything the scan found in one repository. Canonically ordered."""

    modules: Sequence[str] = ()
    hits: Sequence[McpHit] = ()
    dynamics: Sequence[McpDynamic] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", tuple(sorted(set(self.modules))))
        object.__setattr__(self, "hits", tuple(sorted(set(self.hits), key=_hit_key)))
        object.__setattr__(
            self, "dynamics", tuple(sorted(set(self.dynamics), key=_dynamic_key))
        )


def scan_mcp(root: str | Path, client_package: str) -> McpScan:
    """Parse ``root`` read-only and report MCP call evidence."""
    modules = _read(Path(root))
    reachable = _reachable(modules, client_package)
    return McpScan(modules=tuple(module.rel for module in reachable))
