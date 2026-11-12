"""A durable SQLite run queue and webhook-event log."""

import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    bundle TEXT,
    status TEXT,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    exit INTEGER,
    report TEXT,
    error TEXT,
    idempotency_key TEXT UNIQUE,
    attempts INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery TEXT UNIQUE,
    event TEXT,
    action TEXT,
    installation TEXT,
    received_at TEXT,
    payload TEXT
)
"""


class StoreError(Exception):
    """A store file that cannot be opened or upgraded."""


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


@dataclass(frozen=True, slots=True)
class Run:
    """One queued or finished migration run."""

    id: str
    bundle: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit: int | None = None
    report: dict | None = None
    error: str | None = None
    idempotency_key: str | None = None
    attempts: int = 0
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bundle": self.bundle,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit": self.exit,
            "report": self.report,
            "error": self.error,
            "idempotency_key": self.idempotency_key,
            "attempts": self.attempts,
            "cancel_requested": self.cancel_requested,
        }


@dataclass(frozen=True, slots=True)
class Event:
    """One deduplicated webhook delivery."""

    delivery: str
    event: str
    action: str | None
    installation: str | None
    received_at: str
    payload: dict | None

    def to_dict(self) -> dict:
        return {
            "delivery": self.delivery,
            "event": self.event,
            "action": self.action,
            "installation": self.installation,
            "received_at": self.received_at,
            "payload": self.payload,
        }


def _row_to_run(row: sqlite3.Row) -> Run:
    report = row["report"]
    return Run(
        id=row["id"],
        bundle=row["bundle"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        exit=row["exit"],
        report=None if report is None else json.loads(report),
        error=row["error"],
        idempotency_key=row["idempotency_key"],
        attempts=row["attempts"],
        cancel_requested=bool(row["cancel_requested"]),
    )


# Spec AC1: T13a databases are upgraded in place, one column at a time.
def _ensure_run_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(runs)")
    }
    for name in ("attempts", "cancel_requested"):
        if name not in columns:
            connection.execute(
                f"ALTER TABLE runs ADD COLUMN {name}"
                " INTEGER NOT NULL DEFAULT 0"
            )


class RunStore:
    """The shared SQLite store, serialized by one lock and one connection."""

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._lock = threading.Lock()
        connection = None
        try:
            connection = sqlite3.connect(str(path), check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.executescript(_SCHEMA)
            with connection:
                _ensure_run_columns(connection)
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise StoreError(f"cannot open store {path}: {exc}") from exc
        self._connection = connection

    def create_run(
        self, bundle: str, idempotency_key: str | None = None
    ) -> Run:
        with self._lock:
            if idempotency_key is not None:
                row = self._connection.execute(
                    "SELECT * FROM runs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    return _row_to_run(row)
            run = Run(
                id=self._new_id(),
                bundle=bundle,
                status="queued",
                created_at=self._now().isoformat(),
                idempotency_key=idempotency_key,
            )
            with self._connection:
                self._connection.execute(
                    "INSERT INTO runs (id, bundle, status, created_at,"
                    " idempotency_key) VALUES (?, ?, ?, ?, ?)",
                    (
                        run.id,
                        run.bundle,
                        run.status,
                        run.created_at,
                        run.idempotency_key,
                    ),
                )
            return run

    def claim_next(self) -> Run | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE status = 'queued'"
                " ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            started_at = self._now().isoformat()
            with self._connection:
                self._connection.execute(
                    "UPDATE runs SET status = 'running', started_at = ?,"
                    " attempts = attempts + 1 WHERE id = ? AND status = 'queued'",
                    (started_at, row["id"]),
                )
            return replace(
                _row_to_run(row),
                status="running",
                started_at=started_at,
                attempts=row["attempts"] + 1,
            )

    # Spec AC2: a retry re-queues the same row and keeps its attempt count.
    def requeue(self, run_id: str) -> Run:
        with self._lock:
            row = self._get_row(run_id)
            if row is None:
                raise ValueError(f"unknown run: {run_id}")
            if row["status"] != "running":
                raise ValueError(f"run {run_id} is {row['status']}, not running")
            with self._connection:
                self._connection.execute(
                    "UPDATE runs SET status = 'queued', started_at = NULL,"
                    " finished_at = NULL, exit = NULL, report = NULL,"
                    " error = NULL WHERE id = ? AND status = 'running'",
                    (run_id,),
                )
            return _row_to_run(self._get_row(run_id))

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        exit: int,
        report: dict | None,
        error: str | None = None,
    ) -> Run:
        if status not in ("succeeded", "failed"):
            raise ValueError(f"invalid finish status: {status}")
        with self._lock:
            row = self._get_row(run_id)
            if row is None:
                raise ValueError(f"unknown run: {run_id}")
            if row["status"] != "running":
                raise ValueError(f"run {run_id} is {row['status']}, not running")
            with self._connection:
                self._connection.execute(
                    "UPDATE runs SET status = ?, finished_at = ?, exit = ?,"
                    " report = ?, error = ? WHERE id = ? AND status = 'running'",
                    (
                        status,
                        self._now().isoformat(),
                        exit,
                        None if report is None else _canonical_json(report),
                        error,
                        run_id,
                    ),
                )
            return _row_to_run(self._get_row(run_id))

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._get_row(run_id)
        return None if row is None else _row_to_run(row)

    def find_by_idempotency_key(self, key: str | None) -> Run | None:
        """The run for one key, or None; keeps the create path's replay cheap."""
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return None if row is None else _row_to_run(row)

    def list(self, limit: int = 50) -> tuple[Run, ...]:
        limit = max(1, min(limit, 200))
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_row_to_run(row) for row in rows)

    def record_event(
        self,
        delivery: str,
        event: str,
        action: str | None = None,
        installation: str | None = None,
        payload: dict | None = None,
    ) -> bool:
        with self._lock:
            try:
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO events (delivery, event, action,"
                        " installation, received_at, payload)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            delivery,
                            event,
                            action,
                            installation,
                            self._now().isoformat(),
                            None if payload is None else _canonical_json(payload),
                        ),
                    )
            except sqlite3.IntegrityError:
                return False
        return True

    def _get_row(self, run_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # Spec AC1: a cheap liveness read; any database error means not ready.
    def ping(self) -> bool:
        with self._lock:
            try:
                self._connection.execute("SELECT 1")
            except sqlite3.Error:
                return False
        return True
