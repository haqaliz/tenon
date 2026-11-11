import threading
import time

from tenon.prove import tail
from tenon.service.runner import Outcome
from tenon.service.store import RunStore
from tenon.service.worker import Worker


def a_store(tmp_path):
    return RunStore(tmp_path / "runs.db")


def a_report(*, repos=1):
    return {"command": "provider", "summary": {"repos": repos, "passed": repos}}


# Spec AC4: an empty queue does no work and reports False.
def test_run_once_is_false_when_the_queue_is_empty(tmp_path):
    store = a_store(tmp_path)
    calls = []
    worker = Worker(store, lambda run: calls.append(run))

    assert worker.run_once() is False
    assert calls == []


# Spec AC4: the oldest queued run executes and finishes succeeded with its report.
def test_run_once_executes_and_finishes_succeeded(tmp_path):
    store = a_store(tmp_path)
    run = store.create_run("bundle.json")
    executed = []
    worker = Worker(
        store,
        lambda claimed: executed.append(claimed)
        or Outcome(0, a_report(), None),
    )

    assert worker.run_once() is True

    assert [entry.id for entry in executed] == [run.id]
    assert executed[0].status == "running"
    finished = store.get(run.id)
    assert finished.status == "succeeded"
    assert finished.exit == 0
    assert finished.report == a_report()
    assert finished.error is None
    assert finished.started_at is not None
    assert finished.finished_at is not None


# Spec AC4: exit 1 is a completed but failed run, report included.
def test_run_once_marks_a_nonzero_exit_failed_with_the_report(tmp_path):
    store = a_store(tmp_path)
    run = store.create_run("bundle.json")
    worker = Worker(
        store,
        lambda claimed: Outcome(1, {"summary": {"repos": 1, "failed": 1}}, None),
    )

    assert worker.run_once() is True

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert finished.exit == 1
    assert finished.report == {"summary": {"repos": 1, "failed": 1}}
    assert finished.error is None


# Spec AC4: a runner error is failed with its exit and error.
def test_run_once_marks_a_runner_error_failed(tmp_path):
    store = a_store(tmp_path)
    run = store.create_run("bundle.json")
    worker = Worker(store, lambda claimed: Outcome(2, None, "boom"))

    assert worker.run_once() is True

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert finished.exit == 2
    assert finished.report is None
    assert finished.error == "boom"


# Spec AC4: an exception is a failed run with a capped, report-free error.
def test_run_once_turns_an_exception_into_a_failed_run(tmp_path):
    store = a_store(tmp_path)
    run = store.create_run("bundle.json")

    def explode(claimed):
        raise RuntimeError(text)

    text = "\n".join(f"line {number}" for number in range(30))
    worker = Worker(store, explode)

    assert worker.run_once() is True

    finished = store.get(run.id)
    assert finished.status == "failed"
    assert finished.exit is None
    assert finished.report is None
    assert finished.error == tail(text)
    assert len(finished.error.splitlines()) == 20


# Spec AC4/S1: runs execute in FIFO order, one per call.
def test_run_once_is_fifo_and_sequential(tmp_path):
    store = a_store(tmp_path)
    store.create_run("first.json")
    store.create_run("second.json")
    seen = []
    worker = Worker(
        store,
        lambda claimed: seen.append(claimed.bundle) or Outcome(0, {}, None),
    )

    assert worker.run_once() is True
    assert worker.run_once() is True
    assert worker.run_once() is False

    assert seen == ["first.json", "second.json"]


# Spec AC4: start runs one daemon thread and stop joins it.
def test_start_and_stop_run_one_daemon_thread(tmp_path):
    store = a_store(tmp_path)
    store.create_run("bundle.json")
    done = threading.Event()
    finished = []

    def execute(claimed):
        finished.append(claimed.id)
        done.set()
        return Outcome(0, a_report(), None)

    worker = Worker(store, execute, poll=0.01)

    worker.start()
    assert done.wait(2)
    run_id = finished[0]
    worker.stop()

    assert worker._thread is not None
    assert worker._thread.daemon is True
    assert worker._thread.is_alive() is False
    assert store.get(run_id).status == "succeeded"


# Spec AC4: the idle wait is the injected clock when one is given.
def test_start_uses_the_injected_clock_for_the_idle_wait(tmp_path):
    store = a_store(tmp_path)
    waits = []
    waited = threading.Event()

    def clock(seconds):
        waits.append(seconds)
        waited.set()
        time.sleep(0.01)
        return False

    worker = Worker(store, lambda claimed: Outcome(0, {}, None), poll=0.25, clock=clock)

    worker.start()
    assert waited.wait(2)
    worker.stop()

    assert waits[0] == 0.25
