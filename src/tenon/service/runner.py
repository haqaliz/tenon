"""Run one bundle through the shipped CLI in a subprocess."""

import json
import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tenon.prove import tail

_STOP_GRACE = 5


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one CLI run left behind: an exit, a report or a named error."""

    exit: int | None
    report: dict | None
    error: str | None
    cancelled: bool = False


def _error_message(result: subprocess.CompletedProcess) -> str:
    """The CLI's ``--json`` error message, when stdout is one."""
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError):
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return message if isinstance(message, str) else ""


# Spec AC2: start_new_session makes the child its own group, so a stop kills
# the CLI and its git children; an already-dead group is not an error.
def _stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    try:
        process.wait(timeout=_STOP_GRACE)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            return
        try:
            process.wait(timeout=_STOP_GRACE)
        except subprocess.TimeoutExpired:
            pass


class CommandRunner:
    """The shipped CLI as one injectable, cancellable subprocess."""

    def __init__(
        self,
        builder: Callable[[Path], list[str]],
        *,
        timeout: float = 3600,
        poll: float = 0.2,
        popen: Callable[..., subprocess.Popen] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._builder = builder
        self._timeout = timeout
        self._poll = poll
        self._popen = popen or subprocess.Popen
        self._clock = clock or time.monotonic

    # Spec AC2: poll the child so a cancel or the total timeout can stop it.
    def run(
        self, bundle: Path, cancel: Callable[[], bool] | None = None
    ) -> Outcome:
        argv = self._builder(bundle)
        deadline = self._clock() + self._timeout
        try:
            process = self._popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                start_new_session=True,
            )
        except OSError as error:
            return Outcome(None, None, tail(f"cannot run {argv[0]}: {error}"))

        while True:
            try:
                stdout, stderr = process.communicate(timeout=self._poll)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel():
                    _stop(process)
                    return Outcome(None, None, "run cancelled", cancelled=True)
                if self._clock() >= deadline:
                    _stop(process)
                    return Outcome(
                        None, None, f"run timed out after {self._timeout}s"
                    )

        result = subprocess.CompletedProcess(
            argv, process.returncode, stdout, stderr
        )
        # Spec AC4: only the CLI's completed envelope (0/1) carries a report.
        if result.returncode not in (0, 1):
            detail = tail(_error_message(result) or result.stderr)
            return Outcome(
                result.returncode,
                None,
                detail or f"run failed with exit {result.returncode}",
            )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            return Outcome(result.returncode, None, f"invalid report: {error}")
        if not isinstance(report, dict):
            return Outcome(
                result.returncode, None, "invalid report: expected a JSON object"
            )
        return Outcome(result.returncode, report, None)
