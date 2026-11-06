import json
from pathlib import Path

from tenon.detect import ChangeKind, Location, diff
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
OUTPUT = "#/tools/read_file/outputSchema/properties"
ADDITIONAL = "#/tools/read_file/inputSchema"


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


# Spec AC3: a removed output property is breaking.
def test_a_removed_output_property_is_breaking():
    old = load_mcp(FIXTURES / "tools-output-v1.json")
    new = load_mcp(FIXTURES / "tools-output-v2.json")

    removed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_REMOVED)

    assert len(removed) == 1
    change = removed[0]
    assert change.location == Location(pointer=OUTPUT, method="tool", path="read_file")
    assert change.before == a_payload("content", "string")
    assert change.after is None
    assert change.breaking is True


# Spec AC3: added output properties are not breaking.
def test_added_output_properties_are_not_breaking():
    old = load_mcp(FIXTURES / "tools-output-v1.json")
    new = load_mcp(FIXTURES / "tools-output-v2.json")

    added = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_ADDED)

    assert [(change.before, change.after, change.breaking) for change in added] == [
        (None, a_payload("bytes", "string"), False),
        (None, a_payload("checksum", "string"), False),
    ]
    assert {change.location.pointer for change in added} == {OUTPUT}


# Spec AC3: a new required output property is an addition, never required-added.
def test_a_new_required_output_property_is_not_required_added():
    old = load_mcp(FIXTURES / "tools-output-v1.json")
    new = load_mcp(FIXTURES / "tools-output-v2.json")

    result = diff_mcp(old, new)

    assert of_kind(result, ChangeKind.PROPERTY_REQUIRED_ADDED) == []
    checksum = [
        change
        for change in of_kind(result, ChangeKind.PROPERTY_ADDED)
        if change.after == a_payload("checksum", "string")
    ]
    assert len(checksum) == 1
    assert checksum[0].breaking is False


# Spec AC3: a changed output property type is breaking.
def test_a_changed_output_property_type_is_breaking():
    old = load_mcp(FIXTURES / "tools-output-v1.json")
    new = load_mcp(FIXTURES / "tools-output-v2.json")

    changed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_TYPE_CHANGED)

    assert len(changed) == 1
    change = changed[0]
    assert change.location == Location(pointer=OUTPUT, method="tool", path="read_file")
    assert change.before == a_payload("size", "integer")
    assert change.after == a_payload("size", "string")
    assert change.breaking is True


# Spec AC3: a narrowed output enum is breaking.
def test_a_narrowed_output_enum_is_breaking():
    old = load_mcp(FIXTURES / "tools-output-v1.json")
    new = load_mcp(FIXTURES / "tools-output-v2.json")

    narrowed = of_kind(diff_mcp(old, new), ChangeKind.ENUM_NARROWED)

    assert len(narrowed) == 1
    change = narrowed[0]
    assert change.location == Location(pointer=OUTPUT, method="tool", path="read_file")
    assert change.before == {
        "name": "mode",
        "enum": ["fast", "safe", "strict"],
    }
    assert change.after == {"name": "mode", "enum": ["fast", "safe"]}
    assert change.breaking is True


# Spec AC4: open/absent to closed is a breaking additionalProperties change.
def test_closing_additional_properties_is_breaking():
    old = load_mcp(FIXTURES / "tools-additional-v1.json")
    new = load_mcp(FIXTURES / "tools-additional-v2.json")

    changes = of_kind(
        diff_mcp(old, new), ChangeKind.ADDITIONAL_PROPERTIES_CHANGED
    )

    assert len(changes) == 1
    change = changes[0]
    assert change.location == Location(pointer=ADDITIONAL, method="tool", path="read_file")
    assert change.before is None
    assert change.after is False
    assert change.breaking is True


# Spec AC4: closed to open is a non-breaking widening.
def test_widening_additional_properties_is_not_breaking():
    old = load_mcp(FIXTURES / "tools-additional-v2.json")
    new = load_mcp(FIXTURES / "tools-additional-v1.json")

    changes = of_kind(
        diff_mcp(old, new), ChangeKind.ADDITIONAL_PROPERTIES_CHANGED
    )

    assert len(changes) == 1
    change = changes[0]
    assert change.before is False
    assert change.after is None
    assert change.breaking is False


# Spec AC4: true to false is a closing and therefore breaking.
def test_true_to_false_additional_properties_is_breaking():
    old = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": True,
            },
        )
    )
    new = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
        )
    )

    changes = of_kind(
        diff_mcp(old, new), ChangeKind.ADDITIONAL_PROPERTIES_CHANGED
    )

    assert len(changes) == 1
    assert changes[0].before is True
    assert changes[0].after is False
    assert changes[0].breaking is True


# Spec AC4: equal additionalProperties emits nothing.
def test_equal_additional_properties_is_not_recorded():
    for fixture in ("tools-additional-v1.json", "tools-additional-v2.json"):
        document = load_mcp(FIXTURES / fixture)
        assert diff_mcp(document, load_mcp(FIXTURES / fixture)).changes == ()


# Spec AC4: output schemas compare additionalProperties at their own pointer.
def test_additional_properties_on_an_output_schema_is_recorded():
    old = a_document(
        a_tool("read_file", output_schema={"type": "object", "properties": {}})
    )
    new = a_document(
        a_tool(
            "read_file",
            output_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
    )

    changes = of_kind(
        diff_mcp(old, new), ChangeKind.ADDITIONAL_PROPERTIES_CHANGED
    )

    assert len(changes) == 1
    assert changes[0].location.pointer == "#/tools/read_file/outputSchema"
    assert changes[0].before is None
    assert changes[0].after is False
    assert changes[0].breaking is True


# Spec AC9: the new kind belongs to the MCP differ; OpenAPI never emits it.
def test_the_openapi_differ_never_emits_the_mcp_only_kind():
    def a_spec(additional=None):
        schema = {"type": "object", "properties": {"id": {"type": "string"}}}
        if additional is not None:
            schema["additionalProperties"] = additional
        return {
            "openapi": "3.0.3",
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {"application/json": {"schema": schema}},
                            }
                        }
                    }
                }
            },
        }

    result = diff(a_spec(), a_spec(False))

    assert ChangeKind.ADDITIONAL_PROPERTIES_CHANGED not in {
        change.kind for change in result.changes
    }
