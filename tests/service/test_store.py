import sqlite3
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
    ]


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


# Spec AC4: finish status is only succeeded or failed.
@pytest.mark.parametrize("status", ["queued", "running", "done", ""])
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


# Spec surface: the package exports the three public values.
def test_the_service_package_exports_the_store_surface():
    assert ExportedRun is Run
    assert ExportedEvent is Event
    assert ExportedRunStore is RunStore
