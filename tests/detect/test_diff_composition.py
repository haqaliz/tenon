from pathlib import Path

import pytest

from tenon.detect import ChangeKind, UnanalyzedReason, diff
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def name_of(payload):
    return payload.get("name") if isinstance(payload, dict) else payload


def unanalyzed(result):
    return [(entry.pointer, entry.reason) for entry in result.unanalyzed]


BODY = "#/paths/~1pets/post/requestBody/content/application~1json/schema"


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


def test_the_composition_pair_reports_the_sibling_change_and_the_skip():
    result = diff(
        load(FIXTURES / "composition-skip-old.yaml"),
        load(FIXTURES / "composition-skip-new.yaml"),
    )

    assert [
        (change.kind, change.location.pointer, change.before, change.after)
        for change in result.changes
    ] == [
        (
            ChangeKind.PROPERTY_TYPE_CHANGED,
            "#/components/schemas/Payment/properties",
            {"name": "amount", "type": "integer", "format": None},
            {"name": "amount", "type": "string", "format": None},
        )
    ]
    assert unanalyzed(result) == [
        (
            "#/components/schemas/Payment/properties/method",
            UnanalyzedReason.UNSUPPORTED_COMPOSITION,
        )
    ]


def test_no_change_is_invented_from_the_skipped_one_of():
    result = diff(
        load(FIXTURES / "composition-skip-old.yaml"),
        load(FIXTURES / "composition-skip-new.yaml"),
    )

    assert ChangeKind.PROPERTY_REMOVED not in {change.kind for change in result.changes}
    assert "#/components/schemas/Payment/properties/method" not in {
        change.location.pointer for change in result.changes
    }


def test_one_of_in_a_parameter_schema_is_skipped_at_the_exact_pointer():
    result = diff(
        load(FIXTURES / "composition-oneof-old.yaml"),
        load(FIXTURES / "composition-oneof-new.yaml"),
    )

    assert result.changes == ()
    assert unanalyzed(result) == [
        ("#/paths/~1search/get/parameters/0/schema", UnanalyzedReason.UNSUPPORTED_COMPOSITION)
    ]


@pytest.mark.parametrize("keyword", ["oneOf", "anyOf"])
def test_union_keywords_are_skipped_at_the_schema_pointer(keyword):
    old = body_document({keyword: [{"type": "string"}, {"type": "integer"}]})
    new = body_document({"type": "string"})

    result = diff(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [(BODY, UnanalyzedReason.UNSUPPORTED_COMPOSITION)]


def test_discriminator_inside_all_of_is_skipped_at_the_member_pointer():
    document = load(FIXTURES / "composition-discriminator.yaml")

    result = diff(document, document)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (f"{BODY}/allOf/1", UnanalyzedReason.UNSUPPORTED_COMPOSITION)
    ]


def test_all_of_that_is_not_a_plain_merge_is_skipped():
    schema = {"allOf": [{"type": "object"}, {"type": "array", "items": {"type": "string"}}]}

    result = diff(body_document(schema), body_document({"type": "object"}))

    assert result.changes == ()
    assert unanalyzed(result) == [
        (f"{BODY}/allOf/1", UnanalyzedReason.UNSUPPORTED_COMPOSITION)
    ]


def test_conflicting_all_of_properties_are_skipped():
    schema = {
        "allOf": [
            {"type": "object", "properties": {"id": {"type": "string"}}},
            {"type": "object", "properties": {"id": {"type": "integer"}}},
        ]
    }

    result = diff(body_document(schema), body_document({"type": "object"}))

    assert result.changes == ()
    assert unanalyzed(result) == [
        (f"{BODY}/allOf/1", UnanalyzedReason.UNSUPPORTED_COMPOSITION)
    ]


def test_all_of_with_a_ref_member_skips_the_whole_merge():
    old = body_document(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
                {"$ref": "#/components/schemas/Node"},
            ]
        }
    )
    new = body_document(
        {"type": "object", "properties": {"id": {"type": "string"}}}
    )

    result = diff(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [
        (f"{BODY}/allOf/1", UnanalyzedReason.CYCLIC_REF)
    ]


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
