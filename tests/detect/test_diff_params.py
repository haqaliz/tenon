from pathlib import Path

from tenon.detect import ChangeKind, diff
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def name_of(payload):
    return payload.get("name") if isinstance(payload, dict) else payload


def changes():
    return diff(
        load(FIXTURES / "params-old.yaml"),
        load(FIXTURES / "params-new.yaml"),
    ).changes


def of_kind(kind):
    return [change for change in changes() if change.kind is kind]


def type_basis(name, where, kind, fmt=None):
    return {"name": name, "in": where, "type": kind, "format": fmt}


def test_removed_parameter_is_breaking_and_points_at_the_operation_list():
    removed = of_kind(ChangeKind.PARAMETER_REMOVED)
    limit = [change for change in removed if name_of(change.before) == "limit"]

    assert len(limit) == 1
    assert limit[0].location.method == "get"
    assert limit[0].location.path == "/items"
    assert limit[0].location.pointer == "#/paths/~1items/get/parameters"
    assert limit[0].after is None
    assert limit[0].breaking is True


def test_inherited_path_level_parameter_is_reported_once_per_operation():
    removed = [
        change for change in of_kind(ChangeKind.PARAMETER_REMOVED) if name_of(change.before) == "tenant"
    ]

    assert sorted(change.location.method for change in removed) == ["get", "post"]
    assert {change.location.pointer for change in removed} == {"#/paths/~1items/parameters"}
    assert all(change.breaking is True for change in removed)


def test_optional_parameter_becoming_required():
    added = [
        change
        for change in of_kind(ChangeKind.PARAMETER_REQUIRED_ADDED)
        if name_of(change.after) == "mode"
    ]

    assert len(added) == 1
    assert name_of(added[0].before) == "mode"
    assert added[0].location.method == "get"
    assert added[0].location.pointer == "#/paths/~1items/get/parameters"
    assert added[0].breaking is True


def test_new_required_parameter():
    added = [
        change
        for change in of_kind(ChangeKind.PARAMETER_REQUIRED_ADDED)
        if name_of(change.after) == "sort"
    ]

    assert len(added) == 1
    assert added[0].before is None
    assert added[0].breaking is True


def test_new_optional_parameter_is_not_reported():
    assert not [
        change
        for change in changes()
        if name_of(change.before) == "debug" or name_of(change.after) == "debug"
    ]


def test_parameter_type_change():
    changed = of_kind(ChangeKind.PARAMETER_TYPE_CHANGED)

    assert len(changed) == 1
    assert changed[0].before == type_basis("page", "query", "integer")
    assert changed[0].after == type_basis("page", "query", "string")
    assert changed[0].location.pointer == "#/paths/~1items/get/parameters"
    assert changed[0].breaking is True


def test_unchanged_parameters_are_not_reported():
    names = {
        change.before for change in changes() if isinstance(change.before, str)
    } | {change.after for change in changes() if isinstance(change.after, str)}

    assert "api-version" not in names
    assert "accept" not in names
    assert "payload" not in names


def test_the_whole_diff_has_exactly_the_expected_records():
    assert [
        (change.kind.value, change.location.method, change.before, change.after)
        for change in changes()
    ] == [
        ("parameter_removed", "get", type_basis("limit", "query", "integer"), None),
        (
            "parameter_required_added",
            "get",
            None,
            type_basis("sort", "query", "string"),
        ),
        (
            "parameter_required_added",
            "get",
            type_basis("mode", "query", "string"),
            type_basis("mode", "query", "string"),
        ),
        ("parameter_type_changed", "get", type_basis("page", "query", "integer"), type_basis("page", "query", "string")),
        ("parameter_removed", "get", type_basis("tenant", "header", "string"), None),
        ("parameter_removed", "post", type_basis("tenant", "header", "string"), None),
    ]


def spec(path_item):
    return {
        "openapi": "3.0.3",
        "paths": {"/x": path_item},
    }


def test_operation_level_declaration_wins_over_path_level():
    old = spec(
        {
            "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}],
            "get": {"parameters": [], "responses": {}},
        }
    )
    new = spec(
        {
            "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}],
            "get": {
                "parameters": [{"name": "q", "in": "query", "schema": {"type": "integer"}}],
                "responses": {},
            },
        }
    )

    changed = diff(old, new).changes

    assert len(changed) == 1
    assert changed[0].kind is ChangeKind.PARAMETER_TYPE_CHANGED
    assert changed[0].location.pointer == "#/paths/~1x/get/parameters"


def test_operation_level_override_hides_a_path_level_change():
    path_parameter = {"name": "q", "in": "query", "schema": {"type": "string"}}
    operation_parameter = {"name": "q", "in": "query", "schema": {"type": "string"}}
    changed_path_parameter = {"name": "q", "in": "query", "schema": {"type": "integer"}}

    old = spec(
        {
            "parameters": [path_parameter],
            "get": {"parameters": [operation_parameter], "responses": {}},
        }
    )
    new = spec(
        {
            "parameters": [changed_path_parameter],
            "get": {"parameters": [operation_parameter], "responses": {}},
        }
    )

    assert diff(old, new).changes == ()


def test_parameter_format_change_is_a_type_change():
    old = spec(
        {
            "get": {
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {},
            }
        }
    )
    new = spec(
        {
            "get": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {},
            }
        }
    )

    changed = diff(old, new).changes

    assert len(changed) == 1
    assert changed[0].kind is ChangeKind.PARAMETER_TYPE_CHANGED
    assert changed[0].after["format"] == "uuid"
