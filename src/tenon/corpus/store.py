"""The JSONL corpus store: load history, append runs, update outcomes."""

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from .record import CorpusRecord, Outcome


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


def _rewrite(path: Path, records: Iterable[CorpusRecord]) -> None:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            for record in records:
                handle.write(record.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass
        raise


def update_outcome(
    path: str | Path,
    id: str,
    outcome: Outcome | str,
    outcome_url: str | None = None,
    notes: str | None = None,
) -> CorpusRecord:
    """Replace one record's outcome in place, keeping its id and the file order."""
    path = Path(path)
    records = list(load_corpus(path))
    for index, record in enumerate(records):
        if record.id == id:
            break
    else:
        raise CorpusError(f"unknown corpus id: {id}")
    updated = replace(
        record,
        outcome=outcome,
        outcome_url=record.outcome_url if outcome_url is None else outcome_url,
        notes=record.notes if notes is None else notes,
    )
    records[index] = updated
    _rewrite(path, records)
    return updated
