"""Read-only tree-sitter scan for C# names rooted in an SDK namespace.

The scan reports evidence only: every hit carries ``rooted``. Whether a hit is
certain is decided elsewhere.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser, Tree

from .result import SiteShape
from .scan import Hit, ScanResult, _Source, _column

_SKIP_DIRECTORIES = frozenset({"bin", "obj", ".git"})
_MEMBER_SCOPES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "accessor_declaration",
        "local_function_statement",
    }
)


@dataclass(frozen=True, slots=True)
class _Module:
    rel: str
    tree: Tree
    source: _Source


@cache
def _parser() -> Parser:
    return Parser(Language(tree_sitter_c_sharp.language()))


def _files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.cs"):
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


def _unwrap(node: Node | None) -> Node | None:
    """Strip call arguments and parentheses around an expression."""
    while node is not None:
        if node.type == "argument":
            node = node.named_children[-1] if node.named_children else None
        elif node.type == "parenthesized_expression":
            node = node.named_children[0] if node.named_children else None
        else:
            return node
    return None


def _segments(node: Node) -> tuple[str, ...] | None:
    """The base name and the flattened member tail of a member access."""
    names = []
    while node.type == "member_access_expression":
        name = node.child_by_field_name("name")
        expression = node.child_by_field_name("expression")
        if name is None or expression is None:
            return None
        names.append(_text(name))
        node = expression
    if node.type != "identifier":
        return None
    names.append(_text(node))
    names.reverse()
    return tuple(names)


def _under_root(target: str, sdk_parts: tuple[str, ...]) -> bool:
    root = ".".join(sdk_parts)
    return target == root or target.startswith(f"{root}.")


@dataclass(frozen=True, slots=True)
class _Roots:
    sdk_parts: tuple[str, ...]
    namespace_import: bool = False
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def type_path(self, segments: tuple[str, ...]) -> tuple[str, ...] | None:
        """The canonical chain of a type path rooted in the SDK, else ``None``."""
        if len(segments) == 1:
            name = segments[0]
            if name in self.aliases:
                return self.aliases[name]
            return (name,) if self.namespace_import else None
        if (
            len(segments) > len(self.sdk_parts)
            and segments[: len(self.sdk_parts)] == self.sdk_parts
        ):
            return (segments[-1],)
        return None


def _usings(tree: Tree, sdk_package: str) -> tuple[_Roots, bool]:
    """The rooted names and whether a `using static` imports the root."""
    sdk_parts = tuple(sdk_package.split("."))
    namespace_import = False
    static_import = False
    aliases: dict[str, tuple[str, ...]] = {}
    for node in _walk(tree.root_node):
        if node.type != "using_directive":
            continue
        name = node.child_by_field_name("name")
        targets = [
            child
            for child in node.named_children
            if child.type in {"identifier", "qualified_name"}
        ]
        if not targets:
            continue
        target = _text(targets[-1])
        if any(child.type == "static" for child in node.children):
            if _under_root(target, sdk_parts):
                static_import = True
            continue
        if name is not None:
            if _under_root(target, sdk_parts) and target != ".".join(sdk_parts):
                aliases[_text(name)] = (target.rsplit(".", 1)[-1],)
            continue
        if _under_root(target, sdk_parts):
            namespace_import = True
    return _Roots(sdk_parts, namespace_import, aliases), static_import


def _mentions_rooted_type(tree: Tree, roots: _Roots) -> bool:
    """Whether the file spells a fully qualified type under the root."""
    for node in _walk(tree.root_node):
        if node.type == "qualified_name":
            if roots.type_path(tuple(_text(node).split("."))) is not None:
                return True
        elif node.type == "member_access_expression":
            segments = _segments(node)
            if segments is not None and len(segments) > 1:
                if roots.type_path(segments[:-1]) is not None:
                    return True
    return False


class _Visitor:
    """Emit rooted calls and track bindings of rooted receiver types."""

    def __init__(
        self, source: _Source, roots: _Roots, receivers: Mapping[str, str]
    ) -> None:
        self._source = source
        self._roots = roots
        self._receivers = {
            key.replace("::", "."): value for key, value in receivers.items()
        }
        self._bindings: dict[str, tuple[tuple[str, ...] | None, tuple[Node, ...]]] = {}
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

    def _type_chain(self, type_node: Node | None) -> tuple[str, ...] | None:
        """The canonical chain of a rooted type, else ``None``."""
        if type_node is None:
            return None
        if type_node.type == "identifier":
            return self._roots.type_path((_text(type_node),))
        if type_node.type == "qualified_name":
            return self._roots.type_path(tuple(_text(type_node).split(".")))
        return None

    def _keys(self, initializer: Node | None) -> tuple[Node, ...]:
        """The property identifiers of an object initializer."""
        if initializer is None or initializer.type != "initializer_expression":
            return ()
        keys = []
        for child in initializer.named_children:
            if child.type != "assignment_expression":
                continue
            left = child.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                keys.append(left)
        return tuple(keys)

    def _factory(self, call: Node) -> tuple[str, ...] | None:
        """The type chain a configured factory call binds, if its key matches."""
        function = call.child_by_field_name("function")
        segments = _segments(function) if function is not None else None
        if segments is None or len(segments) < 2:
            return None
        prefix = self._roots.type_path(segments[:-1])
        candidates = [".".join(segments)]
        if prefix is not None:
            candidates.insert(0, ".".join((*prefix, segments[-1])))
        for candidate in candidates:
            mapped = self._receivers.get(candidate)
            if mapped is None:
                continue
            chain = tuple(
                part for part in mapped.replace("::", ".").split(".") if part
            )
            if chain:
                return chain
        return None

    def _evidence(
        self, value: Node | None
    ) -> tuple[tuple[str, ...] | None, tuple[Node, ...]]:
        """The type chain a value binds, from a rooted `new` or a mapped factory."""
        node = _unwrap(value)
        if node is None:
            return None, ()
        if node.type == "object_creation_expression":
            return (
                self._type_chain(node.child_by_field_name("type")),
                self._keys(node.child_by_field_name("initializer")),
            )
        if node.type == "invocation_expression":
            return self._factory(node), ()
        return None, ()

    def _bind(
        self, name: str, value: Node | None, declared: Node | None = None
    ) -> None:
        chain, keys = self._evidence(value)
        if chain is None and declared is not None:
            chain = self._type_chain(declared)
        self._bindings[name] = (chain, keys)

    def _assignment(self, node: Node) -> None:
        if node.parent is not None and node.parent.type == "initializer_expression":
            self._visit_children(node)
            return
        left = node.child_by_field_name("left")
        if left is not None and left.type == "identifier":
            self._bind(_text(left), node.child_by_field_name("right"))
        self._visit_children(node)

    def _declaration(self, node: Node) -> None:
        type_node = node.child_by_field_name("type")
        is_var = type_node is not None and type_node.type == "implicit_type"
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                continue
            initializer = (
                child.named_children[1] if len(child.named_children) > 1 else None
            )
            self._bind(
                _text(name_node), initializer, None if is_var else type_node
            )
        self._visit_children(node)

    def _receiver(self, node: Node | None) -> tuple[str, ...] | None:
        """The type chain a bound receiver expression stands for."""
        node = _unwrap(node)
        if node is None:
            return None
        if node.type == "identifier":
            binding = self._bindings.get(_text(node))
            return binding[0] if binding is not None else None
        if node.type != "member_access_expression":
            return None
        expression = node.child_by_field_name("expression")
        name = node.child_by_field_name("name")
        chain = self._receiver(expression)
        if chain is None or name is None:
            return None
        return (*chain, _text(name))

    def _call_chain(
        self, base: str, tail: tuple[str, ...]
    ) -> tuple[tuple[str, ...], bool]:
        binding = self._bindings.get(base)
        if binding is not None:
            if binding[0] is not None:
                return (*binding[0], *tail), True
            return tail, False
        if len(tail) == 1:
            chain = self._roots.type_path((base,))
        else:
            chain = self._roots.type_path((base, *tail[:-1]))
        if chain is not None:
            return (*chain, tail[-1]), True
        return tail, False

    def _creation(self, node: Node) -> None:
        chain = self._type_chain(node.child_by_field_name("type"))
        if chain is not None:
            for key in self._keys(node.child_by_field_name("initializer")):
                self._emit(key, SiteShape.KEYWORD, _text(key), chain, True)
        self._visit_children(node)

    def _member(self, node: Node) -> None:
        expression = node.child_by_field_name("expression")
        name = node.child_by_field_name("name")
        if (
            expression is not None
            and expression.type == "identifier"
            and name is not None
        ):
            binding = self._bindings.get(_text(expression))
            if binding is not None and binding[0] is not None:
                self._emit(name, SiteShape.ATTRIBUTE, _text(name), binding[0], True)
        self._visit_children(node)

    def _argument(self, argument: Node, call_chain: tuple[str, ...]) -> None:
        node = _unwrap(argument)
        if node is None:
            return
        if node.type == "object_creation_expression":
            chain = self._type_chain(node.child_by_field_name("type"))
            if chain is not None:
                for key in self._keys(node.child_by_field_name("initializer")):
                    self._emit(key, SiteShape.KEYWORD, _text(key), call_chain, True)
        elif node.type == "identifier":
            binding = self._bindings.get(_text(node))
            if binding is not None and binding[0] is not None:
                for key in binding[1]:
                    self._emit(key, SiteShape.KEYWORD, _text(key), call_chain, True)
        elif node.type == "member_access_expression":
            expression = node.child_by_field_name("expression")
            field = node.child_by_field_name("name")
            binding = (
                self._bindings.get(_text(expression))
                if expression is not None and expression.type == "identifier"
                else None
            )
            if binding is not None and binding[0] is not None and field is not None:
                self._emit(field, SiteShape.ATTRIBUTE, _text(field), call_chain, True)

    def _call(self, node: Node) -> None:
        function = node.child_by_field_name("function")
        call_chain: tuple[str, ...] | None = None
        if function is not None and function.type == "member_access_expression":
            segments = _segments(function)
            if segments is not None and len(segments) > 1:
                tail = segments[1:]
                chain, rooted = self._call_chain(segments[0], tail)
                self._emit(function, SiteShape.CALL, tail[-1], chain, rooted)
                if rooted:
                    call_chain = chain
                    expression = function.child_by_field_name("expression")
                    if (
                        expression is not None
                        and expression.type == "member_access_expression"
                    ):
                        field = expression.child_by_field_name("name")
                        receiver = self._receiver(expression)
                        if field is not None and receiver is not None:
                            self._emit(
                                field,
                                SiteShape.ATTRIBUTE,
                                _text(field),
                                receiver,
                                True,
                            )
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            if call_chain is not None:
                for argument in arguments.named_children:
                    self._argument(argument, call_chain)
            self.visit(arguments)
        if function is not None and function.type != "member_access_expression":
            self.visit(function)

    def visit(self, node: Node) -> None:
        if node.type in _MEMBER_SCOPES:
            saved = self._bindings
            self._bindings = {}
            self._visit_children(node)
            self._bindings = saved
        elif node.type == "variable_declaration":
            self._declaration(node)
        elif node.type == "assignment_expression":
            self._assignment(node)
        elif node.type == "invocation_expression":
            self._call(node)
        elif node.type == "object_creation_expression":
            self._creation(node)
        elif node.type == "member_access_expression":
            self._member(node)
        else:
            self._visit_children(node)


def scan_csharp(
    root: str | Path,
    sdk_package: str,
    receivers: Mapping[str, str] | None = None,
) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted C# evidence."""
    modules: list[str] = []
    hits: list[Hit] = []
    for module in _read(Path(root)):
        roots, static_import = _usings(module.tree, sdk_package)
        if not (
            roots.namespace_import
            or roots.aliases
            or static_import
            or _mentions_rooted_type(module.tree, roots)
        ):
            continue
        visitor = _Visitor(module.source, roots, receivers or {})
        visitor.visit(module.tree.root_node)
        modules.append(module.rel)
        hits.extend(visitor.hits)
    return ScanResult(modules=tuple(modules), hits=tuple(hits))
