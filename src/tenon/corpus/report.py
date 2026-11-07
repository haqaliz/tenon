"""The corpus report: group records by proof level and human outcome."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tenon.prove.result import ProofLevel

from .record import CorpusRecord, Outcome
from .store import CorpusError


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
        try:
            level = ProofLevel(record.proof["level"])
        except (KeyError, ValueError) as exc:
            raise CorpusError(
                f"record {record.id}: unknown proof level "
                f"{record.proof.get('level')!r}"
            ) from exc
        counts[level][record.outcome] += 1
        outcomes[record.outcome] += 1
    by_level = {}
    for level in ProofLevel:
        counts_for_level = counts[level]
        known = sum(
            counts_for_level[outcome]
            for outcome in (
                Outcome.MERGED,
                Outcome.REJECTED,
                Outcome.CLOSED,
                Outcome.INCIDENT,
            )
        )
        by_level[level] = LevelStats(
            count=sum(counts_for_level.values()),
            merged=counts_for_level[Outcome.MERGED],
            rejected=counts_for_level[Outcome.REJECTED],
            closed=counts_for_level[Outcome.CLOSED],
            incident=counts_for_level[Outcome.INCIDENT],
            local_only=counts_for_level[Outcome.LOCAL_ONLY],
            pending=counts_for_level[Outcome.PENDING],
            known=known,
            merge_rate=(
                counts_for_level[Outcome.MERGED] / known if known > 0 else None
            ),
        )
    return CorpusReport(total=len(records), by_level=by_level, outcomes=outcomes)
