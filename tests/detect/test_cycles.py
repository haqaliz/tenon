"""Cyclic refs are skipped where they close, and everything else is diffed."""

from pathlib import Path

from tenon.detect import ChangeKind, Unanalyzed, UnanalyzedReason, diff
from tenon.detect.diff import _SchemaContext
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"

NODE = "#/components/schemas/Node"
CHILD = f"{NODE}/properties/child"


def unanalyzed(result):
    return [(entry.pointer, entry.reason) for entry in result.unanalyzed]


def test_the_ordinary_change_survives_and_the_cycle_is_recorded_once():
    result = diff(
        load(FIXTURES / "cycle-old.yaml"),
        load(FIXTURES / "cycle-new.yaml"),
    )

    assert [
        (change.kind, change.location.pointer, change.before, change.after)
        for change in result.changes
    ] == [
        (
            ChangeKind.PROPERTY_TYPE_CHANGED,
            f"{NODE}/properties",
            {"name": "name", "type": "string", "format": None},
            {"name": "name", "type": "integer", "format": None},
        )
    ]
    assert unanalyzed(result) == [(CHILD, UnanalyzedReason.CYCLIC_REF)]


def test_no_change_is_invented_from_the_skipped_back_edge():
    result = diff(
        load(FIXTURES / "cycle-old.yaml"),
        load(FIXTURES / "cycle-new.yaml"),
    )

    assert ChangeKind.PROPERTY_REMOVED not in {change.kind for change in result.changes}
    assert CHILD not in {change.location.pointer for change in result.changes}


def test_two_independent_cycles_are_recorded_ordered_by_pointer():
    result = diff(
        load(FIXTURES / "cycle-two.yaml"),
        load(FIXTURES / "cycle-two.yaml"),
    )

    assert result.changes == ()
    assert unanalyzed(result) == [
        ("#/components/schemas/A/properties/next", UnanalyzedReason.CYCLIC_REF),
        ("#/components/schemas/B/properties/next", UnanalyzedReason.CYCLIC_REF),
    ]


def test_a_marker_on_one_side_only_skips_the_pair():
    old = {
        "openapi": "3.0.3",
        "paths": {},
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "child": {"$ref": "#/components/schemas/Node"}
                    },
                }
            }
        },
    }
    new = {
        "openapi": "3.0.3",
        "paths": {},
        "components": {
            "schemas": {
                "Node": {"type": "object", "properties": {"child": {"type": "string"}}}
            }
        },
    }

    result = diff(old, new)

    assert result.changes == ()
    assert unanalyzed(result) == [(CHILD, UnanalyzedReason.CYCLIC_REF)]


def test_record_dedupes_by_pointer_and_reason():
    context = _SchemaContext({}, {})

    context.record("#/components/schemas/A", UnanalyzedReason.CYCLIC_REF)
    context.record("#/components/schemas/A", UnanalyzedReason.CYCLIC_REF)
    context.record("#/components/schemas/A", UnanalyzedReason.UNSUPPORTED_COMPOSITION)

    assert context.unanalyzed == [
        Unanalyzed(pointer="#/components/schemas/A", reason=UnanalyzedReason.CYCLIC_REF),
        Unanalyzed(
            pointer="#/components/schemas/A",
            reason=UnanalyzedReason.UNSUPPORTED_COMPOSITION,
        ),
    ]


def test_a_cyclic_parameter_schema_is_skipped_without_a_crash():
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/x": {
                "get": {
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "schema": {"$ref": "#/paths/~1x/get/parameters/0/schema"},
                        }
                    ],
                    "responses": {},
                }
            }
        },
    }

    result = diff(document, document)

    assert result.changes == ()
    assert unanalyzed(result) == [
        ("#/paths/~1x/get/parameters/0/schema", UnanalyzedReason.CYCLIC_REF)
    ]
