"""Turn a saved MCP ``tools/list`` result into a name-keyed document."""

from pathlib import Path

import yaml


def parse_mcp(text: str, source: str) -> dict:
    """Return the normalized document for ``text``."""
    document = yaml.safe_load(text)
    if isinstance(document, dict):
        tools = document["tools"]
    else:
        tools = document
    return {"tools": {tool["name"]: tool for tool in tools}}


def load_mcp(path: str | Path) -> dict:
    """Read ``path`` as UTF-8 and return the document from :func:`parse_mcp`."""
    path = Path(path)
    return parse_mcp(path.read_text(encoding="utf-8"), str(path))
