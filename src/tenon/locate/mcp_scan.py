"""Read-only AST scan for MCP client tool calls.

The scan reports evidence only: which receiver, which literal tool and which
argument keys, plus the constructs it cannot see through. Whether a call is
certain is decided elsewhere.
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .result import SiteShape
from .scan import (
    DynamicKind,
    _bindings,
    _column,
    _parts,
    _read,
    _reachable,
    _Source,
)


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
    hits: list[McpHit] = []
    dynamics: list[McpDynamic] = []
    for module in reachable:
        roots, classes = _mcp_bindings(module.tree, client_package)
        rooted, alias_dynamics = _rooted_sessions(
            module.tree, roots, classes, module.source
        )
        visitor = _Visitor(module.source, roots, classes, rooted, alias_dynamics)
        visitor.visit(module.tree)
        hits.extend(visitor.hits)
        dynamics.extend(visitor.dynamics)
    return McpScan(
        modules=tuple(module.rel for module in reachable),
        hits=tuple(hits),
        dynamics=tuple(dynamics),
    )


def _mcp_bindings(
    tree: ast.Module, client_package: str
) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    """Import roots of the client package and names bound to ``ClientSession``."""
    roots, _, _ = _bindings(tree, client_package)
    classes = {name for name, full in roots.items() if full[-1] == "ClientSession"}
    return roots, classes


def _is_client_session(
    node: ast.expr,
    roots: dict[str, tuple[str, ...]],
    classes: set[str],
) -> bool:
    """Whether ``node`` constructs the imported ``ClientSession`` class."""
    if not isinstance(node, ast.Call):
        return False
    root, tail = _parts(node.func)
    if root is None:
        return False
    if root in classes and not tail:
        return True
    if root in roots and tail:
        return (roots[root] + tail)[-1] == "ClientSession"
    return False


def _dynamic(
    source: _Source,
    node: ast.AST,
    kind: DynamicKind,
    tool: str | None,
    symbol: str | None = None,
) -> McpDynamic:
    line = source.lines[node.lineno - 1]
    return McpDynamic(
        source.path, node.lineno, _column(line, node.col_offset), kind, tool, symbol
    )


def _rooted_sessions(
    tree: ast.Module,
    roots: dict[str, tuple[str, ...]],
    classes: set[str],
    source: _Source,
) -> tuple[set[str], list[McpDynamic]]:
    """Session names bound by construction or a with-statement.

    A name assigned from a bound session is a second hop: an ``ALIAS_CHAIN``
    dynamic, never a rooted receiver.
    """
    rooted: set[str] = set()
    chained: set[str] = set()
    dynamics: list[McpDynamic] = []
    nodes = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.With, ast.AsyncWith))
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in nodes:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name) and _is_client_session(
                    item.context_expr, roots, classes
                ):
                    rooted.add(item.optional_vars.id)
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0]
        name = target.id
        rooted.discard(name)
        chained.discard(name)
        if _is_client_session(node.value, roots, classes):
            rooted.add(name)
        elif isinstance(node.value, ast.Name) and node.value.id in rooted | chained:
            chained.add(name)
            dynamics.append(
                _dynamic(source, target, DynamicKind.ALIAS_CHAIN, None, name)
            )
    return rooted, dynamics


class _Visitor(ast.NodeVisitor):
    """Emit call evidence and dynamics for MCP ``call_tool`` calls."""

    def __init__(
        self,
        source: _Source,
        roots: dict[str, tuple[str, ...]],
        classes: set[str],
        rooted: set[str],
        dynamics: list[McpDynamic],
    ) -> None:
        self._source = source
        self._roots = roots
        self._classes = classes
        self._rooted = rooted
        self.hits: list[McpHit] = []
        self.dynamics = dynamics

    def _is_rooted(self, receiver: ast.expr) -> bool:
        if isinstance(receiver, ast.Name):
            return receiver.id in self._rooted
        return _is_client_session(receiver, self._roots, self._classes)

    def _emit(
        self, node: ast.AST, symbol: str, rooted: bool, leaf: bool = False
    ) -> None:
        line = self._source.lines[node.lineno - 1]
        byte_col = (
            node.end_col_offset - len(symbol.encode("utf-8"))
            if leaf
            else node.col_offset
        )
        self.hits.append(
            McpHit(
                self._source.path,
                node.lineno,
                _column(line, byte_col),
                SiteShape.CALL,
                symbol,
                None,
                rooted,
                line,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "call_tool":
            self._emit(
                node.func,
                "call_tool",
                self._is_rooted(node.func.value),
                leaf=True,
            )
        self.generic_visit(node)
