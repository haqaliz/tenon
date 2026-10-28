import json
import os
import subprocess
import sys

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import AmbiguityReason, Site, SiteShape
from tenon.propose import Edit, Proposal, ProposalReason, SkipReason, Skipped


def a_site(**overrides):
    values = {
        "path": "billing.py",
        "line": 42,
        "column": 25,
        "shape": "keyword",
        "symbol": "amount",
    }
    values.update(overrides)
    return Site(**values)


def an_edit(**overrides):
    values = {
        "path": "billing.py",
        "line": 42,
        "column": 25,
        "shape": "keyword",
        "old": "amount",
        "new": "amount_cents",
    }
    values.update(overrides)
    return Edit(**values)


def a_change():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer="#/components/schemas/Charge"),
        before="amount",
        after="amount_cents",
        confidence="inferred",
    )


def a_skipped(reason=SkipReason.DYNAMIC_KWARGS, **overrides):
    return Skipped(site=a_site(**overrides), reason=reason)


def a_proposal(edits=(), skipped=(), diff="", reason=None):
    return Proposal(
        change=a_change(),
        edits=list(edits),
        skipped=list(skipped),
        diff=diff,
        reason=reason,
    )


def some_edits():
    return [
        an_edit(path="z.py", line=3, column=1, old="delete", new="remove"),
        an_edit(path="a.py", line=9, column=10, old="amount", new="amount_cents"),
        an_edit(path="a.py", line=9, column=3, old="amount", new="amount_cents"),
    ]


def some_skipped():
    return [
        a_skipped(reason=SkipReason.STALE_SITE, path="z.py", line=3, column=1),
        a_skipped(reason=SkipReason.UNMAPPED_SYMBOL, path="a.py", line=9, column=10),
        a_skipped(reason=SkipReason.DYNAMIC_KWARGS, path="a.py", line=9, column=3),
    ]


# Spec AC1: an Edit constructs for every SiteShape.
@pytest.mark.parametrize("shape", list(SiteShape))
def test_edit_accepts_every_shape(shape):
    edit = an_edit(shape=shape)
    assert edit.shape is SiteShape(shape)
    assert (edit.path, edit.line, edit.column, edit.old, edit.new) == (
        "billing.py",
        42,
        25,
        "amount",
        "amount_cents",
    )


# Spec AC1: a Skipped entry constructs for every SkipReason.
@pytest.mark.parametrize("reason", list(SkipReason))
def test_skipped_accepts_every_reason(reason):
    site = a_site()
    skipped = Skipped(site=site, reason=reason)
    assert skipped.site is site
    assert skipped.reason is reason


# Spec: ProposalReason is the closed three-value vocabulary.
def test_proposal_reason_values_are_the_closed_three():
    assert [reason.value for reason in ProposalReason] == [
        "NO_RULE",
        "NO_CERTAIN_SITES",
        "STALE_SITE",
    ]


# Spec AC7: every AmbiguityReason value is constructible as a SkipReason.
@pytest.mark.parametrize("reason", list(AmbiguityReason))
def test_every_ambiguity_reason_is_a_skip_reason(reason):
    assert SkipReason(reason) is SkipReason(reason.value)


def test_skip_reason_mirrors_ambiguity_reasons_and_adds_two():
    ambiguity = {reason.value for reason in AmbiguityReason}
    skipped = {reason.value for reason in SkipReason}
    assert ambiguity <= skipped
    assert skipped - ambiguity == {"SHAPE_NOT_EDITABLE", "STALE_SITE"}


# Spec AC2: files is the sorted unique set of edit paths.
def test_proposal_files_are_derived_from_edits():
    proposal = Proposal(
        change=a_change(),
        edits=(
            an_edit(path="b.py"),
            an_edit(path="a.py", line=1, column=1),
            an_edit(path="b.py", line=7),
        ),
        skipped=(),
        diff="x",
    )
    assert proposal.files == ("a.py", "b.py")


