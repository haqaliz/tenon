import json
import os
import subprocess
import sys

import pytest

from tenon.detect import (
    Change,
    ChangeKind,
    DiffResult,
    Location,
    RefusalCode,
    SpecRefusal,
    Unanalyzed,
    UnanalyzedReason,
)

KINDS = [
    "endpoint_removed",
    "endpoint_added",
    "parameter_removed",
    "parameter_required_added",
    "parameter_type_changed",
    "property_removed",
    "property_added",
    "property_required_added",
    "property_type_changed",
    "enum_narrowed",
    "schema_removed",
    "schema_added",
    "renamed",
]


def test_change_kind_is_the_closed_thirteen():
    assert [kind.value for kind in ChangeKind] == KINDS


def test_location_accepts_an_rfc6901_fragment_pointer():
    location = Location(method="get", path="/users/{id}", pointer="#/paths/~1users~1{id}/get")
    assert location.pointer == "#/paths/~1users~1{id}/get"
    assert Location(pointer="#").pointer == "#"


@pytest.mark.parametrize("pointer", ["", "/paths/foo", "#paths/foo", "#/paths~2bad"])
def test_location_rejects_a_malformed_pointer(pointer):
    with pytest.raises(ValueError):
        Location(pointer=pointer)


def a_change(kind: ChangeKind = ChangeKind.PROPERTY_REMOVED) -> Change:
    return Change(
        kind=kind,
        location=Location(method="get", path="/users/{id}", pointer="#/paths/~1users~1{id}/get"),
        before={"type": "string", "format": "uuid"},
        after=None,
        breaking=True,
    )


@pytest.mark.parametrize("kind", list(ChangeKind))
def test_change_round_trips_through_dict(kind):
    change = a_change(kind)
    assert Change.from_dict(change.to_dict()) == change


def test_change_dict_uses_json_primitives_only():
    assert a_change(ChangeKind.PARAMETER_REMOVED).to_dict() == {
        "kind": "parameter_removed",
        "location": {
            "method": "get",
            "path": "/users/{id}",
            "pointer": "#/paths/~1users~1{id}/get",
        },
        "before": {"type": "string", "format": "uuid"},
        "after": None,
        "breaking": True,
        "confidence": "certain",
    }


def test_refusal_renders_code_pointer_and_message():
    refusal = SpecRefusal(
        code=RefusalCode.UNRESOLVED_REF,
        pointer="#/components/schemas/User",
        message="no such schema",
    )
    assert isinstance(refusal, Exception)
    text = str(refusal)
    assert "UNRESOLVED_REF" in text
    assert "#/components/schemas/User" in text
    assert "no such schema" in text


def test_refusal_without_a_pointer_still_renders():
    refusal = SpecRefusal(
        code=RefusalCode.UNPARSEABLE, message="line 3, column 5: bad yaml"
    )
    assert refusal.pointer is None
    assert "UNPARSEABLE" in str(refusal)
    assert "line 3, column 5" in str(refusal)


def test_refusal_rejects_a_bare_string_code():
    with pytest.raises(TypeError):
        SpecRefusal(code="NOT_A_SPEC", pointer="#", message="x")


def test_refusal_codes_are_the_closed_six():
    assert [code.value for code in RefusalCode] == [
        "NOT_A_SPEC",
        "UNSUPPORTED_VERSION",
        "UNPARSEABLE",
        "UNRESOLVED_REF",
        "EXTERNAL_REF",
        "UNSUPPORTED_COMPOSITION",
    ]


def test_change_owns_its_nested_values():
    before = {"type": "object", "properties": {"id": {"type": "integer"}}}
    change = Change(kind=ChangeKind.PROPERTY_REMOVED, location=Location(pointer="#"), before=before)
    before["properties"]["id"]["type"] = "string"
    assert change.before["properties"]["id"]["type"] == "integer"
    change.to_dict()["before"]["properties"]["id"]["type"] = "boolean"
    assert change.before["properties"]["id"]["type"] == "integer"


def a_change_at(pointer, kind=ChangeKind.PARAMETER_REMOVED, before=None, after=None):
    return Change(
        kind=kind, location=Location(pointer=pointer), before=before, after=after
    )


def test_diff_result_orders_by_pointer_then_kind_then_values():
    result = DiffResult(
        [
            a_change_at("#/paths/~1users/get/parameters", before="b"),
            a_change_at("#/paths/~1users/get", ChangeKind.ENDPOINT_ADDED),
            a_change_at("#/components/schemas/User", ChangeKind.RENAMED, "userId", "id"),
            a_change_at("#/components/schemas/User", ChangeKind.RENAMED, "a", "b"),
        ]
    )
    assert isinstance(result.changes, tuple)
    assert [(c.location.pointer, c.before) for c in result.changes] == [
        ("#/components/schemas/User", "a"),
        ("#/components/schemas/User", "userId"),
        ("#/paths/~1users/get", None),
        ("#/paths/~1users/get/parameters", "b"),
    ]


