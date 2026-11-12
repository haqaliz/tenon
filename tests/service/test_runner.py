import json
import signal
import subprocess
from dataclasses import FrozenInstanceError

import pytest

from tenon.prove import tail
from tenon.service import runner as runner_module
from tenon.service.runner import CommandRunner, Outcome


def a_process(*, returncode=0, stdout="", stderr="", timeouts=0, waits=0):
    """One fake Popen: communicate may time out, then return the output."""

    class FakeProcess:
        pid = 4242

        def __init__(self):
            self.returncode = None
            self._timeouts = timeouts
            self._waits = waits
            self.communicate_calls = []
            self.wait_calls = []

        def communicate(self, timeout=None):
            self.communicate_calls.append(timeout)
            if self._timeouts:
                self._timeouts -= 1
                raise subprocess.TimeoutExpired(["tenon"], timeout)
            self.returncode = returncode
            return stdout, stderr

        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            if self._waits:
                self._waits -= 1
                raise subprocess.TimeoutExpired(["tenon"], timeout)
            self.returncode = returncode
            return returncode

    return FakeProcess()


def a_popen(process):
    """One fake Popen factory that records the argv and its kwargs."""
    calls = []

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    return calls, popen


def a_runner(process):
    calls, popen = a_popen(process)
    builder = lambda bundle: ["tenon", "provider", "migrate", str(bundle)]  # noqa: E731
    return CommandRunner(builder, popen=popen), calls


def a_clock(*values):
    remaining = iter(values)
    return lambda: next(remaining)


def a_signals(monkeypatch):
    """Record process-group signals instead of touching a real group."""
    seen = []
    monkeypatch.setattr(
        runner_module.os, "killpg", lambda pid, sig: seen.append((pid, sig))
    )
    return seen


# Spec AC2: Outcome is a frozen value with the exit, report, error and cancel.
def test_outcome_is_a_frozen_value():
    outcome = Outcome(exit=0, report={"summary": {}}, error=None)

    assert outcome.exit == 0
    assert outcome.report == {"summary": {}}
    assert outcome.error is None
    assert outcome.cancelled is False
    with pytest.raises(FrozenInstanceError):
        outcome.exit = 1


# Spec AC2: the builder receives the bundle and the child is its own session.
def test_run_builds_the_argv_and_runs_in_a_new_session(tmp_path):
    bundle = tmp_path / "bundle.json"
    process = a_process(stdout='{"command":"provider"}')
    runner, calls = a_runner(process)

    outcome = runner.run(bundle)

    (argv, kwargs), = calls
    assert argv == ["tenon", "provider", "migrate", str(bundle)]
    assert kwargs == {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "shell": False,
        "start_new_session": True,
    }
    assert process.communicate_calls == [0.2]
    assert outcome == Outcome(0, {"command": "provider"}, None)


# Spec AC2: an exit 0 fan-out envelope is a completed run with its report.
def test_exit_zero_with_a_json_report_is_a_completed_run(tmp_path):
    report = {"command": "provider", "summary": {"repos": 2, "passed": 2}}
    runner, _calls = a_runner(a_process(stdout=json.dumps(report)))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(0, report, None)


