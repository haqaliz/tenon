"""Read-only AST scan for names rooted in an SDK package.

The scan reports evidence only: every hit carries ``rooted`` and every construct
it cannot see through becomes a :class:`Dynamic`. Whether a hit is certain is
decided elsewhere.
"""

import ast
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Sequence

from .result import SiteShape

_SKIP_DIRECTORIES = frozenset({".venv", "node_modules", "build", "dist", "__pycache__"})


class DynamicKind(StrEnum):
    """A construct the scanner cannot see through."""

    STAR_KWARGS = "star_kwargs"
    STAR_ARGS = "star_args"
    GETATTR = "getattr"
    ALIAS_CHAIN = "alias_chain"


@dataclass(frozen=True, slots=True)
class Hit:
    """One expression that mentions a name, rooted in the SDK or not."""

    path: str
    line: int
    column: int
    shape: SiteShape
    symbol: str
    chain: tuple[str, ...]
    rooted: bool
    line_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shape, SiteShape):
            object.__setattr__(self, "shape", SiteShape(self.shape))
        object.__setattr__(self, "chain", tuple(self.chain))


@dataclass(frozen=True, slots=True)
class Dynamic:
    """A construct that hides at least one name from static inspection."""

    path: str
    line: int
    column: int
    kind: DynamicKind
    symbol: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DynamicKind):
            object.__setattr__(self, "kind", DynamicKind(self.kind))


def _hit_key(hit: Hit) -> tuple:
    return (
        hit.path,
        hit.line,
        hit.column,
        hit.shape.value,
        hit.symbol,
        hit.chain,
        hit.rooted,
        hit.line_text or "",
    )


