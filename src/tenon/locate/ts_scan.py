"""Read-only tree-sitter scan for TS/JS names rooted in an npm package.

The scan reports evidence only: every hit carries ``rooted`` and every construct
it cannot see through becomes a :class:`Dynamic`. Whether a hit is certain is
decided elsewhere.
"""

import posixpath
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser, Tree

from .scan import Dynamic, DynamicKind, Hit, ScanResult, _Source, _column

_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_SKIP_DIRECTORIES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "out",
        "coverage",
        ".turbo",
        "__pycache__",
    }
)
_TYPESCRIPT_EXTENSIONS = frozenset({".ts", ".mts", ".cts"})
_JAVASCRIPT_EXTENSIONS = frozenset({".js", ".jsx", ".mjs", ".cjs"})


@dataclass(frozen=True, slots=True)
class _Module:
    rel: str
    tree: Tree
    source: _Source


@cache
def _parser(grammar: str) -> Parser:
    language = {
        "typescript": Language(tsts.language_typescript()),
        "tsx": Language(tsts.language_tsx()),
        "javascript": Language(tsjs.language()),
    }[grammar]
    return Parser(language)


def _grammar(suffix: str) -> str:
    if suffix == ".tsx":
        return "tsx"
    if suffix in _JAVASCRIPT_EXTENSIONS:
        return "javascript"
    return "typescript"


def _files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if path.suffix not in _EXTENSIONS or not path.is_file():
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
            tree = _parser(_grammar(path.suffix)).parse(text.encode("utf-8"))
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


def _string_value(node: Node | None) -> str | None:
    if node is None or node.type != "string":
        return None
    text = node.text
    if text is None or len(text) < 2:
        return None
    return text.decode("utf-8")[1:-1]


def _is_sdk(specifier: str, sdk_package: str) -> bool:
    return specifier == sdk_package or specifier.startswith(f"{sdk_package}/")


def _require_source(call: Node) -> str | None:
    function = call.child_by_field_name("function")
    if (
        function is None
        or function.type != "identifier"
        or function.text != b"require"
    ):
        return None
    arguments = call.child_by_field_name("arguments")
    if arguments is None or len(arguments.named_children) != 1:
        return None
    return _string_value(arguments.named_children[0])


def _text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""


def _type_only(node: Node) -> bool:
    return any(
        child.type == "type" and not child.is_named for child in node.children
    )


def _import_source(node: Node) -> str | None:
    source = node.child_by_field_name("source")
    if source is None:
        for child in node.named_children:
            if child.type == "import_require_clause":
                source = child.child_by_field_name("source")
                break
    return _string_value(source)


def _runtime_specifiers(tree: Tree) -> Iterator[str]:
    for node in _walk(tree.root_node):
        if node.type == "import_statement":
            if _type_only(node):
                continue
            specifier = _import_source(node)
        elif node.type == "call_expression":
            specifier = _require_source(node)
        else:
            continue
        if specifier is not None:
            yield specifier


def _import_bindings(
    node: Node, sdk_package: str
) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    specifier = _import_source(node)
    if (
        specifier is None
        or not _is_sdk(specifier, sdk_package)
        or _type_only(node)
    ):
        return {}, set()
    base = tuple(specifier.split("/"))
    roots: dict[str, tuple[str, ...]] = {}
    classes: set[str] = set()
    for clause in node.named_children:
        if clause.type == "import_require_clause":
            identifier = next(
                (child for child in clause.named_children if child.type == "identifier"),
                None,
            )
            if identifier is not None:
                roots[_text(identifier)] = base
        elif clause.type == "import_clause":
            for child in clause.named_children:
                if child.type == "identifier":
                    name = _text(child)
                    roots[name] = base + (name,)
                    classes.add(name)
                elif child.type == "namespace_import":
                    identifier = next(
                        (
                            item
                            for item in child.named_children
                            if item.type == "identifier"
                        ),
                        None,
                    )
                    if identifier is not None:
                        roots[_text(identifier)] = base
                elif child.type == "named_imports":
                    for spec in child.named_children:
                        if spec.type != "import_specifier" or _type_only(spec):
                            continue
                        name_node = spec.child_by_field_name("name")
                        if name_node is None:
                            continue
                        name = _text(name_node)
                        alias_node = spec.child_by_field_name("alias")
                        binding = _text(alias_node) if alias_node is not None else name
                        roots[binding] = base + (name,)
                        classes.add(binding)
    return roots, classes


