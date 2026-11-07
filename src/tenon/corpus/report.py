"""The corpus report: group records by proof level and human outcome."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tenon.prove.result import ProofLevel

from .record import CorpusRecord, Outcome


@dataclass(frozen=True, slots=True)
class LevelStats:
    """The outcome counts for one proof level."""

    count: int
    merged: int
    rejected: int
    closed: int
    incident: int
    local_only: int
    pending: int
    known: int = 0
    merge_rate: float | None = None


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """The whole corpus: the total, per-level stats and outcome counts."""

    total: int
    by_level: Mapping[ProofLevel, LevelStats]
    outcomes: Mapping[Outcome, int]


def benchmark(records: Sequence[CorpusRecord]) -> CorpusReport:
    """Group records by proof level and outcome, keeping every enum value."""
    counts = {level: dict.fromkeys(Outcome, 0) for level in ProofLevel}
    outcomes = dict.fromkeys(Outcome, 0)
    for record in records:
        level = ProofLevel(record.proof["level"])
        counts[level][record.outcome] += 1
        outcomes[record.outcome] += 1
    by_level = {
        level: LevelStats(
            count=sum(counts[level].values()),
            merged=counts[level][Outcome.MERGED],
            rejected=counts[level][Outcome.REJECTED],
            closed=counts[level][Outcome.CLOSED],
            incident=counts[level][Outcome.INCIDENT],
            local_only=counts[level][Outcome.LOCAL_ONLY],
            pending=counts[level][Outcome.PENDING],
        )
        for level in ProofLevel
    }
    return CorpusReport(total=len(records), by_level=by_level, outcomes=outcomes)
