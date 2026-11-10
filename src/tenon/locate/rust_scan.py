"""Read-only tree-sitter scan for Rust names rooted in an SDK crate.

The scan reports evidence only: every hit carries ``rooted`` and every construct
it cannot see through becomes a ``Dynamic``. Whether a hit is certain is decided
elsewhere.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import tree_sitter_rust
from tree_sitter import Language, Node, Parser, Tree

from .result import SiteShape
from .scan import Hit, ScanResult, _Source, _column

_SKIP_DIRECTORIES = frozenset({"target", "vendor", ".git"})


@dataclass(frozen=True, slots=True)
class _Module:
    rel: str
    tree: Tree
    source: _Source


@cache
def _parser() -> Parser:
    return Parser(Language(tree_sitter_rust.language()))


def _files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.rs"):
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


def _path_segments(node: Node) -> tuple[str, ...]:
    if node.type in {"identifier", "type_identifier"}:
        return (_text(node),)
    if node.type in {"scoped_identifier", "scoped_type_identifier"}:
        return _path_segments(node.named_children[0]) + (_text(node.named_children[-1]),)
    return ()


def _use_path(node: Node | None, prefix: tuple[str, ...]) -> tuple[str, ...] | None:
    if node is None:
        return prefix or None
    if node.type == "self":
        return prefix or None
    if node.type == "identifier":
        return prefix + (_text(node),) if prefix else (_text(node),)
    if node.type in {"scoped_identifier", "scoped_type_identifier"}:
        return _path_segments(node)
    return None


def _use_tree(
    node: Node,
    prefix: tuple[str, ...],
    crate: str,
    roots: dict[str, tuple[str, ...]],
) -> bool:
    """Bind one use tree; return whether it mentions the crate."""
    if node.type == "identifier":
        name = _text(node)
        if prefix:
            if prefix[0] != crate:
                return False
            roots[name] = prefix[1:] + (name,)
            return True
        if name == crate:
            roots[name] = ()
            return True
        return False
    if node.type == "self":
        if not prefix or prefix[0] != crate:
            return False
        roots[prefix[-1]] = prefix[1:]
        return True
    if node.type in {"scoped_identifier", "scoped_type_identifier"}:
        path = _path_segments(node)
        if not path or path[0] != crate:
            return False
        roots[path[-1]] = path[1:]
        return True
    if node.type == "use_as_clause":
        path = _use_path(node.child_by_field_name("path"), prefix)
        alias = node.child_by_field_name("alias")
        if path is None or path[0] != crate or alias is None:
            return False
        roots[_text(alias)] = path[1:]
        return True
    if node.type == "scoped_use_list":
        path = _use_path(node.child_by_field_name("path"), prefix)
        use_list = next(
            (child for child in node.named_children if child.type == "use_list"), None
        )
        if path is None or use_list is None:
            return False
        rooted = path[0] == crate
        for item in use_list.named_children:
            rooted = _use_tree(item, path, crate, roots) or rooted
        return rooted
    if node.type == "use_wildcard":
        path_node = node.named_children[0] if node.named_children else None
        path = _use_path(path_node, prefix)
        return bool(path and path[0] == crate)
    return False


def _bindings(
    tree: Tree, crate: str
) -> tuple[dict[str, tuple[str, ...]], bool]:
    """Names rooted in the crate, and whether any use roots the crate."""
    roots: dict[str, tuple[str, ...]] = {}
    crate_used = False
    for node in _walk(tree.root_node):
        if node.type != "use_declaration":
            continue
        for child in node.named_children:
            crate_used = _use_tree(child, (), crate, roots) or crate_used
    return roots, crate_used


def _callee_ref(
    node: Node | None, roots: dict[str, tuple[str, ...]], crate: str
) -> tuple[tuple[str, ...], bool] | None:
    """The canonical chain and rootedness of a call's callee."""
    if node is None:
        return None
    if node.type == "identifier":
        name = _text(node)
        if name in roots:
            return roots[name], True
        if name == crate:
            return (), True
        return None
    if node.type == "scoped_identifier":
        path = _path_segments(node)
        if not path:
            return None
        if path[0] == crate:
            return path[1:], True
        if path[0] in roots:
            return roots[path[0]] + path[1:], True
        return path, False
    return None


class _Visitor:
    """Emit rooted calls and unrooted non-method path calls."""

    def __init__(
        self,
        source: _Source,
        crate: str,
        roots: dict[str, tuple[str, ...]],
    ) -> None:
        self._source = source
        self._crate = crate
        self._roots = roots
        self.rooted = False
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

    def _call(self, node: Node) -> None:
        function = node.child_by_field_name("function")
        ref = _callee_ref(function, self._roots, self._crate)
        if ref is not None:
            chain, rooted = ref
            if rooted:
                self.rooted = True
                if chain:
                    self._emit(function, SiteShape.CALL, chain[-1], chain, True)
            elif function is not None and function.type == "scoped_identifier":
                self._emit(function, SiteShape.CALL, chain[-1], chain, False)
        if function is not None and function.type != "field_expression":
            self.visit(function)
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            for argument in arguments.named_children:
                self.visit(argument)

    def visit(self, node: Node) -> None:
        if node.type == "call_expression":
            self._call(node)
        else:
            for child in node.children:
                self.visit(child)


def scan_rust(root: str | Path, sdk_package: str) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted Rust evidence."""
    modules: list[str] = []
    hits: list[Hit] = []
    for module in _read(Path(root)):
        roots, crate_used = _bindings(module.tree, sdk_package)
        visitor = _Visitor(module.source, sdk_package, roots)
        visitor.visit(module.tree.root_node)
        if crate_used or visitor.rooted:
            modules.append(module.rel)
            hits.extend(visitor.hits)
    return ScanResult(modules=tuple(modules), hits=tuple(hits))
