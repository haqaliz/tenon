import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tenon.detect import ChangeKind, Location, UnanalyzedReason, diff
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


def unanalyzed(result):
    return [(entry.pointer, entry.reason) for entry in result.unanalyzed]


def a_payload(name, type_, fmt=None):
    return {"name": name, "type": type_, "format": fmt}


INPUT = "#/tools/read_file/inputSchema/properties"
OUTPUT = "#/tools/read_file/outputSchema/properties"
ADDITIONAL = "#/tools/read_file/inputSchema"
NESTED_OPTIONS = "#/tools/read_file/inputSchema/properties/options/properties"
NESTED_ITEMS = "#/tools/read_file/inputSchema/properties/tags/items/properties"
CREATE_CHARGE = "#/tools/create_charge/inputSchema/properties"


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


# Spec AC5: a removed property of a nested object uses the exact pointer.
def test_a_nested_object_property_removal_uses_the_exact_pointer():
    old = load_mcp(FIXTURES / "tools-nested-v1.json")
    new = load_mcp(FIXTURES / "tools-nested-v2.json")

    removed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_REMOVED)

    assert len(removed) == 1
    change = removed[0]
    assert change.location == Location(
        pointer=NESTED_OPTIONS, method="tool", path="read_file"
    )
    assert change.before == a_payload("verbose", "boolean")
    assert change.breaking is True


# Spec AC5: a type change inside a nested object uses the exact pointer.
def test_a_nested_property_type_change_uses_the_exact_pointer():
    old = load_mcp(FIXTURES / "tools-nested-v1.json")
    new = load_mcp(FIXTURES / "tools-nested-v2.json")

    changed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_TYPE_CHANGED)

    retries = [
        change for change in changed if change.before == a_payload("retries", "integer")
    ]
    assert len(retries) == 1
    change = retries[0]
    assert change.location == Location(
        pointer=NESTED_OPTIONS, method="tool", path="read_file"
    )
    assert change.after == a_payload("retries", "string")
    assert change.breaking is True


# Spec AC5: a property inside array items uses the exact pointer.
def test_an_array_items_property_type_change_uses_the_exact_pointer():
    old = load_mcp(FIXTURES / "tools-nested-v1.json")
    new = load_mcp(FIXTURES / "tools-nested-v2.json")

    changed = of_kind(diff_mcp(old, new), ChangeKind.PROPERTY_TYPE_CHANGED)

    label = [
        change for change in changed if change.before == a_payload("label", "string")
    ]
    assert len(label) == 1
    change = label[0]
    assert change.location == Location(
        pointer=NESTED_ITEMS, method="tool", path="read_file"
    )
    assert change.after == a_payload("label", "integer")
    assert change.breaking is True


# Spec AC4/AC5: nested additionalProperties is recorded at that nested schema.
def test_nested_additional_properties_is_recorded_at_the_nested_schema():
    old = load_mcp(FIXTURES / "tools-nested-v1.json")
    new = load_mcp(FIXTURES / "tools-nested-v2.json")

    changes = of_kind(
        diff_mcp(old, new), ChangeKind.ADDITIONAL_PROPERTIES_CHANGED
    )

    assert len(changes) == 1
    change = changes[0]
    assert change.location.pointer == (
        "#/tools/read_file/inputSchema/properties/options"
    )
    assert change.before is True
    assert change.after is False
    assert change.breaking is True


# Spec AC6: a unique same-shape property pair becomes an inferred rename.
def test_a_unique_property_rename_is_inferred():
    old = load_mcp(FIXTURES / "tools-rename-v1.json")
    new = load_mcp(FIXTURES / "tools-rename-v2.json")

    changes = diff_mcp(old, new).changes

    assert len(changes) == 1
    change = changes[0]
    assert change.kind is ChangeKind.RENAMED
    assert change.location == Location(
        pointer=CREATE_CHARGE, method="tool", path="create_charge"
    )
    assert change.before == "nickname"
    assert change.after == "handle"
    assert change.breaking is True
    assert change.confidence == "inferred"


# Spec AC6: an ambiguous pair stays a removal plus an addition.
def test_an_ambiguous_property_pair_stays_removed_and_added():
    old = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {
                    "nickname": {"type": "string"},
                    "alias": {"type": "string"},
                },
            },
        )
    )
    new = a_document(
        a_tool(
            "read_file",
            input_schema={
                "type": "object",
                "properties": {"handle": {"type": "string"}},
            },
        )
    )

    changes = diff_mcp(old, new).changes

    assert [change.kind for change in changes] == [
        ChangeKind.PROPERTY_ADDED,
        ChangeKind.PROPERTY_REMOVED,
        ChangeKind.PROPERTY_REMOVED,
    ]
    assert all(change.confidence == "certain" for change in changes)


# Spec AC6: a removed and an added tool are never inferred as a rename.
def test_a_removed_and_added_tool_is_never_a_rename():
    old = a_document(
        a_tool("alpha", input_schema={"type": "object", "properties": {}})
    )
    new = a_document(
        a_tool("beta", input_schema={"type": "object", "properties": {}})
    )

    changes = diff_mcp(old, new).changes

    assert [change.kind for change in changes] == [
        ChangeKind.ENDPOINT_REMOVED,
        ChangeKind.ENDPOINT_ADDED,
    ]
    assert ChangeKind.RENAMED not in {change.kind for change in changes}
    assert all(change.confidence == "certain" for change in changes)


