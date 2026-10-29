"""The proposer seam: any object may propose; assembly still decides."""

from dataclasses import replace
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, SiteShape, locate
from tenon.propose import Edit, ProposalReason, RuleProposer, SkipReason, propose

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
SDK_DECOY = FIXTURES / "sdk-decoy"
STRIPE = LocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"


def a_component_rename():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before="amount",
        after="amount_cents",
    )


class FakeProposer:
    """Not a RuleProposer: proves assembly needs no rule-specific path."""

    def __init__(self, *edits):
        self.edits = tuple(edits)

    def propose(self, change, located, root):
        return self.edits


def recorded_edit():
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    return RuleProposer().propose(change, located, SDK_BASIC)[0]


def test_a_fake_proposer_edit_goes_through_the_same_assembly():
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    edit = recorded_edit()

    proposal = propose(change, located, SDK_BASIC, proposer=FakeProposer(edit))

    assert proposal.edits == (edit,)
    assert proposal.reason is None
    assert "amount_cents=amount" in proposal.diff


def test_a_fake_proposer_cannot_edit_an_ambiguous_site():
    change = a_component_rename()
    located = locate(change, SDK_DECOY, STRIPE)
    certain = RuleProposer().propose(change, located, SDK_DECOY)[0]
    ambiguous = Edit(
        path="acme/mixed.py",
        line=10,
        column=8,
        shape=SiteShape.KEYWORD,
        old="amount",
        new="amount_cents",
    )

    proposal = propose(
        change, located, SDK_DECOY, proposer=FakeProposer(certain, ambiguous)
    )

    assert proposal.edits == (certain,)
    assert "record(amount_cents=1)" not in proposal.diff
    assert [
        (entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [(10, 8, SkipReason.UNROOTED_RECEIVER)]


def test_a_fake_proposer_cannot_bypass_verification():
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    fabricated = replace(recorded_edit(), old="nominal")

    proposal = propose(
        change, located, SDK_BASIC, proposer=FakeProposer(fabricated)
    )

    assert proposal.reason is ProposalReason.STALE_SITE
    assert proposal.edits == ()
    assert proposal.diff == ""
    assert [
        (entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [(5, 23, SkipReason.STALE_SITE)]


def test_a_fake_proposer_cannot_escape_the_repository():
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    unsafe = replace(recorded_edit(), path="/etc/passwd")

    with pytest.raises(ValueError):
        propose(change, located, SDK_BASIC, proposer=FakeProposer(unsafe))
