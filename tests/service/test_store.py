import sqlite3
from datetime import datetime, timezone

import pytest

from tenon.service.store import Run, RunStore, StoreError

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-11-11T12:00:00+00:00"


def a_now():
    return NOW


def an_id_factory(*values):
    remaining = iter(values)
    return lambda: next(remaining)


def a_store(tmp_path, *, name="runs.db", now=a_now, new_id=None):
    if new_id is None:
        new_id = an_id_factory(*(f"{number:032x}" for number in range(1, 101)))
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