# Spec AC7: a plain allOf merge is walked like one object schema.
def test_a_plain_all_of_merge_is_walked():
    old = load_mcp(FIXTURES / "tools-composition-v1.json")
    new = load_mcp(FIXTURES / "tools-composition-v2.json")

    result = diff_mcp(old, new)

    assert [
        (change.kind, change.location.pointer, change.before, change.after)
        for change in result.changes
    ] == [
        (
            ChangeKind.PROPERTY_TYPE_CHANGED,
            "#/tools/pay/inputSchema/properties",
            a_payload("id", "string"),
            a_payload("id", "integer"),
        )
    ]
    assert result.unanalyzed == ()


# Spec AC7: union keywords are skipped and recorded at the schema pointer.
@pytest.mark.parametrize("keyword", ["oneOf", "anyOf"])
def test_a_union_keyword_is_recorded_as_unanalyzed(keyword):
    old = a_document(
        a_tool(
            "choose",
            input_schema={keyword: [{"type": "string"}, {"type": "integer"}]},
        )
    )
    new = a_document(a_tool("choose", input_schema={"type": "string"}))

    result = diff_mcp(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (
            "#/tools/choose/inputSchema",
            UnanalyzedReason.UNSUPPORTED_COMPOSITION,
        )
    ]


# Spec AC7: a discriminator is skipped and recorded at the schema pointer.
def test_a_discriminator_is_recorded_as_unanalyzed():
    schema = {
        "type": "object",
        "discriminator": {"propertyName": "kind"},
        "properties": {"kind": {"type": "string"}},
    }

    result = diff_mcp(
        a_document(a_tool("pay", input_schema=schema)),
        a_document(a_tool("pay", input_schema=schema)),
    )

    assert result.changes == ()
    assert unanalyzed(result) == [
        ("#/tools/pay/inputSchema", UnanalyzedReason.UNSUPPORTED_COMPOSITION)
    ]


# Spec AC7: a non-merge allOf member is skipped at its own pointer.
def test_a_non_merge_all_of_is_recorded_as_unanalyzed():
    old = a_document(
        a_tool(
            "pay",
            input_schema={
                "allOf": [
                    {"type": "object"},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
        )
    )
    new = a_document(a_tool("pay", input_schema={"type": "object"}))

    result = diff_mcp(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (
            "#/tools/pay/inputSchema/allOf/1",
            UnanalyzedReason.UNSUPPORTED_COMPOSITION,
        )
    ]


# Spec AC7: composition in an output schema is recorded too.
def test_composition_in_an_output_schema_is_recorded():
    old = a_document(
        a_tool(
            "choose",
            output_schema={"anyOf": [{"type": "string"}, {"type": "integer"}]},
        )
    )
    new = a_document(a_tool("choose", output_schema={"type": "string"}))

    result = diff_mcp(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (
            "#/tools/choose/outputSchema",
            UnanalyzedReason.UNSUPPORTED_COMPOSITION,
        )
    ]


# Spec AC7: a cyclic $ref marker is recorded, never followed or skipped silently.
def test_a_cyclic_ref_marker_is_recorded():
    old = load_mcp(FIXTURES / "tools-ref-cycle.json")
    new = load_mcp(FIXTURES / "tools-ref-cycle.json")

    result = diff_mcp(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (
            "#/tools/walk/inputSchema/properties/node/properties/next",
            UnanalyzedReason.CYCLIC_REF,
        )
    ]


# Spec AC8: property insertion order does not change the result.
def test_schema_property_order_is_irrelevant():
    def a_schema(*names):
        return {
            "type": "object",
            "properties": {name: {"type": "string"} for name in names},
        }

    old_a = a_document(a_tool("x", input_schema=a_schema("keep", "gone")))
    old_b = a_document(a_tool("x", input_schema=a_schema("gone", "keep")))
    new = a_document(
        a_tool("x", input_schema={"type": "object", "properties": {"keep": {}}})
    )

    assert diff_mcp(old_a, new).to_json() == diff_mcp(old_b, new).to_json()


# Spec AC8: the diff JSON is byte-identical across hash seeds.
SUBPROCESS_SCRIPT = f"""
from pathlib import Path

from tenon.detect.mcp_diff import diff_mcp
from tenon.detect.mcp_ingest import load_mcp

fixtures = Path({str(FIXTURES)!r})
print(
    diff_mcp(
        load_mcp(fixtures / "tools-nested-v1.json"),
        load_mcp(fixtures / "tools-nested-v2.json"),
    ).to_json(),
    end="",
)
"""


def a_diff_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_diff_json_is_byte_stable_across_hash_seeds():
    assert a_diff_json_with_hash_seed("0") == a_diff_json_with_hash_seed("1")


# Spec AC8/M8: the package exports the MCP differ; diff stays as shipped.
def test_tenon_detect_exports_diff_mcp():
    import tenon.detect
    from tenon.detect.mcp_diff import diff_mcp as module_diff_mcp

    assert tenon.detect.diff_mcp is module_diff_mcp
    assert callable(tenon.detect.diff)