# Spec AC2: files cannot be passed in at all.
def test_proposal_rejects_a_files_argument():
    with pytest.raises(TypeError):
        Proposal(change=a_change(), edits=(), skipped=(), files=("a.py",), diff="")


# Spec AC6: an edit-bearing proposal without a diff is an error.
def test_proposal_rejects_edits_without_a_diff():
    with pytest.raises(ValueError):
        a_proposal(edits=(an_edit(),), diff="")


# Spec AC5: a reason means "no edits", so edits with a reason are an error.
def test_proposal_rejects_edits_with_a_reason():
    with pytest.raises(ValueError):
        a_proposal(edits=(an_edit(),), diff="x", reason=ProposalReason.STALE_SITE)


# Spec AC5: an empty proposal must name why it is empty.
def test_proposal_rejects_no_edits_without_a_reason():
    with pytest.raises(ValueError):
        a_proposal(edits=(), skipped=(a_skipped(),), diff="")


# Spec AC6: an empty proposal must not carry a diff.
def test_proposal_rejects_no_edits_with_a_diff():
    with pytest.raises(ValueError):
        a_proposal(edits=(), diff="x", reason=ProposalReason.NO_RULE)


# Spec AC5: an empty proposal with skipped sites is valid.
def test_empty_proposal_with_skipped_is_valid():
    proposal = a_proposal(
        edits=(),
        skipped=(a_skipped(),),
        diff="",
        reason=ProposalReason.NO_CERTAIN_SITES,
    )
    assert proposal.edits == ()
    assert proposal.files == ()
    assert len(proposal.skipped) == 1


@pytest.mark.parametrize("reason", list(ProposalReason))
def test_empty_proposal_accepts_every_reason(reason):
    assert a_proposal(reason=reason).reason is reason


def test_proposal_coerces_a_reason_string():
    assert a_proposal(reason="NO_RULE").reason is ProposalReason.NO_RULE


# Spec AC3: edits are ordered by path, line, column, shape, old.
def test_edits_are_canonically_ordered():
    proposal = a_proposal(edits=some_edits(), diff="x")
    assert isinstance(proposal.edits, tuple)
    assert [(edit.path, edit.line, edit.column) for edit in proposal.edits] == [
        ("a.py", 9, 3),
        ("a.py", 9, 10),
        ("z.py", 3, 1),
    ]


def test_edits_with_identical_coordinates_order_by_shape_then_old():
    pairs = [
        ("keyword", "zeta"),
        ("attribute", "amount"),
        ("keyword", "amount"),
        ("attribute", "zeta"),
    ]
    proposal = a_proposal(
        edits=[
            an_edit(path="a.py", line=1, column=1, shape=shape, old=old)
            for shape, old in pairs
        ],
        diff="x",
    )
    assert [(edit.shape.value, edit.old) for edit in proposal.edits] == [
        ("attribute", "amount"),
        ("attribute", "zeta"),
        ("keyword", "amount"),
        ("keyword", "zeta"),
    ]


# Spec AC3: skipped sites are ordered by path, line, column, reason.
def test_skipped_are_canonically_ordered():
    proposal = a_proposal(
        skipped=some_skipped(), reason=ProposalReason.NO_CERTAIN_SITES
    )
    assert isinstance(proposal.skipped, tuple)
    assert [
        (entry.site.path, entry.site.line, entry.site.column, entry.reason.value)
        for entry in proposal.skipped
    ] == [
        ("a.py", 9, 3, "DYNAMIC_KWARGS"),
        ("a.py", 9, 10, "UNMAPPED_SYMBOL"),
        ("z.py", 3, 1, "STALE_SITE"),
    ]