def _pattern_bindings(
    pattern: Node, base: tuple[str, ...]
) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    roots: dict[str, tuple[str, ...]] = {}
    classes: set[str] = set()
    for child in pattern.named_children:
        if child.type == "shorthand_property_identifier_pattern":
            name = _text(child)
            roots[name] = base + (name,)
            classes.add(name)
        elif child.type == "pair_pattern":
            key = child.child_by_field_name("key")
            value = child.child_by_field_name("value")
            if key is None or value is None or value.type != "identifier":
                continue
            name = _string_value(key) if key.type == "string" else _text(key)
            if name is None:
                continue
            binding = _text(value)
            roots[binding] = base + (name,)
            classes.add(binding)
    return roots, classes


def _require_bindings(
    declarator: Node, sdk_package: str
) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    value = declarator.child_by_field_name("value")
    if value is None or value.type != "call_expression":
        return {}, set()
    specifier = _require_source(value)
    if specifier is None or not _is_sdk(specifier, sdk_package):
        return {}, set()
    base = tuple(specifier.split("/"))
    name = declarator.child_by_field_name("name")
    if name is None:
        return {}, set()
    if name.type == "identifier":
        return {_text(name): base}, set()
    if name.type == "object_pattern":
        return _pattern_bindings(name, base)
    return {}, set()


def _bindings(
    tree: Tree, sdk_package: str
) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    """Names bound to the SDK, and the names that look like classes."""
    roots: dict[str, tuple[str, ...]] = {}
    classes: set[str] = set()
    for node in _walk(tree.root_node):
        if node.type == "import_statement":
            imported, imported_classes = _import_bindings(node, sdk_package)
        elif node.type == "variable_declarator":
            imported, imported_classes = _require_bindings(node, sdk_package)
        else:
            continue
        roots.update(imported)
        classes.update(imported_classes)
    return roots, classes


def _dynamic(
    source: _Source,
    node: Node,
    kind: DynamicKind,
    symbol: str | None = None,
    chain: tuple[str, ...] = (),
) -> Dynamic:
    line = source.lines[node.start_point.row]
    return Dynamic(
        source.path,
        node.start_point.row + 1,
        _column(line, node.start_point.column),
        kind,
        symbol,
        chain,
    )


def _unwrap(node: Node | None) -> Node | None:
    while node is not None and node.type in {
        "parenthesized_expression",
        "as_expression",
        "satisfies_expression",
        "non_null_expression",
    }:
        node = node.named_children[0] if node.named_children else None
    return node


def _parts(node: Node | None) -> tuple[str | None, tuple[str, ...]]:
    tail = []
    while node is not None and node.type == "member_expression":
        property_node = node.child_by_field_name("property")
        if property_node is None:
            break
        tail.append(_text(property_node))
        node = node.child_by_field_name("object")
    node = _unwrap(node)
    root = _text(node) if node is not None and node.type == "identifier" else None
    tail.reverse()
    return root, tuple(tail)


def _full(
    root: str | None,
    tail: tuple[str, ...],
    roots: dict[str, tuple[str, ...]],
    sdk_parts: tuple[str, ...],
) -> tuple[str, ...] | None:
    if root is None or root not in roots:
        return None
    full = roots[root] + tail
    return full if full[: len(sdk_parts)] == sdk_parts else None


def _alias_cycle(pending: dict[str, str], target: str, rhs: str) -> bool:
    if target == rhs:
        return True
    seen = {target}
    name = rhs
    while name in pending:
        if name in seen:
            return True
        seen.add(name)
        name = pending[name]
    return name in seen


def _pattern_names(pattern: Node) -> Iterator[Node]:
    for node in _walk(pattern):
        if node.type in {"shorthand_property_identifier_pattern", "identifier"}:
            yield node


