from pathlib import Path

from tenon.detect import ChangeKind, diff
from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def changes():
    return diff(
        load(FIXTURES / "paths-old.yaml"),
        load(FIXTURES / "paths-new.yaml"),
    ).changes


def of_kind(kind):
    return [change for change in changes() if change.kind is kind]


def test_removed_path_reports_one_endpoint_removed_per_method():
    old = {
        "openapi": "3.0.3",
        "paths": {
            "/legacy": {
                "get": {"responses": {}},
                "post": {"responses": {}},
            }
        },
    }

    removed = [
        change
        for change in diff(old, {"openapi": "3.0.3", "paths": {}}).changes
        if change.kind is ChangeKind.ENDPOINT_REMOVED
    ]

    assert sorted(change.location.method for change in removed) == ["get", "post"]
    assert {change.location.pointer for change in removed} == {"#/paths"}
    assert all(change.before == "/legacy" for change in removed)
    assert all(change.after is None for change in removed)
    assert all(change.breaking is True for change in removed)


def test_removed_method_on_a_surviving_path_points_at_the_path_item():
    removed = [
        change
        for change in of_kind(ChangeKind.ENDPOINT_REMOVED)
        if change.location.path == "/users"
    ]

    assert len(removed) == 1
    assert removed[0].location.method == "post"
    assert removed[0].location.pointer == "#/paths/~1users"
    assert removed[0].breaking is True


def test_path_item_pointer_escapes_tilde_and_slash():
    removed = [
        change
        for change in of_kind(ChangeKind.ENDPOINT_REMOVED)
        if change.location.path == "/odd~path"
    ]

    assert len(removed) == 1
    assert removed[0].location.pointer == "#/paths/~1odd~0path"


def test_added_path_reports_one_endpoint_added_per_method():
    new = {
        "openapi": "3.0.3",
        "paths": {
            "/orders": {
                "get": {"responses": {}},
                "post": {"responses": {}},
            }
        },
    }

    added = [
        change
        for change in diff({"openapi": "3.0.3", "paths": {}}, new).changes
        if change.kind is ChangeKind.ENDPOINT_ADDED
    ]

    assert sorted(change.location.method for change in added) == ["get", "post"]
    assert {change.location.pointer for change in added} == {"#/paths"}
    assert all(change.before is None for change in added)
    assert all(change.after == "/orders" for change in added)
    assert all(change.breaking is False for change in added)


def test_added_method_on_a_surviving_path_points_at_the_path_item():
    added = [
        change
        for change in of_kind(ChangeKind.ENDPOINT_ADDED)
        if change.location.path == "/users"
    ]

    assert len(added) == 1
    assert added[0].location.method == "put"
    assert added[0].location.pointer == "#/paths/~1users"
    assert added[0].breaking is False


def test_unchanged_paths_produce_no_records():
    paths = [change.location.path for change in changes()]

    assert "/same" not in paths


def test_the_whole_diff_has_exactly_the_expected_records():
    assert [(change.kind.value, change.location.method, change.location.path) for change in changes()] == [
        ("renamed", "get", "/orders"),
        ("endpoint_removed", "post", "/odd~path"),
        ("endpoint_added", "put", "/users"),
        ("endpoint_removed", "post", "/users"),
    ]

    renamed = changes()[0]
    assert (renamed.before, renamed.after) == ("/legacy", "/orders")
    assert renamed.confidence == "inferred"


def test_absent_paths_is_not_a_crash():
    assert diff({}, {"paths": {}}).changes == ()
    assert diff({"paths": {}}, {}).changes == ()
