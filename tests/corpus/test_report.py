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
