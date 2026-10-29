"""One check: launch, exit codes, timeouts, capped tails and input validation."""

import sys
import time

import pytest

from tenon.prove.run import run_check


def check(command, cwd, kind="baseline", timeout=5.0):
    return run_check(command, cwd, kind, timeout)


# Spec AC7 / PRD M7: a green command is recorded with the tuple that ran.
def test_a_zero_exit_command_is_recorded_as_green(tmp_path):
    result = check([sys.executable, "-c", "print('ok')"], tmp_path)

    assert result.kind == "baseline"
    assert result.command == (sys.executable, "-c", "print('ok')")
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stdout_tail == "ok"
    assert result.stderr_tail == ""


# Spec AC3: the after kind is echoed, and a non-zero code is kept.
def test_a_non_zero_exit_keeps_its_code_and_kind(tmp_path):
    result = check([sys.executable, "-c", "raise SystemExit(3)"], tmp_path, "after")

    assert result.kind == "after"
    assert result.returncode == 3
    assert result.timed_out is False


# Spec AC9: a missing executable is an ordinary failed check, never an exception.
def test_a_missing_executable_returns_127_naming_it(tmp_path):
    result = check(["tenon-no-such-command-xyz"], tmp_path)

    assert result.returncode == 127
    assert result.timed_out is False
    assert "tenon-no-such-command-xyz" in result.stderr_tail


# Spec AC7: a timeout has no return code, and the call does not wait for the child.
def test_a_timeout_kills_the_child_and_has_no_return_code(tmp_path):
    started = time.monotonic()

    result = check(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout=0.2
    )

    assert time.monotonic() - started < 2.0
    assert result.timed_out is True
    assert result.returncode is None


# PRD S1: only the last 20 stdout lines survive.
def test_stdout_tail_keeps_the_last_twenty_lines(tmp_path):
    script = "\n".join(f"print('line {number}')" for number in range(30))

    result = check([sys.executable, "-c", script], tmp_path)

    assert result.stdout_tail.splitlines() == [
        f"line {number}" for number in range(10, 30)
    ]


# PRD S1: the same cap applies to stderr.
def test_stderr_tail_keeps_the_last_twenty_lines(tmp_path):
    script = "\n".join(
        f"print('line {number}', file=sys.stderr)" for number in range(30)
    )

    result = check([sys.executable, "-c", f"import sys; {script}"], tmp_path)

    assert result.stderr_tail.splitlines() == [
        f"line {number}" for number in range(10, 30)
    ]


def test_stdout_and_stderr_are_recorded_separately(tmp_path):
    script = "import sys; print('out'); print('err', file=sys.stderr)"

    result = check([sys.executable, "-c", script], tmp_path)

    assert result.stdout_tail == "out"
    assert result.stderr_tail == "err"


# PRD M10: the caller's environment is inherited unchanged.
def test_the_callers_environment_reaches_the_check(tmp_path, monkeypatch):
    monkeypatch.setenv("TENON_PROVE_CHECK", "visible")

    result = check(
        [sys.executable, "-c", "import os; print(os.environ['TENON_PROVE_CHECK'])"],
        tmp_path,
    )

    assert result.stdout_tail == "visible"


# PRD M3: the command runs with cwd set to the copy.
def test_the_check_runs_in_the_given_directory(tmp_path):
    (tmp_path / "marker.txt").write_text("here", encoding="utf-8")

    result = check([sys.executable, "-c", "print(open('marker.txt').read())"], tmp_path)

    assert result.stdout_tail == "here"


# PRD M10: a string command would imply a shell; it is rejected.
def test_a_string_command_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        check("python -m pytest", tmp_path)


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_raises_value_error(tmp_path, timeout):
    with pytest.raises(ValueError):
        check([sys.executable, "-c", "pass"], tmp_path, timeout=timeout)
