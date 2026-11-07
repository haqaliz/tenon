"""The benchmark corpus: validated records in a JSONL history."""

from .record import CorpusRecord, Outcome, record_id
from .report import CorpusReport, LevelStats, benchmark
from .store import (
    CorpusError,
    append_records,
    load_corpus,
    update_outcome,
)

__all__ = [
    "CorpusError",
    "CorpusRecord",
    "CorpusReport",
    "LevelStats",
    "Outcome",
    "append_records",
    "benchmark",
    "load_corpus",
    "record_id",
    "update_outcome",
]
