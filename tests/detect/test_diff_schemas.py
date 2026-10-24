from pathlib import Path

import pytest

from tenon.detect import ChangeKind, RefusalCode, SpecRefusal, diff
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"

BODY = "#/paths/~1users/post/requestBody/content/application~1json/schema"
RESPONSE = (
    "#/paths/~1users~1{id}/get/responses/200/content/application~1json/schema"
)


def changes():
    return diff(
        load(FIXTURES / "schemas-old.yaml"),
        load(FIXTURES / "schemas-new.yaml"),
    ).changes


def of_kind(kind):
    return [change for change in changes() if change.kind is kind]


def type_basis(name, kind, fmt=None):
    return {"name": name, "type": kind, "format": fmt}


def enum_basis(name, values):
    return {"name": name, "enum": values}


def test_property_removed_is_breaking():
    removed = of_kind(ChangeKind.PROPERTY_REMOVED)

    assert len(removed) == 1
    assert removed[0].before == "nickname"
    assert removed[0].after is None
    assert removed[0].location.pointer == f"{BODY}/properties"
    assert removed[0].breaking is True


def test_new_optional_property_added_is_not_breaking():
    added = of_kind(ChangeKind.PROPERTY_ADDED)

    assert len(added) == 1
    assert added[0].before is None
    assert added[0].after == "email"
    assert added[0].location.pointer == f"{BODY}/properties"
    assert added[0].breaking is False


def test_existing_property_becoming_required_is_breaking():
    added = [
        change
        for change in of_kind(ChangeKind.PROPERTY_REQUIRED_ADDED)
        if change.before == "age"
    ]

    assert len(added) == 1
    assert added[0].after == "age"
    assert added[0].location.pointer == f"{BODY}/properties"
    assert added[0].breaking is True


def test_new_required_property_is_breaking():
    added = [
        change
        for change in of_kind(ChangeKind.PROPERTY_REQUIRED_ADDED)
        if change.after == "team"
    ]

    assert len(added) == 1
    assert added[0].before is None
    assert added[0].breaking is True


def test_nested_property_type_change():
    changed = [
        change
        for change in of_kind(ChangeKind.PROPERTY_TYPE_CHANGED)
        if change.location.pointer.endswith("/address/properties")
    ]

    assert len(changed) == 1
    assert changed[0].before == type_basis("zip", "string")
    assert changed[0].after == type_basis("zip", "integer")
    assert changed[0].location.pointer == f"{BODY}/properties/address/properties"
    assert changed[0].breaking is True


def test_array_items_are_recursed():
    changed = [
        change
        for change in of_kind(ChangeKind.PROPERTY_TYPE_CHANGED)
        if change.location.pointer == f"{BODY}/properties/tags"
    ]

    assert len(changed) == 1
    assert changed[0].before == {"type": "string", "format": None}
    assert changed[0].after == {"type": "integer", "format": None}
    assert changed[0].breaking is True


def test_response_schema_is_walked():
    changed = [
        change
        for change in of_kind(ChangeKind.PROPERTY_TYPE_CHANGED)
        if change.location.pointer.startswith(RESPONSE)
    ]

    assert len(changed) == 1
    assert changed[0].before == type_basis("id", "integer")
    assert changed[0].after == type_basis("id", "string")
    assert changed[0].location.method == "get"
    assert changed[0].location.path == "/users/{id}"
    assert changed[0].breaking is True


def test_enum_narrowed_is_breaking():
    narrowed = of_kind(ChangeKind.ENUM_NARROWED)

    assert len(narrowed) == 1
    assert narrowed[0].before == enum_basis("role", ["admin", "guest", "user"])
    assert narrowed[0].after == enum_basis("role", ["admin", "user"])
    assert narrowed[0].location.pointer == f"{BODY}/properties"
    assert narrowed[0].breaking is True


