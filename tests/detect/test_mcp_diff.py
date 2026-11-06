import json
from pathlib import Path

from tenon.detect import ChangeKind, Location
from tenon.detect.mcp_diff import diff_mcp
from tenon.detect.mcp_ingest import load_mcp, parse_mcp

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mcp"


def a_document(*tools):
    return {"tools": {tool["name"]: tool for tool in tools}}


def a_tool(name, input_schema=None, output_schema=None):
    tool = {"name": name}
    if input_schema is not None:
        tool["inputSchema"] = input_schema
    if output_schema is not None:
        tool["outputSchema"] = output_schema
    return tool


def of_kind(result, kind):
    return [change for change in result.changes if change.kind is kind]


# Spec AC1: a removed tool is a breaking endpoint removal.
def test_a_removed_tool_is_a_breaking_endpoint_removal():
    old = load_mcp(FIXTURES / "tools-v1.json")
    new = load_mcp(FIXTURES / "tools-v2.json")

    removed = of_kind(diff_mcp(old, new), ChangeKind.ENDPOINT_REMOVED)

    assert len(removed) == 1
    change = removed[0]
    assert change.location == Location(
        pointer="#/tools/list_files", method="tool", path="list_files"
    )
    assert change.before == "list_files"
    assert change.after is None
    assert change.breaking is True


# Spec AC1: an added tool is a non-breaking endpoint addition.
def test_an_added_tool_is_a_non_breaking_endpoint_addition():
    old = load_mcp(FIXTURES / "tools-v1.json")
    new = load_mcp(FIXTURES / "tools-v2.json")

    added = of_kind(diff_mcp(old, new), ChangeKind.ENDPOINT_ADDED)

    assert len(added) == 1
    change = added[0]
    assert change.location == Location(
        pointer="#/tools/write_file", method="tool", path="write_file"
    )
    assert change.before is None
    assert change.after == "write_file"
    assert change.breaking is False


# Spec AC1: tool names in pointers are RFC 6901-escaped.
def test_a_tool_name_is_escaped_in_the_pointer():
    old = a_document(a_tool("a/b~c"))

    removed = of_kind(diff_mcp(old, a_document()), ChangeKind.ENDPOINT_REMOVED)

    assert len(removed) == 1
    assert removed[0].location.pointer == "#/tools/a~1b~0c"
    assert removed[0].location.path == "a/b~c"


# Spec AC1/S2: tool order in the input does not change the result.
def test_tool_order_is_irrelevant():
    raw = json.loads((FIXTURES / "tools-v2.json").read_text(encoding="utf-8"))
    raw["tools"].reverse()
    reordered = parse_mcp(json.dumps(raw), "<inline>")
    old = load_mcp(FIXTURES / "tools-v1.json")
    new = load_mcp(FIXTURES / "tools-v2.json")

    assert diff_mcp(old, reordered).to_json() == diff_mcp(old, new).to_json()
