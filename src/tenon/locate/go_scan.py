"""Read-only tree-sitter scan for Go names rooted in an SDK import root.

The scan reports evidence only: every hit carries ``rooted``. Whether a hit is
certain is decided elsewhere.
"""

import re
from collections.abc import Iterator, Mapping
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


def _unwrap(node: Node | None) -> Node | None:
    """Strip parentheses and address-of operators."""
    while node is not None:
        if node.type == "parenthesized_expression":
            node = node.named_children[0] if node.named_children else None
        elif node.type == "unary_expression":
            operator = node.child_by_field_name("operator")
            if operator is None or _text(operator) != "&":
                return node
            node = node.child_by_field_name("operand")
        else:
            return node
    return None


@dataclass(frozen=True, slots=True)
class _Binding:
    """A name bound to a rooted type, its literal fields and its evidence kind."""

    chain: tuple[str, ...]
    fields: tuple[Node, ...] = ()
    literal: bool = False


def _type_chain(
    type_node: Node | None, roots: dict[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    """The canonical chain of a rooted qualified type, else ``None``."""
    while type_node is not None and type_node.type == "pointer_type":
        type_node = type_node.named_children[0] if type_node.named_children else None
    if type_node is None or type_node.type != "qualified_type":
        return None
    package = type_node.child_by_field_name("package")
    name = type_node.child_by_field_name("name")
    if package is None or name is None:
        return None
    prefix = roots.get(_text(package))
    if prefix is None:
        return None
    return prefix + (_text(name),)


def _result_chain(
    result: Node | None, roots: dict[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    """The canonical chain of a function's first result type, else ``None``."""
    if result is None:
        return None
    if result.type == "parameter_list":
        first = result.named_children[0] if result.named_children else None
        if first is None or first.type != "parameter_declaration":
            return None
        if first.child_by_field_name("name") is not None:
            return None
        result = first.child_by_field_name("type")
    return _type_chain(result, roots)


def _returns(
    tree: Tree, roots: dict[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Same-file function name -> SDK result chain from its signature.

    A named result, ``error`` or non-SDK first result is no evidence; a later
    definition of the same name replaces or clears the map.
    """
    found: dict[str, tuple[str, ...]] = {}
    for node in _walk(tree.root_node):
        if node.type != "function_declaration":
            continue
        name = node.child_by_field_name("name")
        if name is None:
            continue
        chain = _result_chain(node.child_by_field_name("result"), roots)
        if chain is None:
            found.pop(_text(name), None)
        else:
            found[_text(name)] = chain
    return found


class _Visitor:
    """Emit rooted calls, literal fields and field accesses."""

    def __init__(
        self,
        source: _Source,
        roots: dict[str, tuple[str, ...]],
        receivers: Mapping[str, str],
        returns: dict[str, tuple[str, ...]],
    ) -> None:
        self._source = source
        self._roots = roots
        self._receivers = receivers
        self._returns = returns
        self._bindings: dict[str, _Binding] = {}
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

    def _keys(self, literal: Node) -> tuple[Node, ...]:
        """The keyed-element key identifiers of a composite literal."""
        body = literal.child_by_field_name("body")
        if body is None:
            return ()
        keys = []
        for child in body.named_children:
            if child.type != "keyed_element":
                continue
            key = child.child_by_field_name("key")
            identifier = key.named_children[0] if key and key.named_children else None
            if identifier is not None and identifier.type == "identifier":
                keys.append(identifier)
        return tuple(keys)

    def _bind(self, name: str, value: Node | None) -> None:
        binding = self._evidence(value)
        if binding is None:
            self._bindings.pop(name, None)
        else:
            self._bindings[name] = binding

    def _evidence(self, value: Node | None) -> _Binding | None:
        """The rooted type a value binds, from a literal or a mapped factory."""
        node = _unwrap(value)
        if node is None:
            return None
        if node.type == "composite_literal":
            chain = _type_chain(node.child_by_field_name("type"), self._roots)
            if chain is None:
                return None
            return _Binding(chain, self._keys(node), True)
        if node.type == "call_expression":
            return self._call_evidence(node)
        return None

    def _call_evidence(self, call: Node) -> _Binding | None:
        """The type a mapped factory or a typed helper call binds."""
        function = call.child_by_field_name("function")
        if function is None:
            return None
        if function.type == "identifier":
            annotated = self._returns.get(_text(function))
            return _Binding(annotated) if annotated is not None else None
        if function.type != "selector_expression":
            return None
        package = function.child_by_field_name("operand")
        field = function.child_by_field_name("field")
        if package is None or field is None or package.type != "identifier":
            return None
        name = _text(package)
        if name not in self._roots:
            return None
        for key in (f"{name}.{_text(field)}", _text(field)):
            mapped = self._receivers.get(key)
            if mapped is None:
                continue
            chain = tuple(part for part in mapped.split(".") if part)
            if chain:
                return _Binding(chain)
        return None

    def _parameters(self, node: Node) -> None:
        """Seed the body from the annotated parameters of a function."""
        parameters = node.child_by_field_name("parameters")
        if parameters is None:
            return
        for declaration in parameters.named_children:
            if declaration.type != "parameter_declaration":
                continue
            chain = _type_chain(
                declaration.child_by_field_name("type"), self._roots
            )
            if chain is None:
                continue
            # Spec AC2: a grouped name list binds each name.
            for name in declaration.named_children:
                if name.type != "identifier":
                    break
                if _text(name) != "_":
                    self._bindings[_text(name)] = _Binding(chain)

    def _bind_type(self, name: str, type_node: Node | None) -> None:
        chain = _type_chain(type_node, self._roots)
        if chain is None:
            self._bindings.pop(name, None)
        else:
            self._bindings[name] = _Binding(chain)

    def _short_var(self, node: Node) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        targets = left.named_children if left is not None else ()
        values = right.named_children if right is not None else ()
        for index, target in enumerate(targets):
            if target.type != "identifier" or _text(target) == "_":
                continue
            self._bind(_text(target), values[index] if index < len(values) else None)
        self._visit_children(node)

    def _var(self, node: Node) -> None:
        for child in node.named_children:
            specs = (
                child.named_children
                if child.type == "var_spec_list"
                else (child,)
            )
            for spec in specs:
                if spec.type == "var_spec":
                    self._spec(spec)
        self._visit_children(node)

    def _spec(self, spec: Node) -> None:
        name_node = spec.child_by_field_name("name")
        if name_node is None or name_node.type != "identifier":
            return
        name = _text(name_node)
        if name == "_":
            return
        value = spec.child_by_field_name("value")
        if value is not None:
            expressions = value.named_children
            self._bind(name, expressions[0] if expressions else None)
        else:
            self._bind_type(name, spec.child_by_field_name("type"))

    def _assign(self, node: Node) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        targets = left.named_children if left is not None else ()
        values = right.named_children if right is not None else ()
        for index, target in enumerate(targets):
            if target.type != "identifier" or _text(target) == "_":
                continue
            self._bind(_text(target), values[index] if index < len(values) else None)
        self._visit_children(node)

    def _literal(self, node: Node) -> None:
        chain = _type_chain(node.child_by_field_name("type"), self._roots)
        if chain is not None:
            for key in self._keys(node):
                self._emit(key, SiteShape.KEYWORD, _text(key), chain, True)
        self._visit_children(node)

    def _receiver(self, node: Node | None) -> tuple[str, ...] | None:
        """The type chain a bound receiver expression stands for."""
        node = _unwrap(node)
        if node is None:
            return None
        if node.type == "identifier":
            binding = self._bindings.get(_text(node))
            return binding.chain if binding is not None else None
        if node.type == "selector_expression":
            operand = node.child_by_field_name("operand")
            field = node.child_by_field_name("field")
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is None or function.type != "selector_expression":
                return None
            operand = function.child_by_field_name("operand")
            field = function.child_by_field_name("field")
        else:
            return None
        chain = self._receiver(operand)
        if chain is None or field is None:
            return None
        return chain + (_text(field),)

    def _selector(self, node: Node) -> None:
        operand = node.child_by_field_name("operand")
        field = node.child_by_field_name("field")
        receiver = self._receiver(operand)
        if field is not None and receiver is not None:
            binding = (
                self._bindings.get(_text(operand))
                if operand is not None and operand.type == "identifier"
                else None
            )
            chain = (
                binding.chain
                if binding is not None and binding.literal
                else receiver + (_text(field),)
            )
            self._emit(field, SiteShape.ATTRIBUTE, _text(field), chain, True)
        self._visit_children(node)

    def _argument(self, argument: Node, call_chain: tuple[str, ...]) -> None:
        node = _unwrap(argument)
        if node is None:
            return
        if node.type == "composite_literal":
            chain = _type_chain(node.child_by_field_name("type"), self._roots)
            if chain is not None:
                for key in self._keys(node):
                    self._emit(key, SiteShape.KEYWORD, _text(key), call_chain, True)
        elif node.type == "identifier":
            binding = self._bindings.get(_text(node))
            if binding is not None:
                for key in binding.fields:
                    self._emit(key, SiteShape.KEYWORD, _text(key), call_chain, True)
        elif node.type == "selector_expression":
            operand = node.child_by_field_name("operand")
            field = node.child_by_field_name("field")
            if (
                operand is not None
                and operand.type == "identifier"
                and field is not None
                and _text(operand) in self._bindings
            ):
                self._emit(
                    field, SiteShape.ATTRIBUTE, _text(field), call_chain, True
                )

    def _call(self, node: Node) -> None:
        function = node.child_by_field_name("function")
        call_chain: tuple[str, ...] | None = None
        if function is not None and function.type == "selector_expression":
            field = function.child_by_field_name("field")
            receiver = self._receiver(function.child_by_field_name("operand"))
            if field is not None and receiver is not None:
                call_chain = receiver + (_text(field),)
                self._emit(function, SiteShape.CALL, _text(field), call_chain, True)
                operand = function.child_by_field_name("operand")
                if operand is not None:
                    self.visit(operand)
            else:
                segments = _selector_segments(function)
                if segments is not None:
                    base, tail = segments
                    prefix = self._roots.get(base)
                    rooted = prefix is not None
                    chain = prefix + tail if rooted else tail
                    if tail:
                        self._emit(function, SiteShape.CALL, tail[-1], chain, rooted)
                    if rooted:
                        call_chain = chain
        arguments = node.child_by_field_name("arguments")
        if arguments is not None:
            if call_chain is not None:
                for argument in arguments.named_children:
                    self._argument(argument, call_chain)
            self.visit(arguments)
        if function is not None and function.type != "selector_expression":
            self.visit(function)

    def visit(self, node: Node) -> None:
        if node.type in {
            "function_declaration",
            "method_declaration",
            "func_literal",
        }:
            saved = self._bindings
            self._bindings = {}
            # Spec AC2: an annotated parameter is the body's initial receiver.
            self._parameters(node)
            self._visit_children(node)
            self._bindings = saved
        elif node.type == "call_expression":
            self._call(node)
        elif node.type == "short_var_declaration":
            self._short_var(node)
        elif node.type == "var_declaration":
            self._var(node)
        elif node.type == "assignment_statement":
            self._assign(node)
        elif node.type == "composite_literal":
            self._literal(node)
        elif node.type == "selector_expression":
            self._selector(node)
        else:
            self._visit_children(node)


def scan_go(
    root: str | Path,
    sdk_package: str,
    package_name: str | None = None,
    receivers: Mapping[str, str] | None = None,
) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted Go evidence."""
    modules: list[str] = []
    hits: list[Hit] = []
    for module in _read(Path(root)):
        roots, sdk_imported = _imports(module.tree, sdk_package, package_name)
        if not sdk_imported:
            continue
        visitor = _Visitor(
            module.source, roots, receivers or {}, _returns(module.tree, roots)
        )
        visitor.visit(module.tree.root_node)
        modules.append(module.rel)
        hits.extend(visitor.hits)
    return ScanResult(modules=tuple(modules), hits=tuple(hits))