# Spec AC2: exit 1 with a JSON envelope keeps the report and the exit.
def test_exit_one_with_a_json_report_is_a_completed_run(tmp_path):
    runner, _calls = a_runner(
        a_process(returncode=1, stdout='{"summary":{"repos":1,"failed":1}}')
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 1
    assert outcome.report == {"summary": {"repos": 1, "failed": 1}}
    assert outcome.error is None


# Spec AC2: exit 2 is a run error carrying the capped stderr.
def test_exit_two_uses_the_stderr_as_the_error(tmp_path):
    runner, _calls = a_runner(
        a_process(returncode=2, stdout='{"ignored":true}', stderr="boom\n")
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 2
    assert outcome.report is None
    assert outcome.error == "boom"


# Spec AC2: the CLI writes --json errors to stdout; use that message before stderr.
def test_exit_two_uses_the_json_error_message(tmp_path):
    stdout = '{"error":{"kind":"usage","message":"--api-token is required"}}'
    runner, _calls = a_runner(a_process(returncode=2, stdout=stdout))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 2
    assert outcome.report is None
    assert outcome.error == "--api-token is required"


# Spec AC2: an exit with no output still names the failure.
def test_exit_two_without_output_names_the_exit(tmp_path):
    runner, _calls = a_runner(a_process(returncode=2))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.error == "run failed with exit 2"


# Spec AC2: a non-JSON stdout at exit 0/1 is a named error.
def test_exit_zero_without_json_is_an_invalid_report(tmp_path):
    runner, _calls = a_runner(a_process(stdout="not json"))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 0
    assert outcome.report is None
    assert outcome.error.startswith("invalid report: ")


# Spec AC2: a JSON value that is not an object is not a fan-out envelope.
def test_a_json_array_is_an_invalid_report(tmp_path):
    runner, _calls = a_runner(a_process(stdout="[1, 2]"))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 0
    assert outcome.report is None
    assert outcome.error == "invalid report: expected a JSON object"


# Spec AC2: the total timeout stops the group and keeps the named error.
def test_a_timeout_stops_the_group_and_is_a_named_error(tmp_path, monkeypatch):
    signals = a_signals(monkeypatch)
    process = a_process(timeouts=2)
    _calls, popen = a_popen(process)
    runner = CommandRunner(
        lambda bundle: ["tenon", str(bundle)],
        timeout=5.0,
        popen=popen,
        clock=a_clock(0, 0, 100),
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(None, None, "run timed out after 5.0s")
    assert signals == [(4242, signal.SIGTERM)]
    assert process.wait_calls == [5]


# Spec AC2: a cancel predicate true during the wait terminates the group.
def test_a_cancel_stops_the_group_and_marks_the_outcome(tmp_path, monkeypatch):
    signals = a_signals(monkeypatch)
    process = a_process(timeouts=1)
    _calls, popen = a_popen(process)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)], popen=popen)

    outcome = runner.run(tmp_path / "bundle.json", cancel=lambda: True)

    assert outcome == Outcome(None, None, "run cancelled", True)
    assert signals == [(4242, signal.SIGTERM)]
    assert process.communicate_calls == [0.2]


# Spec AC2: a false predicate keeps polling until the child completes.
def test_a_false_cancel_predicate_keeps_waiting(tmp_path):
    process = a_process(timeouts=2, stdout='{"command":"provider"}')
    _calls, popen = a_popen(process)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)], popen=popen)
    answers = iter([False, False])

    outcome = runner.run(tmp_path / "bundle.json", cancel=lambda: next(answers))

    assert outcome == Outcome(0, {"command": "provider"}, None)
    assert process.communicate_calls == [0.2, 0.2, 0.2]


# Spec AC2: a group that ignores SIGTERM is killed after the grace period.
def test_a_stop_escalates_to_sigkill(tmp_path, monkeypatch):
    signals = a_signals(monkeypatch)
    process = a_process(timeouts=1, waits=1)
    _calls, popen = a_popen(process)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)], popen=popen)

    outcome = runner.run(tmp_path / "bundle.json", cancel=lambda: True)

    assert outcome.cancelled is True
    assert signals == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
    assert process.wait_calls == [5, 5]


# Spec AC2: an already-dead group is not an error.
def test_a_missing_group_is_not_an_error(tmp_path, monkeypatch):
    def missing(_pid, _sig):
        raise ProcessLookupError

    monkeypatch.setattr(runner_module.os, "killpg", missing)
    process = a_process(timeouts=1)
    _calls, popen = a_popen(process)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)], popen=popen)

    outcome = runner.run(tmp_path / "bundle.json", cancel=lambda: True)

    assert outcome == Outcome(None, None, "run cancelled", True)
    assert process.wait_calls == []


# Spec AC2: a command that cannot start is a named error.
def test_an_oserror_is_a_named_error(tmp_path):
    def missing(_argv, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    runner = CommandRunner(lambda bundle: ["/missing/tenon"], popen=missing)

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit is None
    assert outcome.report is None
    assert outcome.error.startswith("cannot run /missing/tenon: ")


# Spec AC2: the error is capped with the shared tail helper.
def test_a_long_stderr_is_capped_with_tail(tmp_path):
    stderr = "\n".join(f"line {number}" for number in range(40))
    runner, _calls = a_runner(a_process(returncode=2, stderr=stderr))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.error == tail(stderr)
    assert outcome.error.splitlines()[0] == "line 20"
    assert len(outcome.error.splitlines()) == 20


# Spec AC2: the default process factory is subprocess.Popen.
def test_the_default_popen_is_subprocess_popen(tmp_path, monkeypatch):
    seen = []
    process = a_process(stdout='{"command":"provider"}')

    def fake_popen(argv, **kwargs):
        seen.append((argv, kwargs))
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)])

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(0, {"command": "provider"}, None)
    assert seen[0][1]["start_new_session"] is True
    assert seen[0][1]["shell"] is False
