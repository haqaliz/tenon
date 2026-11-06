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


def a_payload(name, type_, fmt=None):
    return {"name": name, "type": type_, "format": fmt}


INPUT = "#/tools/read_file/inputSchema/properties"


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


# Spec AC2: a removed input property is breaking and uses T1's record shape.
def test_a_removed_input_property_is_breaking():
    old = load_mcp(FIXTURES / "tools-input-v1.json")
    new = load_mcp(FIXTURES / "tools-input-v2.json")

    removed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_REMOVED)

    assert len(removed) == 1
    change = removed[0]
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before == a_payload("max_bytes", "integer")
    assert change.after is None
    assert change.breaking is True
    assert change.confidence == "certain"


# Spec AC2: a new optional input property is not breaking.
def test_an_added_input_property_is_not_breaking():
    old = load_mcp(FIXTURES / "tools-input-v1.json")
    new = load_mcp(FIXTURES / "tools-input-v2.json")

    added = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_ADDED)

    assert len(added) == 1
    change = added[0]
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before is None
    assert change.after == a_payload("encoding", "string")
    assert change.breaking is False


# Spec AC2: a new required input property is a breaking required-added record.
def test_a_new_required_input_property_is_breaking():
    old = load_mcp(FIXTURES / "tools-input-v1.json")
    new = load_mcp(FIXTURES / "tools-input-v2.json")

    required = [
        change
        for change in of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_REQUIRED_ADDED)
        if change.after == a_payload("offset", "string")
    ]

    assert len(required) == 1
    change = required[0]
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before is None
    assert change.breaking is True


# Spec AC2: an existing input property becoming required is breaking.
def test_an_existing_input_property_becoming_required_is_breaking():
    old = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        )
    )
    new = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
    )

    changes = diff_mcp(old, new).changes

    assert len(changes) == 1
    change = changes[0]
    assert change.kind is ChangeKind.PROPERTY_REQUIRED_ADDED
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before == a_payload("path", "string")
    assert change.after == a_payload("path", "string")
    assert change.breaking is True


# Spec AC2: a changed input property type is breaking.
def test_a_changed_input_property_type_is_breaking():
    old = load_mcp(FIXTURES / "tools-input-v1.json")
    new = load_mcp(FIXTURES / "tools-input-v2.json")

    changed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_TYPE_CHANGED)

    assert len(changed) == 1
    change = changed[0]
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before == a_payload("limit", "integer")
    assert change.after == a_payload("limit", "string")
    assert change.breaking is True


# Spec AC2: a strict subset enum is a breaking narrowing.
def test_a_narrowed_input_enum_is_breaking():
    old = load_mcp(FIXTURES / "tools-input-v1.json")
    new = load_mcp(FIXTURES / "tools-input-v2.json")

    narrowed = of_kind(diff_mcp(old, new), ChangeKind.ENUM_NARROWED)

    assert len(narrowed) == 1
    change = narrowed[0]
    assert change.location == Location(pointer=INPUT, method="tool", path="read_file")
    assert change.before == {
        "name": "mode",
        "enum": ["append", "read", "write"],
    }
    assert change.after == {"name": "mode", "enum": ["append", "read"]}
    assert change.breaking is True


# Spec AC2: a widened or reordered enum is not a narrowing.
def test_a_widened_or_reordered_input_enum_is_not_a_change():
    for old_values, new_values in (
        (["a"], ["a", "b"]),
        (["b", "a"], ["a", "b"]),
        (["a", "b"], ["a", "b"]),
    ):
        old = a_document(
            a_tool(
                "read_file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": old_values}
                    },
                },
            )
        )
        new = a_document(
            a_tool(
                "read_file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": new_values}
                    },
                },
            )
        )

        assert of_kind(diff_mcp(old, new), ChangeKind.ENUM_NARROWED) == []
