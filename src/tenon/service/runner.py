"""Run one bundle through the shipped CLI in a subprocess."""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tenon.prove import tail


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one CLI run left behind: an exit, a report or a named error."""

    exit: int | None
    report: dict | None
    error: str | None


class CommandRunner:
    """The shipped CLI as one injectable subprocess."""

    def __init__(
        self,
        builder: Callable[[Path], list[str]],
        *,
        timeout: float = 3600,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self._builder = builder
        self._timeout = timeout
        self._runner = runner or subprocess.run

    def run(self, bundle: Path) -> Outcome:
        argv = self._builder(bundle)
        try:
            result = self._runner(
                argv,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return Outcome(None, None, f"run timed out after {self._timeout}s")
        except OSError as error:
            return Outcome(None, None, tail(f"cannot run {argv[0]}: {error}"))

        # Spec AC4: only the CLI's completed envelope (0/1) carries a report.
        if result.returncode not in (0, 1):
            return Outcome(result.returncode, None, tail(result.stderr))
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            return Outcome(result.returncode, None, f"invalid report: {error}")
        if not isinstance(report, dict):
            return Outcome(
                result.returncode, None, "invalid report: expected a JSON object"
            )
        return Outcome(result.returncode, report, None)
