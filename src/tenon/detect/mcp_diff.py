"""Compare two normalized MCP ``tools/list`` documents and emit typed changes."""

from .diff import _escape
from .record import Change, ChangeKind, DiffResult, Location
from .rename import infer_renames


def diff_mcp(old: dict, new: dict) -> DiffResult:
    """Every change between two normalized MCP documents, canonically ordered."""
    old_tools = _tools_of(old)
    new_tools = _tools_of(new)
    changes: list[Change] = []
    for name in sorted(old_tools):
        if name not in new_tools:
            changes.append(_tool_change(ChangeKind.ENDPOINT_REMOVED, name))
    for name in sorted(new_tools):
        if name not in old_tools:
            changes.append(_tool_change(ChangeKind.ENDPOINT_ADDED, name))
    return DiffResult(infer_renames(changes))


def _tools_of(document: dict) -> dict:
    tools = document.get("tools") if isinstance(document, dict) else None
    return tools if isinstance(tools, dict) else {}


def _tool_change(kind: ChangeKind, name: str) -> Change:
    removed = kind is ChangeKind.ENDPOINT_REMOVED
    return Change(
        kind=kind,
        location=Location(
            pointer=f"#/tools/{_escape(name)}", method="tool", path=name
        ),
        before=name if removed else None,
        after=None if removed else name,
        breaking=removed,
    )
