"""The operator event-to-bundle trigger mapping."""

from pathlib import Path

import pytest

from tenon.service.triggers import Trigger, parse_trigger, parse_triggers


def a_bundles(tmp_path):
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    for name in ("demo.json", "other.json", "demo.txt"):
        (bundles / name).write_text("{}", encoding="utf-8")
    return bundles


# Spec AC1: event.action=bundle and event=bundle parse to the right Trigger.
def test_parse_event_action_bundle(tmp_path):
    bundles = a_bundles(tmp_path)

    assert parse_trigger(
        "installation_repositories.added=demo.json", bundles
    ) == Trigger("installation_repositories", "added", "demo.json")


def test_parse_event_only(tmp_path):
    bundles = a_bundles(tmp_path)

    assert parse_trigger("push=demo.json", bundles) == Trigger(
        "push", None, "demo.json"
    )


# Spec AC2: malformed keys, whitespace and unconfined bundles are named errors.
@pytest.mark.parametrize(
    "value",
    [
        "",
        "demo.json",
        "push=",
        "=demo.json",
        ".added=demo.json",
        "push.=demo.json",
        "push demo=demo.json",
        "push=demo.json extra",
        "push=../demo.json",
        "push=sub/../../demo.json",
        "push=/tmp/demo.json",
        "push=missing.json",
        "push=demo.txt",
    ],
)
def test_a_bad_trigger_is_a_named_error(tmp_path, value):
    bundles = a_bundles(tmp_path)

    with pytest.raises(ValueError, match="trigger|bundle"):
        parse_trigger(value, bundles)


# Spec AC3: an actionless and an action-specific trigger for the same event coexist.
def test_actionless_and_action_specific_coexist(tmp_path):
    bundles = a_bundles(tmp_path)

    triggers = parse_triggers(
        ["push=demo.json", "push.created=other.json"], bundles
    )

    assert triggers == {
        ("push", None): "demo.json",
        ("push", "created"): "other.json",
    }


def test_a_duplicate_exact_trigger_is_a_named_error(tmp_path):
    bundles = a_bundles(tmp_path)

    with pytest.raises(ValueError, match="duplicate"):
        parse_triggers(["push=demo.json", "push=other.json"], bundles)