def _dynamic_key(dynamic: Dynamic) -> tuple:
    return (
        dynamic.path,
        dynamic.line,
        dynamic.column,
        dynamic.kind.value,
        dynamic.symbol or "",
    )


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Everything the scan found in one repository. Canonically ordered."""

    modules: Sequence[str] = ()
    hits: Sequence[Hit] = ()
    dynamics: Sequence[Dynamic] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", tuple(sorted(set(self.modules))))
        object.__setattr__(
            self, "hits", tuple(sorted(set(self.hits), key=_hit_key))
        )
        object.__setattr__(
            self, "dynamics", tuple(sorted(set(self.dynamics), key=_dynamic_key))
        )


@dataclass(frozen=True, slots=True)
class _Source:
    path: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Module:
    rel: str
    name: str
    is_package: bool
    tree: ast.Module
    source: _Source


def scan(root: str | Path, sdk_package: str) -> ScanResult:
    """Parse ``root`` read-only and report SDK-rooted evidence."""
    modules = _read(Path(root))
    reachable = _reachable(modules, sdk_package)
    return ScanResult(modules=tuple(module.rel for module in reachable))


def _modules(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.py"):
        directories = path.relative_to(root).parts[:-1]
        if any(
            directory in _SKIP_DIRECTORIES or directory.startswith(".")
            for directory in directories
        ):
            continue
        found.append(path)
    return sorted(found)


def _module_name(rel: Path) -> tuple[str, bool]:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return "", False
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _read(root: Path) -> list[_Module]:
    modules = []
    for path in _modules(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            continue
        name, is_package = _module_name(path.relative_to(root))
        source = _Source(rel, tuple(text.split("\n")))
        modules.append(_Module(rel, name, is_package, tree, source))
    return modules


def _is_sdk(name: str, sdk_package: str) -> bool:
    return (
        name == sdk_package
        or name.startswith(f"{sdk_package}.")
        or sdk_package.startswith(f"{name}.")
    )


def _import_base(module: _Module, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return ""
    package = module.name if module.is_package else module.name.rpartition(".")[0]
    parts = package.split(".") if package else []
    upward = node.level - 1
    if upward >= len(parts):
        return None
    return ".".join(parts[: len(parts) - upward])


def _import_candidates(base: str, node: ast.ImportFrom) -> list[str]:
    module = f"{base}.{node.module}" if base and node.module else node.module or base
    candidates = [module] if module else []
    for alias in node.names:
        if alias.name != "*":
            candidates.append(f"{module}.{alias.name}" if module else alias.name)
    return candidates


def _imports(
    module: _Module, names: dict[str, _Module], sdk_package: str
) -> tuple[set[str], set[str]]:
    direct: set[str] = set()
    local: set[str] = set()
    for node in module.tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_sdk(alias.name, sdk_package):
                    direct.add(alias.name)
                target = alias.name if alias.name in names else alias.name.split(".")[0]
                if target in names:
                    local.add(target)
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(module, node)
            if base is None:
                continue
            if node.level == 0 and node.module and _is_sdk(node.module, sdk_package):
                direct.add(node.module)
            for candidate in _import_candidates(base, node):
                if candidate in names:
                    local.add(candidate)
    return direct, local


def _reachable(modules: list[_Module], sdk_package: str) -> list[_Module]:
    names: dict[str, _Module] = {}
    for module in modules:
        names.setdefault(module.name, module)
    edges = {
        module.rel: _imports(module, names, sdk_package) for module in modules
    }
    importers: dict[str, set[str]] = {}
    for module in modules:
        for target in edges[module.rel][1]:
            importers.setdefault(names[target].rel, set()).add(module.rel)
    queue = deque(
        module.rel
        for module in modules
        if any(_is_sdk(name, sdk_package) for name in edges[module.rel][0])
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
    by_rel = {module.rel: module for module in modules}
    return [by_rel[rel] for rel in sorted(seen)]


def _bindings(
    tree: ast.Module, sdk_package: str
) -> tuple[dict[str, tuple[str, ...]], set[str], set[tuple[str, ...]]]:
    """Names bound to the SDK, the class names, and their full dotted paths."""
    roots: dict[str, tuple[str, ...]] = {}
    classes: set[str] = set()
    class_paths: set[tuple[str, ...]] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_sdk(alias.name, sdk_package):
                    continue
                full = tuple(alias.name.split("."))
                roots[alias.asname or full[0]] = (
                    full if alias.asname else full[:1]
                )
        elif isinstance(node, ast.ImportFrom):
            if (
                node.level
                or not node.module
                or not _is_sdk(node.module, sdk_package)
            ):
                continue
            base = tuple(node.module.split("."))
            for alias in node.names:
                if alias.name == "*":
                    continue
                full = base + (alias.name,)
                name = alias.asname or alias.name
                roots[name] = full
                classes.add(name)
                class_paths.add(full)
    return roots, classes, class_paths


def _parts(node: ast.expr) -> tuple[str | None, tuple[str, ...]]:
    """The root name and attribute tail of a dotted expression."""
    tail = []
    while isinstance(node, ast.Attribute):
        tail.append(node.attr)
        node = node.value
    tail.reverse()
    return (node.id if isinstance(node, ast.Name) else None), tuple(tail)


def _full(
    root: str | None,
    tail: tuple[str, ...],
    roots: dict[str, tuple[str, ...]],
    sdk_parts: tuple[str, ...],
) -> tuple[str, ...] | None:
    """The full dotted path when it starts at the SDK root, else ``None``."""
    if root is None or root not in roots:
        return None
    full = roots[root] + tail
    return full if full[: len(sdk_parts)] == sdk_parts else None


def _dynamic(
    source: _Source, node: ast.AST, kind: DynamicKind, symbol: str | None = None
) -> Dynamic:
    return Dynamic(source.path, node.lineno, node.col_offset + 1, kind, symbol)


def _aliases(
    tree: ast.Module,
    roots: dict[str, tuple[str, ...]],
    class_paths: set[tuple[str, ...]],
    source: _Source,
    sdk_package: str,
) -> tuple[dict[str, tuple[str, ...]], set[str], list[Dynamic]]:
    """One-hop aliases in source order; a second hop becomes a dynamic."""
    sdk_parts = tuple(sdk_package.split("."))
    aliases: dict[str, tuple[str, ...]] = {}
    class_aliases: set[str] = set()
    dynamics: list[Dynamic] = []
    assigned: set[str] = set()
    nodes = sorted(
        (node for node in ast.walk(tree) if isinstance(node, ast.Assign)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in nodes:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0]
        value = node.value
        if isinstance(value, ast.Name):
            if value.id in assigned:
                dynamics.append(
                    _dynamic(source, target, DynamicKind.ALIAS_CHAIN, target.id)
                )
                continue
            full = roots.get(value.id)
        elif isinstance(value, ast.Call):
            root, tail = _parts(value.func)
            full = _full(root, tail, roots, sdk_parts)
            if full is not None:
                class_aliases.update(
                    {target.id} if full in class_paths else set()
                )
                full = sdk_parts
        elif isinstance(value, ast.Attribute):
            root, tail = _parts(value)
            full = _full(root, tail, roots, sdk_parts)
        else:
            full = None
        if full is None:
            continue
        aliases[target.id] = full
        assigned.add(target.id)
        if full in class_paths:
            class_aliases.add(target.id)
    return aliases, class_aliases, dynamics
