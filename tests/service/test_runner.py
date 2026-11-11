import json
import subprocess
from dataclasses import FrozenInstanceError

import pytest

from tenon.prove import tail
from tenon.service.runner import CommandRunner, Outcome


def a_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        ["tenon"], returncode, stdout, stderr
    )


def a_recording_runner(result):
    """One fake subprocess.run that records the argv and its kwargs."""
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return result

    return calls, runner


def a_runner(result):
    calls, runner = a_recording_runner(result)
    builder = lambda bundle: ["tenon", "provider", "migrate", str(bundle)]  # noqa: E731
    return CommandRunner(builder, runner=runner), calls


# Spec AC1/AC4: Outcome is a frozen value with the exit, report and error.
def test_outcome_is_a_frozen_value():
    outcome = Outcome(exit=0, report={"summary": {}}, error=None)

    assert outcome.exit == 0
    assert outcome.report == {"summary": {}}
    assert outcome.error is None
    with pytest.raises(FrozenInstanceError):
        outcome.exit = 1


# Spec AC4: the builder receives the bundle and the child runs without a shell.
def test_run_builds_the_argv_from_the_bundle(tmp_path):
    bundle = tmp_path / "bundle.json"
    runner, calls = a_runner(a_completed(stdout='{"command":"provider"}'))

    outcome = runner.run(bundle)

    (argv, kwargs), = calls
    assert argv == ["tenon", "provider", "migrate", str(bundle)]
    assert kwargs == {
        "capture_output": True,
        "text": True,
        "shell": False,
        "timeout": 3600,
    }
    assert outcome == Outcome(0, {"command": "provider"}, None)


# Spec AC4: an exit 0 fan-out envelope is a completed run with its report.
def test_exit_zero_with_a_json_report_is_a_completed_run(tmp_path):
    report = {"command": "provider", "summary": {"repos": 2, "passed": 2}}
    runner, _calls = a_runner(a_completed(stdout=json.dumps(report)))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(0, report, None)


# Spec AC4: exit 1 with a JSON envelope keeps the report and the exit.
def test_exit_one_with_a_json_report_is_a_completed_run(tmp_path):
    runner, _calls = a_runner(
        a_completed(returncode=1, stdout='{"summary":{"repos":1,"failed":1}}')
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 1
    assert outcome.report == {"summary": {"repos": 1, "failed": 1}}
    assert outcome.error is None


# Spec AC4: exit 2 is a run error carrying the capped stderr.
def test_exit_two_uses_the_stderr_as_the_error(tmp_path):
    runner, _calls = a_runner(
        a_completed(returncode=2, stdout='{"ignored":true}', stderr="boom\n")
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 2
    assert outcome.report is None
    assert outcome.error == "boom"


# Spec AC4: the CLI writes --json errors to stdout; use that message before stderr.
def test_exit_two_uses_the_json_error_message(tmp_path):
    stdout = '{"error":{"kind":"usage","message":"--api-token is required"}}'
    runner, _calls = a_runner(a_completed(returncode=2, stdout=stdout))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 2
    assert outcome.report is None
    assert outcome.error == "--api-token is required"


# Spec AC4: an exit with no output still names the failure.
def test_exit_two_without_output_names_the_exit(tmp_path):
    runner, _calls = a_runner(a_completed(returncode=2))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.error == "run failed with exit 2"


# Spec AC4: a non-JSON stdout at exit 0/1 is a named error.
def test_exit_zero_without_json_is_an_invalid_report(tmp_path):
    runner, _calls = a_runner(a_completed(stdout="not json"))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 0
    assert outcome.report is None
    assert outcome.error.startswith("invalid report: ")


# Spec AC4: a JSON value that is not an object is not a fan-out envelope.
def test_a_json_array_is_an_invalid_report(tmp_path):
    runner, _calls = a_runner(a_completed(stdout="[1, 2]"))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit == 0
    assert outcome.report is None
    assert outcome.error == "invalid report: expected a JSON object"


# Spec AC4: a timeout is a named error with no exit.
def test_a_timeout_is_a_named_error(tmp_path):
    def timeout(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, 5)

    runner = CommandRunner(
        lambda bundle: ["tenon", str(bundle)], timeout=5.0, runner=timeout
    )

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(None, None, "run timed out after 5.0s")


# Spec AC4: a command that cannot start is a named error.
def test_an_oserror_is_a_named_error(tmp_path):
    def missing(argv, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    runner = CommandRunner(lambda bundle: ["/missing/tenon"], runner=missing)

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.exit is None
    assert outcome.report is None
    assert outcome.error.startswith("cannot run /missing/tenon: ")


# Spec AC4: the error is capped with the shared tail helper.
def test_a_long_stderr_is_capped_with_tail(tmp_path):
    stderr = "\n".join(f"line {number}" for number in range(40))
    runner, _calls = a_runner(a_completed(returncode=2, stderr=stderr))

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome.error == tail(stderr)
    assert outcome.error.splitlines()[0] == "line 20"
    assert len(outcome.error.splitlines()) == 20


# Spec AC4: the default runner is subprocess.run with the exact call shape.
def test_the_default_runner_is_subprocess_run(tmp_path, monkeypatch):
    seen = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return a_completed(stdout='{"command":"provider"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = CommandRunner(lambda bundle: ["tenon", str(bundle)])

    outcome = runner.run(tmp_path / "bundle.json")

    assert outcome == Outcome(0, {"command": "provider"}, None)
    assert seen[0][1]["shell"] is False
    assert seen[0][1]["timeout"] == 3600
