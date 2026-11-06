"""Turn a saved MCP ``tools/list`` result into a name-keyed document, or refuse it by name."""

from pathlib import Path

import yaml

from .ingest import _escape
from .record import RefusalCode, SpecRefusal


def parse_mcp(text: str, source: str) -> dict:
    """Return the normalized document for ``text``, or refuse it by name."""
    if not text.strip():
        raise SpecRefusal(RefusalCode.UNPARSEABLE, message=f"{source}: empty document")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        position = (
            f"line {mark.line + 1}, column {mark.column + 1}" if mark else "unknown position"
        )
        problem = getattr(exc, "problem", None) or "invalid YAML"
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{source}: {problem} at {position}"
        ) from None
    if isinstance(document, list):
        tools = document
    elif isinstance(document, dict):
        if "tools" not in document:
            raise SpecRefusal(
                RefusalCode.NOT_A_SPEC,
                "#/tools",
                message=f"{source}: no 'tools' list",
            )
        tools = document["tools"]
    else:
        raise SpecRefusal(
            RefusalCode.NOT_A_SPEC, "#", message=f"{source}: not a tools/list result"
        )
    if not isinstance(tools, list):
        raise SpecRefusal(
            RefusalCode.NOT_A_SPEC, "#/tools", message=f"{source}: 'tools' is not a list"
        )
    normalized: dict[str, dict] = {}
    for index, tool in enumerate(tools):
        where = f"#/tools/{index}"
        if not isinstance(tool, dict):
            raise SpecRefusal(
                RefusalCode.NOT_A_SPEC,
                where,
                message=f"{source}: tool is not a mapping",
            )
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            raise SpecRefusal(
                RefusalCode.NOT_A_SPEC,
                f"{where}/name",
                message=f"{source}: tool has no non-empty name",
            )
        escaped = _escape(name)
        if name in normalized:
            raise SpecRefusal(
                RefusalCode.NOT_A_SPEC,
                f"#/tools/{escaped}",
                message=f"{source}: duplicate tool name {name!r}",
            )
        for key in ("inputSchema", "outputSchema"):
            if key in tool and not isinstance(tool[key], dict):
                raise SpecRefusal(
                    RefusalCode.NOT_A_SPEC,
                    f"#/tools/{escaped}/{key}",
                    message=f"{source}: {key} is not a mapping",
                )
        normalized[name] = tool
    return {"tools": normalized}


def load_mcp(path: str | Path) -> dict:
    """Read ``path`` as UTF-8 and return the document from :func:`parse_mcp`."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{path}: cannot read: {exc}"
        ) from None
    return parse_mcp(text, str(path))
