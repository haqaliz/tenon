"""The first real vendor spec pair: Twilio Lookups, 2.0.0 -> 2.10.0.

Committed so T1's real-spec behaviour is guarded offline. The pair is the
readable half of the M0.3 dig; Stripe's spec refuses on cyclic refs before this
point and cannot be committed at 4.4 MB.
"""

from pathlib import Path

from tenon.detect import ChangeKind, diff, load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def changes():
    return diff(
        load(FIXTURES / "twilio-lookups-2.0.0.json"),
        load(FIXTURES / "twilio-lookups-2.10.0.json"),
    ).changes


def test_a_real_vendor_pair_diffs_without_refusal():
    result = diff(
        load(FIXTURES / "twilio-lookups-2.0.0.json"),
        load(FIXTURES / "twilio-lookups-2.10.0.json"),
    )

    assert len(result.changes) == 37
    assert result.unanalyzed == ()


def test_the_real_pair_reports_three_breaking_schema_removals():
    removed = [change for change in changes() if change.kind is ChangeKind.SCHEMA_REMOVED]
    assert {change.before for change in removed} == {
        "lookups.v2.phone_number",
        "phone_number_enum_type",
        "phone_number_enum_validation_error",
    }
    assert all(change.breaking for change in removed)


def test_the_real_pair_has_no_renames_to_propose():
    # The M0.3 finding: two years of this real vendor's changes contain nothing
    # T3's single rename rule can fix.
    assert [change for change in changes() if change.kind is ChangeKind.RENAMED] == []
