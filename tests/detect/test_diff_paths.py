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
    removed = [
        change
        for change in of_kind(ChangeKind.ENDPOINT_REMOVED)
        if change.location.path == "/legacy"
    ]

    assert len(removed) == 1
    change = removed[0]
    assert change.location.method == "get"
    assert change.location.pointer == "#/paths"
    assert change.before == "/legacy"
    assert change.after is None
    assert change.breaking is True


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
    added = [
        change
        for change in of_kind(ChangeKind.ENDPOINT_ADDED)
        if change.location.path == "/orders"
    ]

    assert len(added) == 1
    change = added[0]
    assert change.location.method == "get"
    assert change.location.pointer == "#/paths"
    assert change.before is None
    assert change.after == "/orders"
    assert change.breaking is False


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
        ("endpoint_added", "get", "/orders"),
        ("endpoint_removed", "get", "/legacy"),
        ("endpoint_removed", "post", "/odd~path"),
        ("endpoint_added", "put", "/users"),
        ("endpoint_removed", "post", "/users"),
    ]


def test_absent_paths_is_not_a_crash():
    assert diff({}, {"paths": {}}).changes == ()
    assert diff({"paths": {}}, {}).changes == ()