def test_widened_or_reordered_enum_is_not_a_change():
    reported = {change.before.get("name") for change in of_kind(ChangeKind.ENUM_NARROWED)}

    assert "scope" not in reported
    assert "kind" not in reported


def test_unchanged_properties_are_not_reported():
    reported = {
        change.before.get("name")
        for change in changes()
        if isinstance(change.before, dict)
    }

    assert "name" not in reported
    assert "street" not in reported
    assert "email" not in reported


def test_every_non_rename_kind_except_components_is_produced():
    kinds = {change.kind for change in changes()}

    assert kinds == {
        ChangeKind.PROPERTY_ADDED,
        ChangeKind.PROPERTY_REMOVED,
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        ChangeKind.PROPERTY_TYPE_CHANGED,
        ChangeKind.ENUM_NARROWED,
    }


def test_component_schema_added_and_removed():
    old = {
        "openapi": "3.0.3",
        "components": {"schemas": {"Keep": {"type": "object"}, "Gone": {"type": "string"}}},
    }
    new = {
        "openapi": "3.0.3",
        "components": {"schemas": {"Keep": {"type": "object"}, "Fresh": {"type": "string"}}},
    }

    result = diff(old, new).changes

    assert [(change.kind, change.before, change.after) for change in result] == [
        (ChangeKind.SCHEMA_ADDED, None, "Fresh"),
        (ChangeKind.SCHEMA_REMOVED, "Gone", None),
    ]
    assert [change.location.pointer for change in result] == ["#/components/schemas"] * 2
    assert [change.breaking for change in result] == [False, True]


def test_a_shared_component_reports_one_change_not_one_per_operation():
    result = diff(
        load(FIXTURES / "refs-old.yaml"),
        load(FIXTURES / "refs-new.yaml"),
    )

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.kind is ChangeKind.PROPERTY_TYPE_CHANGED
    assert change.location.pointer == "#/components/schemas/User/properties"
    assert change.location.method is None
    assert change.location.path is None
    assert change.before == type_basis("id", "string")
    assert change.after == type_basis("id", "integer")


def test_a_component_used_as_a_parameter_schema_reports_one_change():
    def document(kind):
        operation = {
            "parameters": [
                {"name": "q", "in": "query", "schema": {"type": kind}}
            ],
            "responses": {},
        }
        return {
            "openapi": "3.0.3",
            "paths": {"/a": {"get": operation}, "/b": {"get": operation}},
            "components": {"schemas": {"Q": {"type": kind}}},
        }

    result = diff(document("string"), document("integer"))

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.kind is ChangeKind.PROPERTY_TYPE_CHANGED
    assert change.location.pointer == "#/components/schemas/Q"


def test_reordering_keys_changes_nothing():
    old = load(FIXTURES / "schemas-old.yaml")
    new = load(FIXTURES / "schemas-new.yaml")

    def reversed_keys(value):
        if isinstance(value, dict):
            return {key: reversed_keys(value[key]) for key in reversed(list(value))}
        if isinstance(value, list):
            return [reversed_keys(item) for item in value]
        return value

    assert diff(reversed_keys(old), reversed_keys(new)).to_json() == diff(old, new).to_json()


def cyclic_document(schema):
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


def test_cyclic_schema_structure_is_refused_not_silently_stopped():
    schema = {"type": "object", "properties": {}}
    schema["properties"]["self"] = schema

    with pytest.raises(SpecRefusal) as caught:
        diff(cyclic_document(schema), cyclic_document(schema))

    assert caught.value.code is RefusalCode.UNRESOLVED_REF
    assert "cyclic" in caught.value.message


def test_a_lingering_ref_is_refused():
    document = cyclic_document({"$ref": "#/components/schemas/X"})

    with pytest.raises(SpecRefusal) as caught:
        diff(document, document)

    assert caught.value.code is RefusalCode.UNRESOLVED_REF
    assert caught.value.pointer.endswith("/schema/$ref")
