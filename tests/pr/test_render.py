"""Render a deterministic PR draft: summary, title, commit, branch and body."""

import hashlib
import json
import re

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.pr.render import (
    _branch,
    _commit_message,
    _slug,
    _summary,
    _title,
)
from tenon.prove import CheckResult, ProofLevel, ProofResult

CHARGE_POINTER = "#/components/schemas/Charge/properties"
COMMAND = ("python", "-m", "pytest", "-q")


def a_check(**overrides):
    values = {
        "kind": "baseline",
        "command": COMMAND,
        "returncode": 0,
        "timed_out": False,
    }
    values.update(overrides)
    return CheckResult(**values)


def a_passed_proof():
    return ProofResult(
        level=ProofLevel.TESTS_PASSED,
        baseline=a_check(kind="baseline"),
        after=a_check(kind="after"),
        patch_applied=True,
    )


def a_change(**overrides):
    values = {
        "kind": ChangeKind.RENAMED,
        "location": Location(
            pointer=CHARGE_POINTER,
            method="post",
            path="/v1/checkout/sessions",
        ),
        "before": "payment_method_types",
        "after": "allowed_payment_method_types",
    }
    values.update(overrides)
    return Change(**values)


# Spec AC1: the summary names the method and path when both are present.
def test_summary_uses_the_method_and_path():
    assert _summary(a_change()) == (
        "renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec AC1: the title is the level, the prefix, and that one summary.
def test_title_is_the_level_and_the_tenon_prefix():
    assert _title(a_passed_proof(), _summary(a_change())) == (
        "[TESTS_PASSED] tenon: renamed POST /v1/checkout/sessions: "
        "payment_method_types -> allowed_payment_method_types"
    )


# Spec AC1: the commit subject is the same summary, with no level.
def test_commit_message_is_the_summary_without_the_level():
    assert _commit_message(_summary(a_change())) == (
        "tenon: renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec: without a method and path the location is the pointer.
def test_summary_falls_back_to_the_pointer():
    change = a_change(location=Location(pointer=CHARGE_POINTER))

    assert _summary(change) == (
        f"renamed {CHARGE_POINTER}: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec: a before or after value is the only reason to add the arrow.
def test_summary_omits_the_arrow_when_both_values_are_none():
    assert _summary(a_change(before=None, after=None)) == (
        "renamed POST /v1/checkout/sessions"
    )


# Spec AC2: scalars render readably and containers render as compact canonical JSON.
@pytest.mark.parametrize(
    ("before", "after", "rendered"),
    [
        ("old", "new", "old -> new"),
        (3, 4, "3 -> 4"),
        (1.5, 2.0, "1.5 -> 2.0"),
        (False, True, "False -> True"),
        (None, "value", "None -> value"),
        (
            {"b": 2, "a": 1},
            [2, {"z": 1, "a": 0}],
            '{"a":1,"b":2} -> [2,{"a":0,"z":1}]',
        ),
    ],
)
def test_summary_renders_values_readably(before, after, rendered):
    assert _summary(a_change(before=before, after=after)) == (
        f"renamed POST /v1/checkout/sessions: {rendered}"
    )


BRANCH = re.compile(r"tenon/[a-z0-9-]+-[0-9a-f]{8}")


# Spec AC3: the branch shape is fixed.
def test_branch_matches_the_contract():
    assert BRANCH.fullmatch(_branch(a_change(), "diff")) is not None


# Spec AC3: the same change and diff always give the same branch.
def test_branch_is_stable_for_the_same_change_and_diff():
    change = a_change()

    assert _branch(change, "diff") == _branch(change, "diff")


# Spec AC3: one changed diff byte changes the suffix.
def test_branch_changes_when_one_diff_byte_changes():
    change = a_change()

    assert _branch(change, "diff") != _branch(change, "difF")


# Spec AC3: punctuation and unicode still produce a valid, readable slug.
def test_branch_sanitises_punctuation_and_unicode():
    branch = _branch(a_change(before="café/über", after="naïve — value"), "")

    assert BRANCH.fullmatch(branch) is not None
    assert "--" not in branch


# Spec AC3: an all-punctuation summary falls back to the word change.
def test_slug_falls_back_to_change_when_empty():
    assert _slug("!!! ???") == "change"


# Spec: lower-case, every run of non-alphanumerics collapsed to one dash, trimmed.
def test_slug_lowercases_and_collapses_runs():
    assert _slug("Renamed  POST /v1//Checkout: A -> B") == (
        "renamed-post-v1-checkout-a-b"
    )


# Spec AC3: the readable part stops at 48 characters.
def test_slug_truncates_to_48_characters():
    assert _slug("a" * 200) == "a" * 48


# Spec AC3: the suffix is sha256(change_json + NUL + diff), first eight hex.
def test_branch_suffix_hashes_the_canonical_change_and_diff():
    change = a_change()
    payload = (
        json.dumps(
            change.to_dict(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\0"
        + b"diff"
    )
    expected = hashlib.sha256(payload).hexdigest()[:8]

    assert _branch(change, "diff") == f"tenon/{_slug(_summary(change))}-{expected}"

