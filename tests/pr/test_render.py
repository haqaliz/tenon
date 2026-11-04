"""Render a deterministic PR draft: summary, title, commit, branch and body."""

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import Site, SiteShape
from tenon.pr import render_pr
from tenon.pr.render import (
    _branch,
    _commit_message,
    _slug,
    _summary,
    _title,
)
from tenon.propose import SkipReason, Skipped

CHARGE_POINTER = "#/components/schemas/Charge/properties"
PROOF_BASIC = Path(__file__).parent.parent / "fixtures" / "repos" / "proof-basic"


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
def test_title_is_the_level_and_the_tenon_prefix(a_passed_proof):
    assert _title(a_passed_proof, _summary(a_change())) == (
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



PASSED_BODY = """\
## Tenon proof: TESTS_PASSED

The command returned 0 before and after the patch in an isolated copy.

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `python -m pytest -q`
- Baseline exit: `0`
- After exit: `0`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

The check ran green before and after the patch, so the change did not break the command Tenon ran. It does not prove the change is correct.

Opened by Tenon. No merge was performed.
"""


# Spec AC4: the happy path body is one pinned deterministic text.
def test_passed_body_is_the_golden_text(a_rename_proposal, a_passed_proof):
    assert render_pr(a_rename_proposal, a_passed_proof).body == PASSED_BODY


# Spec AC1: render_pr wires the same summary into the title and the commit.
def test_render_pr_reuses_the_summary_in_the_title_and_commit(
    a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    summary = _summary(a_rename_proposal.change)

    assert draft.title == f"[TESTS_PASSED] tenon: {summary}"
    assert draft.commit_message == f"tenon: {summary}"


# Spec AC4: the sections keep the fixed order.
def test_passed_body_sections_are_in_the_fixed_order(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body
    headings = [
        "## Tenon proof: TESTS_PASSED",
        "### Change",
        "### Check",
        "### Files",
        "### Skipped sites",
        "### What this proves",
    ]

    assert [body.index(heading) for heading in headings] == sorted(
        body.index(heading) for heading in headings
    )


# Spec AC4: the command and both exit codes appear.
def test_passed_body_records_the_command_and_both_exits(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "- Command: `python -m pytest -q`" in body
    assert "- Baseline exit: `0`" in body
    assert "- After exit: `0`" in body


# Spec AC4: every touched file is listed.
def test_passed_body_lists_every_file(a_rename_proposal, a_passed_proof):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    for path in a_rename_proposal.files:
        assert f"- `{path}`" in body


# Spec AC4: every skipped site keeps its path, line, symbol and reason.
def test_passed_body_lists_every_skipped_site(a_rename_proposal, a_passed_proof):
    proposal = replace(
        a_rename_proposal,
        skipped=(
            Skipped(
                site=Site(
                    path="acme/billing.py",
                    line=7,
                    column=30,
                    shape=SiteShape.KEYWORD,
                    symbol="amount",
                ),
                reason=SkipReason.DYNAMIC_KWARGS,
            ),
            Skipped(
                site=Site(
                    path="acme/client.py",
                    line=2,
                    column=9,
                    shape=SiteShape.DICT_KEY,
                    symbol="amount",
                ),
                reason=SkipReason.STALE_SITE,
            ),
        ),
    )

    body = render_pr(proposal, a_passed_proof).body

    assert "- `acme/billing.py:7` `amount`: DYNAMIC_KWARGS" in body
    assert "- `acme/client.py:2` `amount`: STALE_SITE" in body


# Spec AC4: an empty skipped list says so explicitly.
def test_passed_body_says_none_for_no_skipped_sites(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "### Skipped sites\n\nNone." in body


# Spec AC4: the full unified diff is never copied into the body.
def test_passed_body_contains_no_diff(a_rename_proposal, a_passed_proof):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "--- a/" not in body
    assert a_rename_proposal.diff not in body


# Spec: one footer, last, and exactly one trailing newline.
def test_passed_body_ends_with_the_footer_and_one_newline(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert body.endswith("Opened by Tenon. No merge was performed.\n")
    assert body.count("Opened by Tenon. No merge was performed.") == 1
    assert not body.endswith("\n\n")