def _aliases(
    tree: Tree,
    roots: dict[str, tuple[str, ...]],
    classes: set[str],
    sdk_package: str,
    source: _Source,
) -> tuple[dict[str, tuple[str, ...]], set[str], list[Dynamic]]:
    """One-hop aliases in source order; a second Name hop is a dynamic."""
    sdk_parts = tuple(sdk_package.split("/"))
    aliases: dict[str, tuple[str, ...]] = {}
    hops: dict[str, int] = {}
    class_aliases: set[str] = set()
    dynamics: list[Dynamic] = []
    pending: dict[str, str] = {}
    events: list[tuple[int, Node, Node | None]] = []

    for node in _walk(tree.root_node):
        if node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            if name is not None:
                events.append((node.start_byte, name, node.child_by_field_name("value")))
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                events.append(
                    (node.start_byte, left, node.child_by_field_name("right"))
                )
    events.sort(key=lambda event: event[0])

    def forget(name: str) -> None:
        aliases.pop(name, None)
        hops.pop(name, None)
        class_aliases.discard(name)
        pending.pop(name, None)

    def bind(name: str, target: Node, value: Node | None) -> None:
        value = _unwrap(value)
        if value is None:
            return
        if value.type == "identifier":
            rhs = _text(value)
            if _alias_cycle(pending, name, rhs):
                dynamics.append(
                    _dynamic(source, target, DynamicKind.ALIAS_CHAIN, name)
                )
                return
            if rhs in aliases:
                if hops[rhs] >= 1:
                    dynamics.append(
                        _dynamic(source, target, DynamicKind.ALIAS_CHAIN, name)
                    )
                    return
                full = aliases[rhs]
                hop = 1
                if rhs in class_aliases:
                    class_aliases.add(name)
            elif rhs in roots:
                full = roots[rhs]
                hop = 0
                if rhs in classes:
                    class_aliases.add(name)
            else:
                pending[name] = rhs
                return
        elif value.type in {"call_expression", "new_expression"}:
            function = value.child_by_field_name(
                "function" if value.type == "call_expression" else "constructor"
            )
            root, tail = _parts(function)
            if _full(root, tail, roots, sdk_parts) is None:
                return
            full = sdk_parts
            hop = 0
            if function is not None and function.type == "identifier":
                if _text(function) in classes:
                    class_aliases.add(name)
        elif value.type == "member_expression":
            root, tail = _parts(value)
            full = _full(root, tail, roots, sdk_parts)
            if full is None:
                return
            hop = 0
        else:
            return
        aliases[name] = full
        hops[name] = hop

    def destructure(pattern: Node, value: Node | None) -> None:
        value = _unwrap(value)
        if value is None:
            return
        root, tail = _parts(value)
        full = _full(root, tail, roots, sdk_parts)
        if full is None:
            return
        for child in pattern.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                name = _text(child)
                aliases[name] = full + (name,)
                hops[name] = 0
            elif child.type == "pair_pattern":
                key = child.child_by_field_name("key")
                member = child.child_by_field_name("value")
                if key is None or member is None:
                    continue
                member_name = (
                    _string_value(key) if key.type == "string" else _text(key)
                )
                if member_name is None:
                    continue
                if member.type == "identifier":
                    aliases[_text(member)] = full + (member_name,)
                    hops[_text(member)] = 0
                else:
                    for binding in _pattern_names(member):
                        dynamics.append(
                            _dynamic(
                                source,
                                binding,
                                DynamicKind.ALIAS_CHAIN,
                                _text(binding),
                            )
                        )
            elif child.type in {"rest_pattern", "array_pattern"}:
                for binding in _pattern_names(child):
                    dynamics.append(
                        _dynamic(
                            source,
                            binding,
                            DynamicKind.ALIAS_CHAIN,
                            _text(binding),
                        )
                    )

    for _, target, value in events:
        if target.type == "identifier":
            name = _text(target)
            forget(name)
            bind(name, target, value)
        elif target.type == "object_pattern":
            for binding in _pattern_names(target):
                forget(_text(binding))
            destructure(target, value)

    return aliases, class_aliases, dynamics


def _resolve_relative(
    importer: str, specifier: str, files: set[str]
) -> str | None:
    target = posixpath.normpath(
        posixpath.join(posixpath.dirname(importer), specifier)
    )
    candidates = [
        target,
        *(target + extension for extension in _EXTENSIONS),
        *(f"{target}/index{extension}" for extension in _EXTENSIONS),
    ]
    return next((candidate for candidate in candidates if candidate in files), None)


def _reachable(modules: list[_Module], sdk_package: str) -> list[_Module]:
    files = {module.rel for module in modules}
    by_rel = {module.rel: module for module in modules}
    specifiers = {
        module.rel: tuple(_runtime_specifiers(module.tree)) for module in modules
    }
    importers: dict[str, set[str]] = {}
    for module in modules:
        for specifier in specifiers[module.rel]:
            if not specifier.startswith("."):
                continue
            target = _resolve_relative(module.rel, specifier, files)
            if target is not None:
                importers.setdefault(target, set()).add(module.rel)
    queue = deque(
        module.rel
        for module in modules
        if any(_is_sdk(specifier, sdk_package) for specifier in specifiers[module.rel])
    )
    seen: set[str] = set()
    while queue:
        rel = queue.popleft()
        if rel in seen:
            continue
        seen.add(rel)
        for importer in importers.get(rel, ()):
            if importer not in seen:
                queue.append(importer)
    return [by_rel[rel] for rel in sorted(seen)]


def scan_ts(root: str | Path, sdk_package: str) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted TS/JS evidence."""
    modules = _read(Path(root))
    reachable = _reachable(modules, sdk_package)
    return ScanResult(
        modules=tuple(module.rel for module in reachable),
        hits=tuple[Hit](),
        dynamics=tuple[Dynamic](),
    )
