"""The benchmark corpus: validated records in a JSONL history."""

from .record import CorpusRecord, Outcome, record_id
from .store import (
    CorpusError,
    append_records,
    load_corpus,
    update_outcome,
)

__all__ = [
    "CorpusError",
    "CorpusRecord",
    "Outcome",
    "append_records",
    "load_corpus",
    "record_id",
    "update_outcome",
]
