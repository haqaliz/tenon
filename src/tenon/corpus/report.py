"""The corpus report: group records by proof level and human outcome."""

import json
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

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "merged": self.merged,
            "rejected": self.rejected,
            "closed": self.closed,
            "incident": self.incident,
            "local_only": self.local_only,
            "pending": self.pending,
            "known": self.known,
            "merge_rate": self.merge_rate,
        }


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """The whole corpus: the total, per-level stats and outcome counts."""

    total: int
    by_level: Mapping[ProofLevel, LevelStats]
    outcomes: Mapping[Outcome, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "by_level": {
                level.value: stats.to_dict()
                for level, stats in self.by_level.items()
            },
            "outcomes": {
                outcome.value: count for outcome, count in self.outcomes.items()
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def render_text(self) -> str:
        return render_text(self)


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


def _count(count: int, singular: str) -> str:
    return f"{count} {singular if count == 1 else singular + 's'}"


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    first = f"{cells[0]:<{widths[0]}}"
    rest = "  ".join(
        cell.rjust(width) for cell, width in zip(cells[1:], widths[1:])
    )
    return f"{first}  {rest}"


def render_text(report: CorpusReport) -> str:
    """The level table, one row per level, then the outcome counts."""
    rows = [
        (
            level.value,
            str(stats.count),
            str(stats.merged),
            str(stats.rejected),
            str(stats.closed),
            str(stats.incident),
            str(stats.local_only),
            str(stats.pending),
            "n/a" if stats.merge_rate is None else f"{stats.merge_rate:.2f}",
        )
        for level, stats in report.by_level.items()
    ]
    header = (
        "level",
        "count",
        "merged",
        "rejected",
        "closed",
        "incident",
        "local",
        "pending",
        "rate",
    )
    widths = [
        max(len(row[index]) for row in (header, *rows))
        for index in range(len(header))
    ]
    lines = [f"corpus: {_count(report.total, 'record')}", _row(header, widths)]
    lines.extend(_row(row, widths) for row in rows)
    outcomes = " ".join(
        f"{outcome.value}={count}" for outcome, count in report.outcomes.items()
    )
    lines.append(f"outcomes: {outcomes}")
    return "\n".join(lines) + "\n"
