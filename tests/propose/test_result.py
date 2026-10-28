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


# Spec AC5: ProposalReason is the closed three-value vocabulary.
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
