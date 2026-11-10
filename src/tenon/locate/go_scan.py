"""Read-only tree-sitter scan for Go names rooted in an SDK import root.

The scan reports evidence only: every hit carries ``rooted``. Whether a hit is
certain is decided elsewhere.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import tree_sitter_go
from tree_sitter import Language, Node, Parser, Tree

from .result import SiteShape
from .scan import Hit, ScanResult, _Source, _column

_SKIP_DIRECTORIES = frozenset({"vendor", "testdata", ".git"})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_VERSION = re.compile(r"v\d+")


@dataclass(frozen=True, slots=True)
class _Module:
    rel: str
    tree: Tree
    source: _Source


@cache
def _parser() -> Parser:
    return Parser(Language(tree_sitter_go.language()))


def _files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.go"):
        if not path.is_file():
            continue
        directories = path.relative_to(root).parts[:-1]
        if any(
            directory in _SKIP_DIRECTORIES or directory.startswith(".")
            for directory in directories
        ):
            continue
        found.append(path)
    return sorted(found)


def _read(root: Path) -> list[_Module]:
    modules = []
    for path in _files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            tree = _parser().parse(text.encode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if tree.root_node.has_error:
            continue
        modules.append(_Module(rel, tree, _Source(rel, tuple(text.split("\n")))))
    return modules


def _walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""


def _import_path(spec: Node) -> str:
    path = spec.child_by_field_name("path")
    if path is None:
        return ""
    text = _text(path)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "`"}:
        return text[1:-1]
    return ""


def _canonical(path: str, sdk_package: str) -> tuple[str, ...] | None:
    """The path after the import root, or ``None`` when outside it."""
    if path == sdk_package:
        return ()
    prefix = f"{sdk_package}/"
    if path.startswith(prefix):
        return tuple(path[len(prefix) :].split("/"))
    return None


def _inferred_name(path: str) -> str | None:
    """The package clause a Go import path usually implies."""
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None
    candidate = segments[-1]
    if _VERSION.fullmatch(candidate) and len(segments) >= 2:
        candidate = segments[-2]
    if candidate.endswith("-go"):
        candidate = candidate[:-3]
    return candidate if _IDENTIFIER.fullmatch(candidate) else None


def _imports(
    tree: Tree, sdk_package: str, package_name: str | None
) -> tuple[dict[str, tuple[str, ...]], bool]:
    """Names rooted in the SDK, and whether any import roots the package."""
    roots: dict[str, tuple[str, ...]] = {}
    sdk_imported = False
    for node in _walk(tree.root_node):
        if node.type != "import_spec":
            continue
        path = _import_path(node)
        canonical = _canonical(path, sdk_package)
        if canonical is None:
            continue
        sdk_imported = True
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            if name_node.type != "package_identifier":
                continue
            name = _text(name_node)
        elif not canonical and package_name is not None:
            name = package_name
        else:
            name = _inferred_name(path)
        if name is not None:
            roots[name] = canonical
    return roots, sdk_imported


def _selector_segments(node: Node) -> tuple[str, tuple[str, ...]] | None:
    """The base name and the flattened field tail of a selector."""
    tail = []
    while node.type == "selector_expression":
        field = node.child_by_field_name("field")
        if field is None:
            return None
        tail.append(_text(field))
        operand = node.child_by_field_name("operand")
        if operand is None:
            return None
        node = operand
    if node.type != "identifier":
        return None
    tail.reverse()
    return _text(node), tuple(tail)


class _Visitor:
    """Emit rooted calls and unrooted selector calls."""

    def __init__(
        self,
        source: _Source,
        roots: dict[str, tuple[str, ...]],
    ) -> None:
        self._source = source
        self._roots = roots
        self.hits: list[Hit] = []

    def _emit(
        self,
        node: Node,
        shape: SiteShape,
        symbol: str,
        chain: tuple[str, ...],
        rooted: bool,
    ) -> None:
        line = self._source.lines[node.start_point.row]
        self.hits.append(
            Hit(
                self._source.path,
                node.start_point.row + 1,
                _column(line, node.start_point.column),
                shape,
                symbol,
                chain,
                rooted,
                line,
            )
        )

    def _visit_children(self, node: Node) -> None:
        for child in node.children:
            self.visit(child)

    def _call(self, node: Node) -> None:
        function = node.child_by_field_name("function")
        if function is not None and function.type == "selector_expression":
            segments = _selector_segments(function)
            if segments is not None:
                base, tail = segments
                prefix = self._roots.get(base)
                rooted = prefix is not None
                chain = prefix + tail if rooted else tail
                if tail:
                    self._emit(function, SiteShape.CALL, tail[-1], chain, rooted)
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            self.visit(arguments)
        if function is not None and function.type != "selector_expression":
            self.visit(function)

    def visit(self, node: Node) -> None:
        if node.type == "call_expression":
            self._call(node)
        else:
            self._visit_children(node)


def scan_go(
    root: str | Path, sdk_package: str, package_name: str | None = None
) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted Go evidence."""
    modules: list[str] = []
    hits: list[Hit] = []
    for module in _read(Path(root)):
        roots, sdk_imported = _imports(module.tree, sdk_package, package_name)
        if not sdk_imported:
            continue
        visitor = _Visitor(module.source, roots)
        visitor.visit(module.tree.root_node)
        modules.append(module.rel)
        hits.extend(visitor.hits)
    return ScanResult(modules=tuple(modules), hits=tuple(hits))
