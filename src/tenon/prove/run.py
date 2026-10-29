"""Run one check in the copy and record what happened."""

import os
import subprocess
from pathlib import Path
from typing import Sequence

from .result import CheckResult, tail


def _text(value: str | bytes | None) -> str:
    """TimeoutExpired may carry bytes even in text mode; normalise to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_check(
    command: Sequence[str],
    cwd: str | Path,
    kind: str,
    timeout: float,
) -> CheckResult:
    """Run ``command`` in ``cwd`` with a timeout, capping both output tails.

    A missing executable is a check that exited 127, not an exception: the
    command the user gave never ran.
    """
    if isinstance(command, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    command = tuple(command)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            kind=kind,
            command=command,
            returncode=None,
            timed_out=True,
            stdout_tail=tail(_text(exc.stdout)),
            stderr_tail=tail(_text(exc.stderr)),
        )
    except OSError as exc:
        return CheckResult(
            kind=kind,
            command=command,
            returncode=127,
            timed_out=False,
            stderr_tail=f"could not run {command[0]!r}: {exc}",
        )
    return CheckResult(
        kind=kind,
        command=command,
        returncode=completed.returncode,
        timed_out=False,
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )
