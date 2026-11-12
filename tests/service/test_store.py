import sqlite3
import threading
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from itertools import count

import pytest

from tenon.service import Event as ExportedEvent
from tenon.service import Run as ExportedRun
from tenon.service import RunStore as ExportedRunStore
from tenon.service.store import Event, Run, RunStore, StoreError

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-11-11T12:00:00+00:00"
OLD_SCHEMA = """
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    bundle TEXT,
    status TEXT,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    exit INTEGER,
    report TEXT,
    error TEXT,
    idempotency_key TEXT UNIQUE
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery TEXT UNIQUE,
    event TEXT,
    action TEXT,
    installation TEXT,
    received_at TEXT,
    payload TEXT
)
"""


def a_now():
    return NOW


def a_clock(*values):
    remaining = iter(values)
    return lambda: next(remaining)


def an_id_factory(*values):
    remaining = iter(values)
    return lambda: next(remaining)


def a_store(tmp_path, *, name="runs.db", now=a_now, new_id=None):
    if new_id is None:
        counter = count(1)
        new_id = lambda: f"{next(counter):032x}"  # noqa: E731
    return RunStore(tmp_path / name, now=now, new_id=new_id)


# Spec AC1: a created run is queued with a uuid4 hex id and a UTC timestamp.
def test_create_returns_a_queued_run_with_an_id_and_timestamp(tmp_path):
    store = a_store(tmp_path)

    run = store.create_run("acme/api")

    assert run.bundle == "acme/api"
    assert run.status == "queued"
    assert len(run.id) == 32
    assert all(character in "0123456789abcdef" for character in run.id)
    assert run.created_at == STAMP
    assert run.started_at is None
    assert run.finished_at is None
    assert run.exit is None
    assert run.report is None
    assert run.error is None
    assert run.idempotency_key is None


# Spec AC1: get returns the stored run and an unknown id is None.
def test_get_returns_the_run_and_unknown_is_none(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")

    assert store.get(created.id) == created
    assert store.get("f" * 32) is None


# Spec AC1: two creates are two distinct queued runs.
def test_two_creates_make_two_runs(tmp_path):
    store = a_store(tmp_path)

    first = store.create_run("acme/api")
    second = store.create_run("acme/web")

    assert first.id != second.id
    assert store.get(second.id) == second


# Spec AC2: a duplicate key returns the existing run and leaves one row.
def test_create_with_a_duplicate_key_returns_the_existing_run(tmp_path):
    store = a_store(tmp_path)

    first = store.create_run("acme/api", idempotency_key="key-one")
    second = store.create_run("acme/web", idempotency_key="key-one")

    assert second == first
    assert second.bundle == "acme/api"


# Spec AC2: distinct keys create distinct runs.
def test_create_with_distinct_keys_makes_distinct_runs(tmp_path):
    store = a_store(tmp_path)

    first = store.create_run("acme/api", idempotency_key="key-one")
    second = store.create_run("acme/api", idempotency_key="key-two")

    assert first.id != second.id
    assert second.idempotency_key == "key-two"


# Spec AC2: the key lookup returns the existing run and None when absent.
def test_find_by_idempotency_key_returns_the_run_or_none(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api", idempotency_key="key-one")

    assert store.find_by_idempotency_key("key-one") == created
    assert store.find_by_idempotency_key("key-two") is None
    assert store.find_by_idempotency_key(None) is None


# Spec AC7: reopening the file preserves the rows.
def test_reopening_the_store_preserves_runs(tmp_path):
    first_store = a_store(tmp_path)
    created = first_store.create_run("acme/api")
    first_store.close()

    reopened = a_store(tmp_path)

    assert reopened.get(created.id) == created


# Spec AC7: a bad path is a named error.
def test_a_missing_parent_directory_is_a_named_error(tmp_path):
    with pytest.raises(StoreError):
        RunStore(tmp_path / "missing" / "runs.db")


# Spec AC7: a file that is not a database is a named error.
def test_a_corrupt_file_is_a_named_error(tmp_path):
    path = tmp_path / "runs.db"
    path.write_bytes(b"not a database")

    with pytest.raises(StoreError):
        RunStore(path)


# Spec AC8: the injected clock and ids make the values deterministic.
def test_injected_now_and_id_make_create_deterministic(tmp_path):
    later = datetime(2027, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    store = RunStore(
        tmp_path / "runs.db",
        now=lambda: later,
        new_id=lambda: "a" * 32,
    )

    run = store.create_run("acme/api")

    assert run.id == "a" * 32
    assert run.created_at == "2027-01-02T03:04:05+00:00"


# Spec AC1/AC4: to_dict carries every column of a queued run.
def test_run_to_dict_has_the_stored_fields(tmp_path):
    store = a_store(tmp_path)
    run = store.create_run("acme/api", idempotency_key="key-one")

    assert run.to_dict() == {
        "id": run.id,
        "bundle": "acme/api",
        "status": "queued",
        "created_at": STAMP,
        "started_at": None,
        "finished_at": None,
        "exit": None,
        "report": None,
        "error": None,
        "idempotency_key": "key-one",
        "attempts": 0,
        "cancel_requested": False,
    }


# Spec dependency: the schema is the planned runs table.
def test_the_runs_schema_is_created(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)
    store.close()

    with sqlite3.connect(path) as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(runs)")
        ]

    assert columns == [
        "id",
        "bundle",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "exit",
        "report",
        "error",
        "idempotency_key",
        "attempts",
        "cancel_requested",
    ]


# Spec AC1: the new columns are NOT NULL integers defaulting to zero.
def test_the_attempt_columns_are_not_null_and_default_to_zero(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)
    store.close()

    with sqlite3.connect(path) as connection:
        info = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(runs)")
        }

    for name in ("attempts", "cancel_requested"):
        assert info[name][2] == "INTEGER"
        assert info[name][3] == 1
        assert info[name][4] == "0"


# Spec AC1: an old T13a database gains the columns and keeps its rows.
def test_an_old_schema_database_migrates_additively(tmp_path):
    path = tmp_path / "runs.db"
    old_id = "0" * 32
    with sqlite3.connect(path) as connection:
        connection.executescript(OLD_SCHEMA)
        connection.execute(
            "INSERT INTO runs (id, bundle, status, created_at, finished_at,"
            " exit, report) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (old_id, "acme/api", "succeeded", STAMP, STAMP, 0, '{"z":1}'),
        )

    store = a_store(tmp_path)

    old = store.get(old_id)
    assert old.bundle == "acme/api"
    assert old.status == "succeeded"
    assert old.finished_at == STAMP
    assert old.exit == 0
    assert old.report == {"z": 1}
    assert old.attempts == 0
    assert old.cancel_requested is False
    created = store.create_run("acme/web")
    assert store.claim_next().id == created.id
    assert store.get(created.id).attempts == 1
    store.close()

    with sqlite3.connect(path) as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(runs)")
        ]
    assert columns[-2:] == ["attempts", "cancel_requested"]


# Spec AC6: opening the store sets the hardening pragmas.
def test_open_sets_the_sqlite_pragmas(tmp_path):
    store = a_store(tmp_path)
    connection = store._connection

    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    store.close()


# Spec AC6: :memory: keeps working with the pragmas.
def test_an_in_memory_store_sets_the_supported_pragmas():
    store = RunStore(":memory:")
    connection = store._connection

    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "memory"
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    store.close()


# Spec edge case: :memory: works through the single connection.
def test_an_in_memory_store_works():
    store = RunStore(":memory:")

    run = store.create_run("acme/api")

    assert store.get(run.id) == run


# Spec AC3: claim returns the oldest queued run and marks it running.
def test_claim_returns_the_oldest_queued_run_and_marks_it_running(tmp_path):
    times = a_clock(
        datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 2, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 3, tzinfo=timezone.utc),
    )
    store = a_store(tmp_path, now=times)
    older = store.create_run("acme/api")
    newer = store.create_run("acme/web")

    claimed = store.claim_next()

    assert claimed.id == older.id
    assert claimed.bundle == "acme/api"
    assert claimed.status == "running"
    assert claimed.started_at == "2026-11-11T12:02:00+00:00"
    assert store.get(older.id).status == "running"
    assert store.get(newer.id).status == "queued"


# Spec AC3: equal created_at values are claimed in insertion order.
def test_claim_breaks_ties_by_insertion_order(tmp_path):
    store = a_store(tmp_path)
    first = store.create_run("acme/api")
    second = store.create_run("acme/web")

    assert store.claim_next().id == first.id
    assert store.claim_next().id == second.id


# Spec AC3: an empty queue claims None and a claimed run is never reclaimed.
def test_claim_is_none_when_empty_and_never_repeats(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")

    assert store.claim_next().id == created.id
    assert store.claim_next() is None


# Spec AC2: a claim increments attempts exactly once.
def test_a_claim_increments_attempts_exactly_once(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    assert created.attempts == 0
    assert created.to_dict()["attempts"] == 0

    claimed = store.claim_next()

    assert claimed.attempts == 1
    assert claimed.to_dict()["attempts"] == 1
    assert store.claim_next() is None
    assert store.get(created.id).attempts == 1


# Spec AC7: the lock lets parallel claimers take each run exactly once.
def test_parallel_claims_take_each_run_exactly_once(tmp_path):
    store = a_store(tmp_path)
    created = {store.create_run(f"acme/{number}").id for number in range(20)}
    claimed = []
    claimed_lock = threading.Lock()

    def claim_all():
        while (run := store.claim_next()) is not None:
            with claimed_lock:
                claimed.append(run)

    threads = [threading.Thread(target=claim_all) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {run.id for run in claimed} == created
    assert len(claimed) == len(created)
    assert {run.attempts for run in claimed} == {1}


# Spec AC2: a requeue returns a running run to the queue and keeps attempts.
def test_requeue_keeps_attempts_and_clears_the_run_fields(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()

    requeued = store.requeue(created.id)

    assert requeued.status == "queued"
    assert requeued.started_at is None
    assert requeued.finished_at is None
    assert requeued.exit is None
    assert requeued.report is None
    assert requeued.error is None
    assert requeued.attempts == 1
    assert store.get(created.id) == requeued
    assert store.claim_next().attempts == 2


# Spec AC2: a requeue clears a stale finish payload as well.
def test_requeue_clears_a_stale_finish_payload(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()
    with store._connection:
        store._connection.execute(
            "UPDATE runs SET finished_at = ?, exit = ?, report = ?,"
            " error = ? WHERE id = ?",
            (STAMP, 1, '{"z":1}', "boom", created.id),
        )

    requeued = store.requeue(created.id)

    assert requeued.finished_at is None
    assert requeued.exit is None
    assert requeued.report is None
    assert requeued.error is None


# Spec AC2: only a running run can be requeued.
@pytest.mark.parametrize("status", ["queued", "succeeded", "failed"])
def test_requeue_rejects_a_non_running_run(tmp_path, status):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    if status != "queued":
        store.claim_next()
        store.finish(created.id, status=status, exit=0, report=None)

    with pytest.raises(ValueError, match="not running"):
        store.requeue(created.id)


# Spec AC2: an unknown run cannot be requeued.
def test_requeue_rejects_an_unknown_run(tmp_path):
    store = a_store(tmp_path)

    with pytest.raises(ValueError, match="unknown run"):
        store.requeue("f" * 32)


# Spec AC4: finish succeeds a running run with exit, report and finished_at.
def test_finish_succeeded_records_exit_report_and_timestamp(tmp_path):
    times = a_clock(
        datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 2, tzinfo=timezone.utc),
    )
    store = a_store(tmp_path, now=times)
    created = store.create_run("acme/api")
    store.claim_next()

    finished = store.finish(
        created.id,
        status="succeeded",
        exit=0,
        report={"results": [], "summary": {"changed": 0}},
    )

    assert finished.status == "succeeded"
    assert finished.exit == 0
    assert finished.report == {"results": [], "summary": {"changed": 0}}
    assert finished.error is None
    assert finished.finished_at == "2026-11-11T12:02:00+00:00"
    assert finished.attempts == 1
    assert store.get(created.id) == finished


# Spec AC4: a failed run keeps its exit code and error.
def test_finish_failed_records_the_exit_and_error(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()

    finished = store.finish(
        created.id,
        status="failed",
        exit=1,
        report=None,
        error="runner exited 1: boom",
    )

    assert finished.status == "failed"
    assert finished.exit == 1
    assert finished.report is None
    assert finished.error == "runner exited 1: boom"
    assert finished.finished_at == STAMP


# Spec AC3: cancelled is a terminal status accepted by finish.
def test_finish_accepts_cancelled(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()

    finished = store.finish(
        created.id, status="cancelled", exit=143, report=None
    )

    assert finished.status == "cancelled"
    assert finished.exit == 143
    assert finished.attempts == 1
    assert finished.finished_at == STAMP


# Spec AC4: finish status is only succeeded, failed or cancelled.
@pytest.mark.parametrize(
    "status", ["queued", "running", "cancelling", "done", ""]
)
def test_finish_rejects_an_invalid_status(tmp_path, status):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()

    with pytest.raises(ValueError):
        store.finish(created.id, status=status, exit=0, report=None)


# Spec AC4: only a running run can finish.
def test_finish_rejects_a_queued_run(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")

    with pytest.raises(ValueError):
        store.finish(created.id, status="succeeded", exit=0, report=None)


# Spec AC4: a finished run cannot finish twice.
def test_finish_rejects_a_second_finish(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()
    store.finish(created.id, status="succeeded", exit=0, report=None)

    with pytest.raises(ValueError):
        store.finish(created.id, status="failed", exit=1, report=None)


# Spec AC4: an unknown run cannot finish.
def test_finish_rejects_an_unknown_run(tmp_path):
    store = a_store(tmp_path)

    with pytest.raises(ValueError):
        store.finish("f" * 32, status="succeeded", exit=0, report=None)


# Spec AC4: the stored report is canonical JSON.
def test_finish_stores_the_report_as_canonical_json(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()
    store.finish(
        created.id,
        status="succeeded",
        exit=0,
        report={"z": 1, "a": {"two": 2, "one": 1}},
    )
    store.close()

    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT report FROM runs WHERE id = ?", (created.id,)
        ).fetchone()[0]

    assert stored == '{"a":{"one":1,"two":2},"z":1}'


# Spec AC3: cancelling a queued run is terminal immediately.
def test_request_cancel_cancels_a_queued_run(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")

    cancelled = store.request_cancel(created.id)

    assert cancelled.status == "cancelled"
    assert cancelled.finished_at == STAMP
    assert cancelled.started_at is None
    assert cancelled.cancel_requested is False
    assert store.get(created.id) == cancelled
    assert store.claim_next() is None
    assert store.request_cancel(created.id) == cancelled


# Spec AC3: cancelling a running run only sets the flag.
def test_request_cancel_flags_a_running_run(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    claimed = store.claim_next()

    cancelling = store.request_cancel(created.id)

    assert cancelling.status == "running"
    assert cancelling.cancel_requested is True
    assert cancelling.to_dict()["cancel_requested"] is True
    assert cancelling.started_at == claimed.started_at
    assert cancelling.finished_at is None
    assert store.cancel_requested(created.id) is True
    assert store.get(created.id) == cancelling


# Spec AC3: a terminal run is returned unchanged.
def test_request_cancel_returns_a_terminal_run_unchanged(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()
    finished = store.finish(created.id, status="succeeded", exit=0, report=None)

    assert store.request_cancel(created.id) == finished


# Spec AC3: unknown cancels are None and the flag is false.
def test_request_cancel_and_the_flag_handle_unknown_runs(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")

    assert store.request_cancel("f" * 32) is None
    assert store.cancel_requested("f" * 32) is False
    assert store.cancel_requested(created.id) is False


# Spec AC4: recover re-queues a stranded run and keeps its attempt count.
def test_recover_requeues_a_stranded_run(tmp_path):
    store = a_store(tmp_path)
    running = store.create_run("acme/api")
    waiting = store.create_run("acme/web")
    store.claim_next()

    assert store.recover() == 1

    recovered = store.get(running.id)
    assert recovered.status == "queued"
    assert recovered.started_at is None
    assert recovered.attempts == 1
    assert store.get(waiting.id) == waiting
    assert store.recover() == 0


# Spec AC4: recover cancels a stranded run whose cancel was requested.
def test_recover_cancels_a_run_with_a_cancel_request(tmp_path):
    store = a_store(tmp_path)
    created = store.create_run("acme/api")
    store.claim_next()
    store.request_cancel(created.id)

    assert store.recover() == 1

    recovered = store.get(created.id)
    assert recovered.status == "cancelled"
    assert recovered.finished_at == STAMP
    assert recovered.cancel_requested is True


# Spec AC4: recover counts both branches and leaves terminal runs alone.
def test_recover_counts_both_branches_and_leaves_terminal_runs(tmp_path):
    store = a_store(tmp_path)
    requeued = store.create_run("acme/requeued")
    cancelled = store.create_run("acme/cancelled")
    done = store.create_run("acme/done")
    store.claim_next()
    store.claim_next()
    store.request_cancel(cancelled.id)
    store.claim_next()
    finished = store.finish(done.id, status="failed", exit=1, report=None)

    assert store.recover() == 2

    assert store.get(requeued.id).status == "queued"
    assert store.get(cancelled.id).status == "cancelled"
    assert store.get(done.id) == finished


# Spec AC5: counts lists all five statuses and follows the transitions.
def test_counts_lists_all_five_statuses_and_follows_transitions(tmp_path):
    store = a_store(tmp_path)
    assert store.counts() == {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    store.create_run("acme/running")
    succeeded = store.create_run("acme/succeeded")
    failed = store.create_run("acme/failed")
    cancelled = store.create_run("acme/cancelled")
    store.create_run("acme/queued")
    assert store.counts()["queued"] == 5

    assert store.claim_next().status == "running"
    assert store.claim_next().id == succeeded.id
    store.finish(succeeded.id, status="succeeded", exit=0, report=None)
    assert store.claim_next().id == failed.id
    store.finish(failed.id, status="failed", exit=1, report=None)
    store.request_cancel(cancelled.id)

    assert store.counts() == {
        "queued": 1,
        "running": 1,
        "succeeded": 1,
        "failed": 1,
        "cancelled": 1,
    }


# Spec AC5: list returns newest-first.
def test_list_is_newest_first(tmp_path):
    times = a_clock(
        datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 11, 12, 2, tzinfo=timezone.utc),
    )
    store = a_store(tmp_path, now=times)
    first = store.create_run("acme/one")
    second = store.create_run("acme/two")
    third = store.create_run("acme/three")

    assert store.list() == (third, second, first)


# Spec AC5: list accepts a limit and returns a tuple.
def test_list_respects_the_limit(tmp_path):
    store = a_store(tmp_path)
    for number in range(3):
        store.create_run(f"acme/{number}")

    listed = store.list(limit=2)

    assert isinstance(listed, tuple)
    assert len(listed) == 2


# Spec AC5: the default limit is 50.
def test_list_defaults_to_fifty(tmp_path):
    store = a_store(tmp_path)
    for number in range(51):
        store.create_run(f"acme/{number}")

    assert len(store.list()) == 50


# Spec AC5: the limit is bounded to 1..200.
def test_list_clamps_the_limit_to_one_and_two_hundred(tmp_path):
    store = a_store(tmp_path)
    for number in range(201):
        store.create_run(f"acme/{number}")

    assert len(store.list(limit=0)) == 1
    assert len(store.list(limit=500)) == 200


# Spec AC6: a webhook event round-trips with a UTC timestamp and its payload.
def test_record_event_stores_the_event_and_payload(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)

    recorded = store.record_event(
        "delivery-one",
        "installation",
        action="created",
        installation="42",
        payload={"z": 1, "a": {"two": 2, "one": 1}},
    )
    store.close()

    assert recorded is True
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT delivery, event, action, installation, received_at, payload"
            " FROM events"
        ).fetchone()
    assert row == (
        "delivery-one",
        "installation",
        "created",
        "42",
        STAMP,
        '{"a":{"one":1,"two":2},"z":1}',
    )


# Spec AC6: a duplicate delivery returns False and leaves the first event only.
def test_record_event_deduplicates_the_delivery(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)
    store.record_event("delivery-one", "push", payload={"number": 1})

    duplicate = store.record_event(
        "delivery-one", "pull_request", payload={"number": 2}
    )
    store.close()

    assert duplicate is False
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT event, payload FROM events WHERE delivery = ?",
            ("delivery-one",),
        ).fetchall()
    assert rows == [("push", '{"number":1}')]


# Spec AC6: the optional event fields default to NULL.
def test_record_event_allows_omitted_details(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)

    assert store.record_event("delivery-one", "ping") is True
    store.close()

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT action, installation, payload FROM events"
        ).fetchone()
    assert row == (None, None, None)


# Spec AC6: Event is a frozen value with a full to_dict.
def test_event_to_dict_has_the_stored_fields():
    event = Event(
        delivery="delivery-one",
        event="push",
        action=None,
        installation="42",
        received_at=STAMP,
        payload={"number": 1},
    )

    assert event.to_dict() == {
        "delivery": "delivery-one",
        "event": "push",
        "action": None,
        "installation": "42",
        "received_at": STAMP,
        "payload": {"number": 1},
    }
    with pytest.raises(FrozenInstanceError):
        event.delivery = "other"


# Spec dependency: the schema is the planned events table.
def test_the_events_schema_is_created(tmp_path):
    path = tmp_path / "runs.db"
    store = a_store(tmp_path)
    store.close()

    with sqlite3.connect(path) as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        ]

    assert columns == [
        "id",
        "delivery",
        "event",
        "action",
        "installation",
        "received_at",
        "payload",
    ]


# Spec AC7: reopening the file preserves runs and events.
def test_reopening_preserves_both_tables(tmp_path):
    first_store = a_store(tmp_path)
    run = first_store.create_run("acme/api")
    first_store.record_event("delivery-one", "push", payload={"number": 1})
    first_store.close()

    reopened = a_store(tmp_path)

    assert reopened.get(run.id) == run
    assert reopened.record_event("delivery-one", "push") is False


# Spec AC1: a fresh open store pings true.
def test_a_fresh_store_pings_true(tmp_path):
    store = a_store(tmp_path)

    assert store.ping() is True


# Spec AC1: a closed store pings false instead of raising.
def test_a_closed_store_pings_false(tmp_path):
    store = a_store(tmp_path)
    store.close()

    assert store.ping() is False


# Spec AC1: a broken database pings false instead of raising.
def test_a_broken_database_pings_false(tmp_path):
    path = tmp_path / "broken.db"
    path.write_bytes(b"not a database")
    store = RunStore(":memory:")
    store.close()
    store._connection = sqlite3.connect(path, check_same_thread=False)

    assert store.ping() is False


# Spec surface: the package exports the three public values.
def test_the_service_package_exports_the_store_surface():
    assert ExportedRun is Run
    assert ExportedEvent is Event
    assert ExportedRunStore is RunStore
