"""The one-thread worker: claim the oldest run, execute it, finish it."""

import threading
from collections.abc import Callable

from tenon.prove import tail

from .runner import Outcome
from .store import Run, RunStore


class Worker:
    """One daemon thread draining the queue one run at a time."""

    def __init__(
        self,
        store: RunStore,
        execute: Callable[[Run], Outcome],
        *,
        poll: float = 1.0,
        retries: int = 0,
        clock: Callable[[float], object] | None = None,
    ) -> None:
        self._store = store
        self._execute = execute
        self._poll = poll
        self._retries = retries
        self._stop = threading.Event()
        self._wait = clock or self._stop.wait
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Execute the oldest queued run; False when the queue is empty."""
        run = self._store.claim_next()
        if run is None:
            return False
        try:
            outcome = self._execute(run)
        except Exception as error:  # noqa: BLE001 - a runner crash is a failed run
            outcome = Outcome(None, None, tail(str(error)))
        # Spec AC1/AC2: cancel is terminal; a report is terminal; only a
        # report-free failure retries, within the configured budget.
        if outcome.cancelled or self._store.cancel_requested(run.id):
            self._store.finish(
                run.id,
                status="cancelled",
                exit=outcome.exit,
                report=outcome.report,
                error=outcome.error,
            )
        elif outcome.report is not None:
            status = (
                "succeeded"
                if outcome.exit == 0 and outcome.error is None
                else "failed"
            )
            self._store.finish(
                run.id,
                status=status,
                exit=outcome.exit,
                report=outcome.report,
                error=outcome.error,
            )
        elif run.attempts <= self._retries:
            self._store.requeue(run.id)
        else:
            self._store.finish(
                run.id,
                status="failed",
                exit=outcome.exit,
                report=None,
                error=outcome.error,
            )
        return True

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._wait(self._poll)