# Spec AC3: repeated sites stay; only the reason breaks the tie.
def test_skipped_keeps_repeated_sites_and_orders_by_reason():
    site = a_site()
    proposal = a_proposal(
        skipped=[
            Skipped(site=site, reason=SkipReason.STALE_SITE),
            Skipped(site=site, reason=SkipReason.DYNAMIC_KWARGS),
        ],
        reason=ProposalReason.NO_CERTAIN_SITES,
    )
    assert [entry.reason for entry in proposal.skipped] == [
        SkipReason.DYNAMIC_KWARGS,
        SkipReason.STALE_SITE,
    ]


# Spec AC3/AC4: insertion order must not leak into the serialised bytes.
def test_to_json_is_identical_for_any_insertion_order():
    expected = a_proposal(
        edits=some_edits(), skipped=some_skipped(), diff="x"
    ).to_json()
    reversed_proposal = a_proposal(
        edits=reversed(some_edits()),
        skipped=reversed(some_skipped()),
        diff="x",
    )
    assert reversed_proposal.to_json() == expected
    rotated_edits = some_edits()[1:] + some_edits()[:1]
    rotated_skipped = some_skipped()[1:] + some_skipped()[:1]
    rotated = a_proposal(edits=rotated_edits, skipped=rotated_skipped, diff="x")
    assert rotated.to_json() == expected


# Spec AC4: no tuple, set, enum object or dataclass repr reaches the payload.
def test_to_json_holds_only_json_primitives():
    proposal = a_proposal(
        edits=some_edits(),
        skipped=some_skipped(),
        diff="--- a/a.py\n+++ b/a.py\n",
    )
    text = proposal.to_json()
    assert json.loads(text) == proposal.to_dict()
    assert json.loads(text)["reason"] is None
    for leak in (
        "SiteShape.",
        "SkipReason.",
        "ProposalReason.",
        "Edit(",
        "Skipped(",
        "Proposal(",
        "Change(",
        "Location(",
        "Site(",
    ):
        assert leak not in text


# Spec AC4: an edit-bearing proposal round-trips with files and a null reason.
def test_edit_bearing_proposal_round_trips_through_json():
    proposal = a_proposal(edits=some_edits(), skipped=some_skipped(), diff="x")
    parsed = json.loads(proposal.to_json())
    assert parsed == proposal.to_dict()
    assert parsed["files"] == ["a.py", "z.py"]
    assert parsed["reason"] is None
    assert parsed["edits"][0]["shape"] in {shape.value for shape in SiteShape}


# Spec AC4: every named reason is a plain string in the payload.
@pytest.mark.parametrize("reason", list(ProposalReason))
def test_empty_proposal_round_trips_every_reason(reason):
    proposal = a_proposal(reason=reason)
    parsed = json.loads(proposal.to_json())
    assert parsed == proposal.to_dict()
    assert parsed["reason"] == reason.value
    assert parsed["files"] == []
    assert parsed["diff"] == ""


SUBPROCESS_SCRIPT = """
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import Site
from tenon.propose import Edit, Proposal, SkipReason, Skipped

edits = [
    Edit(path=path, line=line, column=column, shape=shape, old=old, new=old + "_new")
    for path in {"pkg/z.py", "pkg/a.py"}
    for line in {10, 2}
    for column in {7, 1}
    for shape, old in {("keyword", "amount"), ("attribute", "count")}
]
skipped = [
    Skipped(
        site=Site(path=path, line=line, column=column, shape="call", symbol=old),
        reason=reason,
    )
    for path in {"other/z.py", "other/a.py"}
    for line in {5, 1}
    for column in {3, 9}
    for old in {"create", "delete"}
    for reason in {SkipReason.STALE_SITE, SkipReason.DYNAMIC_KWARGS}
]
proposal = Proposal(
    change=Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer="#"),
        before="amount",
        after="amount_cents",
    ),
    edits=tuple(edits),
    skipped=tuple(skipped),
    diff="+amount_cents",
)
print(proposal.to_json(), end="")
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


# Spec AC4: byte-identical output across hash seeds.
def test_to_json_is_byte_stable_across_hash_seeds():
    assert to_json_with_hash_seed("0") == to_json_with_hash_seed("1")
