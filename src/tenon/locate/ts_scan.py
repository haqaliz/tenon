"""Read-only tree-sitter scan for TS/JS names rooted in an npm package.

The scan reports evidence only: every hit carries ``rooted`` and every construct
it cannot see through becomes a :class:`Dynamic`. Whether a hit is certain is
decided elsewhere.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser, Tree

from .scan import Dynamic, Hit, ScanResult, _Source

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


def _specifiers(tree: Tree) -> Iterator[str]:
    for node in _walk(tree.root_node):
        if node.type == "import_statement":
            specifier = _string_value(node.child_by_field_name("source"))
        elif node.type == "call_expression":
            specifier = _require_source(node)
        else:
            continue
        if specifier is not None:
            yield specifier


def _reachable(modules: list[_Module], sdk_package: str) -> list[_Module]:
    return [
        module
        for module in modules
        if any(_is_sdk(specifier, sdk_package) for specifier in _specifiers(module.tree))
    ]


def scan_ts(root: str | Path, sdk_package: str) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted TS/JS evidence."""
    modules = _read(Path(root))
    reachable = _reachable(modules, sdk_package)
    return ScanResult(
        modules=tuple(module.rel for module in reachable),
        hits=tuple[Hit](),
        dynamics=tuple[Dynamic](),
    )
