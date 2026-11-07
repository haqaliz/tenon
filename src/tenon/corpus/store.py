"""The JSONL corpus store: load history, append runs, update outcomes."""

import json
from collections.abc import Iterable
from pathlib import Path

from .record import CorpusRecord


class CorpusError(Exception):
    """A corpus file or record that cannot be read or written."""


def load_corpus(path: str | Path) -> tuple[CorpusRecord, ...]:
    """Every record in file order; blank lines ignored, a bad line named."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorpusError(f"cannot read corpus {path}: {exc}") from exc
    records: list[CorpusRecord] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError("record must be a JSON object")
            records.append(CorpusRecord.from_dict(data))
        except (TypeError, ValueError) as exc:
            raise CorpusError(f"{path}: line {number}: {exc}") from exc
    return tuple(records)


def append_records(path: str | Path, records: Iterable[CorpusRecord]) -> None:
    """Append one canonical line per record, keeping the existing history."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.to_json() + "\n")
