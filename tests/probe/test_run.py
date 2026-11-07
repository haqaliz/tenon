"""The probe run: per-task verdicts from the fake server and fake agent."""

import sys
from pathlib import Path

from tenon.probe.report import CallReport, Summary
from tenon.probe.run import probe
from tenon.probe.tasks import Expectation, Task

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mcp"
SERVER = FIXTURES / "probe_server.py"
AGENT = FIXTURES / "probe_agent.py"


def a_server(*args):
    return [sys.executable, str(SERVER), *args]


def a_agent(*args):
    return [sys.executable, str(AGENT), *args]


def an_echo_task():
    return Task("echo", "Echo hello", Expectation(("echo",), "echo:hello"))


# Spec AC3: a plan that calls echo and meets its expectation passes with the
# call and its result in the report.
def test_a_task_whose_plan_and_expectation_match_passes():
    report = probe(a_server(), (an_echo_task(),), a_agent(), timeout=5)

    assert report.server.command == tuple(a_server())
    assert report.server.protocol_version == "2025-06-18"
    assert report.server.name == "fake"
    assert report.server.version == "1"
    assert [tool.name for tool in report.tools] == ["echo", "fail"]
    assert report.tools[0].description == "Echo the text back."
    [task] = report.tasks
    assert task.name == "echo"
    assert task.prompt == "Echo hello"
    assert task.agent_ok is True
    assert task.plan == ({"tool": "echo", "arguments": {"text": "hello"}},)
    assert task.calls == (
        CallReport("echo", {"text": "hello"}, True, None, "echo:hello"),
    )
    assert task.expectations.missing_tools == ()
    assert task.expectations.result_contains == "echo:hello"
    assert task.expectations.result_contains_ok is True
    assert task.ok is True
    assert task.error is None
    assert report.summary == Summary(1, 1, 0)


# Spec AC4: a tool's isError result fails the task and is recorded.
def test_a_task_calling_fail_fails_on_iserror():
    task = Task("fail", "fail now", Expectation(("fail",), None))

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    assert result.agent_ok is True
    [call] = result.calls
    assert call.tool == "fail"
    assert call.ok is False
    assert call.error is not None and call.error.startswith("isError")
    assert call.result_excerpt == "boom"
    assert result.ok is False
    assert result.error is not None and "isError" in result.error
    assert report.summary == Summary(1, 0, 1)


# Spec AC4: an expected tool that the plan never calls is missing.
def test_a_missing_expected_tool_fails_with_missing_tools():
    task = Task("missing", "missing tool", Expectation(("nope",), None))

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    assert result.calls[0].tool == "echo"
    assert result.calls[0].ok is True
    assert result.expectations.missing_tools == ("nope",)
    assert result.ok is False
    assert result.error is not None and "missing_tools" in result.error


# Spec AC4: a result substring that no call returned fails the task.
def test_a_missing_result_substring_fails():
    task = Task("echo", "Echo hello", Expectation((), "not-there"))

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    assert result.calls[0].result_excerpt == "echo:hello"
    assert result.expectations.result_contains_ok is False
    assert result.ok is False
    assert result.error is not None and "result_contains" in result.error


# Spec AC4: a failed call does not stop the later calls in the plan.
def test_later_calls_still_run_after_a_failure():
    task = Task("sequence", "sequence", None)

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    assert [call.tool for call in result.calls] == ["fail", "echo"]
    assert [call.ok for call in result.calls] == [False, True]
    assert result.calls[1].result_excerpt == "echo:hello"
    assert result.ok is False


# Spec AC4: a failed task does not stop the later tasks.
def test_a_failed_task_does_not_stop_later_tasks():
    tasks = (
        Task("fail", "fail now", None),
        an_echo_task(),
    )

    report = probe(a_server(), tasks, a_agent(), timeout=5)

    assert [result.ok for result in report.tasks] == [False, True]
    assert report.summary == Summary(2, 1, 1)


# Spec AC4: an invalid agent plan is a failed task, not a crash; later tasks run.
def test_an_invalid_agent_plan_is_a_failed_task():
    tasks = (
        Task("bad", "bad plan", None),
        an_echo_task(),
    )

    report = probe(a_server(), tasks, a_agent(), timeout=5)

    bad, echo = report.tasks
    assert bad.agent_ok is False
    assert bad.plan is None
    assert bad.calls == ()
    assert bad.ok is False
    assert bad.error is not None and bad.error.startswith("AGENT_INVALID")
    assert echo.ok is True


# Spec AC5 edge case: an empty plan with no expectation passes vacuously.
def test_an_empty_plan_without_expectations_passes():
    task = Task("empty", "empty plan", None)

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    assert result.agent_ok is True
    assert result.plan == ()
    assert result.calls == ()
    assert result.ok is True