def some_changes():
    return [
        a_change_at("#/paths/~1users/get/parameters", before="b"),
        a_change_at("#/paths/~1users/get", ChangeKind.ENDPOINT_ADDED),
        a_change_at("#/components/schemas/User", ChangeKind.RENAMED, "userId", "id"),
        a_change_at("#/components/schemas/User", ChangeKind.RENAMED, "a", "b"),
    ]


def test_to_json_is_identical_for_any_insertion_order():
    changes = some_changes()
    expected = DiffResult(changes).to_json()
    assert DiffResult(list(reversed(changes))).to_json() == expected
    assert DiffResult(changes[2:] + changes[:2]).to_json() == expected


def test_to_json_holds_only_json_primitives():
    text = DiffResult(some_changes()).to_json()
    parsed = json.loads(text)
    assert parsed == DiffResult(some_changes()).to_dict()
    assert parsed["changes"][0]["kind"] == "renamed"
    for leak in ("ChangeKind.", "Location(", "Change(", "DiffResult("):
        assert leak not in text


def test_empty_result_serialises():
    assert DiffResult([]).to_json() == '{"changes":[],"unanalyzed":[]}'


def an_unanalyzed(
    pointer="#/components/schemas/Node", reason=UnanalyzedReason.CYCLIC_REF
):
    return Unanalyzed(pointer=pointer, reason=reason)


def test_diff_result_defaults_to_no_unanalyzed_subtrees():
    result = DiffResult(some_changes())
    assert result.unanalyzed == ()


def test_diff_result_carries_unanalyzed_subtrees_as_a_tuple():
    entry = an_unanalyzed()
    result = DiffResult([], [entry])
    assert isinstance(result.unanalyzed, tuple)
    assert result.unanalyzed == (entry,)


def test_unanalyzed_dedupes_by_pointer_and_reason():
    entry = an_unanalyzed()
    same_pointer_other_reason = an_unanalyzed(reason=UnanalyzedReason.UNRESOLVED_REF)
    result = DiffResult([], [entry, entry, same_pointer_other_reason])
    assert result.unanalyzed == (entry, same_pointer_other_reason)


def test_unanalyzed_orders_canonically_from_any_insertion_order():
    entries = [
        an_unanalyzed("#/components/schemas/Zed"),
        an_unanalyzed("#/components/schemas/Alpha", UnanalyzedReason.UNRESOLVED_REF),
        an_unanalyzed("#/components/schemas/Alpha"),
    ]
    expected = DiffResult([], entries).unanalyzed
    assert DiffResult([], list(reversed(entries))).unanalyzed == expected
    assert [(entry.pointer, entry.reason) for entry in expected] == [
        ("#/components/schemas/Alpha", UnanalyzedReason.CYCLIC_REF),
        ("#/components/schemas/Alpha", UnanalyzedReason.UNRESOLVED_REF),
        ("#/components/schemas/Zed", UnanalyzedReason.CYCLIC_REF),
    ]


def test_unanalyzed_does_not_perturb_change_ordering():
    changes = some_changes()
    with_skips = DiffResult(changes, [an_unanalyzed()])
    assert with_skips.changes == DiffResult(changes).changes


def test_unanalyzed_is_in_the_json():
    parsed = json.loads(DiffResult([], [an_unanalyzed()]).to_json())
    assert parsed == {
        "changes": [],
        "unanalyzed": [
            {"pointer": "#/components/schemas/Node", "reason": "CYCLIC_REF"}
        ],
    }


def test_to_json_ignores_dict_insertion_order_inside_values():
    first = DiffResult(
        [
            a_change_at(
                "#/components/schemas/User",
                ChangeKind.PROPERTY_REMOVED,
                {"type": "string", "format": "uuid"},
            )
        ]
    )
    second = DiffResult(
        [
            a_change_at(
                "#/components/schemas/User",
                ChangeKind.PROPERTY_REMOVED,
                {"format": "uuid", "type": "string"},
            )
        ]
    )
    assert first.to_json() == second.to_json()


SUBPROCESS_SCRIPT = """
from tenon.detect import (
    Change,
    ChangeKind,
    DiffResult,
    Location,
    Unanalyzed,
    UnanalyzedReason,
)

before = {key: key for key in {"type", "format", "title", "description", "default"}}
changes = [
    Change(
        kind=ChangeKind.PROPERTY_REMOVED,
        location=Location(pointer="#/components/schemas/User/properties/id"),
        before=before,
    ),
    Change(
        kind=ChangeKind.SCHEMA_ADDED,
        location=Location(pointer="#/components/schemas"),
        after=before,
    ),
]
unanalyzed = [
    Unanalyzed(pointer=pointer, reason=reason)
    for pointer, reason in {
        ("#/components/schemas/Zed", UnanalyzedReason.CYCLIC_REF),
        ("#/components/schemas/Alpha", UnanalyzedReason.UNSUPPORTED_COMPOSITION),
        ("#/components/schemas/Alpha", UnanalyzedReason.UNRESOLVED_REF),
    }
]
print(DiffResult(changes, unanalyzed).to_json(), end="")
"""


def to_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_to_json_is_byte_stable_across_hash_seeds():
    assert to_json_with_hash_seed("0") == to_json_with_hash_seed("1")
