import pytest

from tenon.corpus.record import CorpusRecord, Outcome, record_id
from tenon.corpus.report import CorpusReport, LevelStats, benchmark
from tenon.corpus.store import CorpusError
from tenon.prove.result import ProofLevel

REPO = "https://github.com/o/r"


def a_record(level="TESTS_PASSED", outcome=Outcome.PENDING, commit="commit-one"):
    change = {"kind": "signature", "path": "app.py", "symbol": commit}
    proposal = {"diff": f"--- a/{commit}\n+++ b/{commit}\n"}
    return CorpusRecord(
        id=record_id(REPO, commit, change, proposal),
        repo=REPO,
        commit=commit,
        change=change,
        proposal=proposal,
        proof={"level": level, "cause": None},
        pr=None,
        outcome=outcome,
        recorded="2026-11-07",
    )


# Spec AC1: mixed outcomes across two levels produce the right counts.
def test_grouping_counts_by_level_and_outcome():
    records = [
        a_record("TESTS_PASSED", Outcome.MERGED, "one"),
        a_record("TESTS_PASSED", Outcome.REJECTED, "two"),
        a_record("CHARACTERIZED", Outcome.PENDING, "three"),
        a_record("CHARACTERIZED", Outcome.MERGED, "four"),
    ]

    report = benchmark(records)

    assert report.total == 4
    tests = report.by_level[ProofLevel.TESTS_PASSED]
    assert (tests.count, tests.merged, tests.rejected) == (2, 1, 1)
    characterized = report.by_level[ProofLevel.CHARACTERIZED]
    assert (characterized.count, characterized.merged, characterized.pending) == (
        2,
        1,
        1,
    )
    assert report.outcomes[Outcome.MERGED] == 2
    assert report.outcomes[Outcome.REJECTED] == 1
    assert report.outcomes[Outcome.PENDING] == 1


# Spec AC3: every level and outcome is present, zero-filled when absent.
def test_every_level_and_outcome_is_zero_filled():
    report = benchmark([a_record()])

    assert set(report.by_level) == set(ProofLevel)
    assert set(report.outcomes) == set(Outcome)
    for level, stats in report.by_level.items():
        if level is ProofLevel.TESTS_PASSED:
            continue
        assert stats.count == 0
        assert stats.merged == stats.rejected == stats.closed == 0
        assert stats.incident == stats.local_only == stats.pending == 0
    assert report.by_level[ProofLevel.TESTS_PASSED].pending == 1
    assert report.outcomes[Outcome.PENDING] == 1
    assert report.outcomes[Outcome.MERGED] == 0


# Spec AC2: one merge and one rejection is a 0.5 merge rate.
def test_merge_rate_is_merged_over_known():
    report = benchmark(
        [
            a_record("TESTS_PASSED", Outcome.MERGED, "one"),
            a_record("TESTS_PASSED", Outcome.REJECTED, "two"),
        ]
    )

    stats = report.by_level[ProofLevel.TESTS_PASSED]
    assert (stats.merged, stats.rejected) == (1, 1)
    assert stats.known == 2
    assert stats.merge_rate == 0.5


# Spec AC2: no known outcome means no rate at all.
def test_merge_rate_is_none_when_no_outcome_is_known():
    report = benchmark(
        [
            a_record("TESTS_PASSED", Outcome.PENDING, "one"),
            a_record("TESTS_PASSED", Outcome.LOCAL_ONLY, "two"),
        ]
    )

    stats = report.by_level[ProofLevel.TESTS_PASSED]
    assert (stats.pending, stats.local_only) == (1, 1)
    assert stats.known == 0
    assert stats.merge_rate is None


# Spec AC2: local_only and pending stay out of the known denominator.
def test_local_and_pending_do_not_change_the_denominator():
    report = benchmark(
        [
            a_record("TESTS_PASSED", Outcome.MERGED, "one"),
            a_record("TESTS_PASSED", Outcome.LOCAL_ONLY, "two"),
            a_record("TESTS_PASSED", Outcome.PENDING, "three"),
        ]
    )

    stats = report.by_level[ProofLevel.TESTS_PASSED]
    assert stats.count == 3
    assert stats.known == 1
    assert stats.merge_rate == 1.0


# Spec AC2: a closed change is known but is not a merge.
def test_closed_is_known_but_not_merged():
    report = benchmark(
        [
            a_record("TESTS_PASSED", Outcome.MERGED, "one"),
            a_record("TESTS_PASSED", Outcome.CLOSED, "two"),
        ]
    )

    stats = report.by_level[ProofLevel.TESTS_PASSED]
    assert (stats.merged, stats.closed) == (1, 1)
    assert stats.known == 2
    assert stats.merge_rate == 0.5


# Spec AC6: an unknown proof level is a named error, not a silent skip.
def test_unknown_proof_level_raises_corpus_error_with_the_id():
    record = a_record(level="DONE")

    with pytest.raises(CorpusError, match=record.id):
        benchmark([record])
