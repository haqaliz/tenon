from pathlib import Path

import pytest

from tenon.detect import ChangeKind, RefusalCode, SpecRefusal, diff
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def name_of(payload):
    return payload.get("name") if isinstance(payload, dict) else payload

BODY = "#/paths/~1pets/post/requestBody/content/application~1json/schema"


def one_of_parameter_document(schema):
    return {
        "openapi": "3.0.3",
        "paths": {
            "/search": {
                "get": {
                    "parameters": [{"name": "q", "in": "query", "schema": schema}],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


def body_document(schema):
    return {
        "openapi": "3.0.3",
        "paths": {
            "/pets": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": schema}}
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            }
        },
    }


def test_one_of_in_a_parameter_schema_refuses_at_the_exact_pointer():
    with pytest.raises(SpecRefusal) as caught:
        diff(
            load(FIXTURES / "composition-oneof-old.yaml"),
            load(FIXTURES / "composition-oneof-new.yaml"),
        )

    assert caught.value.code is RefusalCode.UNSUPPORTED_COMPOSITION
    assert caught.value.pointer == "#/paths/~1search/get/parameters/0/schema"


@pytest.mark.parametrize("keyword", ["oneOf", "anyOf"])
def test_union_keywords_refuse_at_the_schema_pointer(keyword):
    schema = {keyword: [{"type": "string"}, {"type": "integer"}]}

    with pytest.raises(SpecRefusal) as caught:
        diff(body_document(schema), body_document({"type": "string"}))

    assert caught.value.code is RefusalCode.UNSUPPORTED_COMPOSITION
    assert caught.value.pointer == BODY
    assert keyword in caught.value.message


def test_discriminator_inside_all_of_refuses_at_the_member_pointer():
    document = load(FIXTURES / "composition-discriminator.yaml")

    with pytest.raises(SpecRefusal) as caught:
        diff(document, document)

    assert caught.value.code is RefusalCode.UNSUPPORTED_COMPOSITION
    assert caught.value.pointer == f"{BODY}/allOf/1"


def test_all_of_that_is_not_a_plain_merge_refuses():
    schema = {"allOf": [{"type": "object"}, {"type": "array", "items": {"type": "string"}}]}

    with pytest.raises(SpecRefusal) as caught:
        diff(body_document(schema), body_document({"type": "object"}))

    assert caught.value.code is RefusalCode.UNSUPPORTED_COMPOSITION
    assert caught.value.pointer == f"{BODY}/allOf/1"


def test_conflicting_all_of_properties_refuse():
    schema = {
        "allOf": [
            {"type": "object", "properties": {"id": {"type": "string"}}},
            {"type": "object", "properties": {"id": {"type": "integer"}}},
        ]
    }

    with pytest.raises(SpecRefusal) as caught:
        diff(body_document(schema), body_document({"type": "object"}))

    assert caught.value.code is RefusalCode.UNSUPPORTED_COMPOSITION
    assert caught.value.pointer == f"{BODY}/allOf/1"


def test_a_plain_all_of_merge_is_traversed():
    result = diff(
        load(FIXTURES / "composition-allof-old.yaml"),
        load(FIXTURES / "composition-allof-new.yaml"),
    )

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.kind is ChangeKind.PROPERTY_REMOVED
    assert change.before["name"] == "age"
    assert change.location.pointer == f"{BODY}/properties"


def test_plain_all_of_merges_required_and_properties():
    old = body_document(
        {
            "allOf": [
                {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
                {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
            ]
        }
    )
    new = body_document(
        {
            "allOf": [
                {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
                {
                    "type": "object",
                    "required": ["name", "age"],
                    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                },
            ]
        }
    )

    changes = diff(old, new).changes

    assert [(change.kind, name_of(change.after)) for change in changes] == [
        (ChangeKind.PROPERTY_REQUIRED_ADDED, "age")
    ]


def test_nullability_only_difference_produces_zero_changes():
    result = diff(
        load(FIXTURES / "nullable-3.0.yaml"),
        load(FIXTURES / "nullable-3.1.yaml"),
    )

    assert result.changes == ()


def test_a_real_type_change_under_normalisation_is_reported_once():
    old = body_document(
        {"type": "object", "properties": {"id": {"type": "string", "nullable": True}}}
    )
    new = body_document(
        {"type": "object", "properties": {"id": {"type": ["integer", "null"]}}}
    )

    changes = diff(old, new).changes

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.PROPERTY_TYPE_CHANGED
    assert changes[0].before == {"name": "id", "type": "string", "format": None}
    assert changes[0].after == {"name": "id", "type": "integer", "format": None}
    assert changes[0].breaking is True


def test_union_type_order_does_not_matter():
    old = body_document(
        {"type": "object", "properties": {"id": {"type": ["string", "integer"]}}}
    )
    new = body_document(
        {"type": "object", "properties": {"id": {"type": ["integer", "string"]}}}
    )

    assert diff(old, new).changes == ()
