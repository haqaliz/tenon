import pytest

from tenon.detect import Change, ChangeKind, Location, RefusalCode, SpecRefusal

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
