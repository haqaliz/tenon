"""The probe run: per-task verdicts from the fake server and fake agent."""

import json
import sys
from pathlib import Path

import pytest

import tenon.probe.run as run_module
from tenon.probe.client import ProbeError
from tenon.probe.report import CallReport, Summary, ToolInfo
from tenon.probe.run import probe
from tenon.probe.tasks import Expectation, Task

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mcp"
SERVER = FIXTURES / "probe_server.py"
AGENT = FIXTURES / "probe_agent.py"


def a_server(*args):
    return [sys.executable, str(SERVER), *args]


def a_agent(*args):
    return [sys.executable, str(AGENT), *args]


def a_echo_task():
    return Task("echo", "Echo hello", Expectation(("echo",), "echo:hello"))


# Spec AC3: a plan that calls echo and meets its expectation passes with the
# call and its result in the report.
def test_a_task_whose_plan_and_expectation_match_passes():
    report = probe(a_server(), (a_echo_task(),), a_agent(), timeout=5)

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
        a_echo_task(),
    )

    report = probe(a_server(), tasks, a_agent(), timeout=5)

    assert [result.ok for result in report.tasks] == [False, True]
    assert report.summary == Summary(2, 1, 1)


# Spec AC4: an invalid agent plan is a failed task, not a crash; later tasks run.
def test_an_invalid_agent_plan_is_a_failed_task():
    tasks = (
        Task("bad", "bad plan", None),
        a_echo_task(),
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


# Spec AC7: the JSON has the exact shape of the observation.
def test_the_json_has_the_exact_shape(tmp_path):
    capture = tmp_path / "request.json"
    report = probe(
        a_server(), (a_echo_task(),), a_agent("--capture", str(capture)), timeout=5
    )

    assert report.to_dict() == {
        "server": {
            "command": a_server(),
            "protocol_version": "2025-06-18",
            "name": "fake",
            "version": "1",
        },
        "tools": [
            {
                "name": "echo",
                "description": "Echo the text back.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            },
            {
                "name": "fail",
                "description": "Always returns an isError result.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ],
        "tasks": [
            {
                "name": "echo",
                "prompt": "Echo hello",
                "agent_ok": True,
                "plan": [{"tool": "echo", "arguments": {"text": "hello"}}],
                "calls": [
                    {
                        "tool": "echo",
                        "arguments": {"text": "hello"},
                        "ok": True,
                        "error": None,
                        "result_excerpt": "echo:hello",
                    }
                ],
                "expectations": {
                    "missing_tools": [],
                    "result_contains": "echo:hello",
                    "result_contains_ok": True,
                },
                "ok": True,
                "error": None,
            }
        ],
        "summary": {"tasks": 1, "ok": 1, "failed": 0},
    }
    assert str(capture) not in report.to_json()


# Spec AC7: the same observations produce byte-identical JSON.
def test_the_json_is_byte_stable_for_the_same_observations():
    first = probe(a_server(), (a_echo_task(),), a_agent(), timeout=5)
    second = probe(a_server(), (a_echo_task(),), a_agent(), timeout=5)

    assert first.to_json() == second.to_json()
    assert first.to_json() == json.dumps(
        first.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert "timestamp" not in first.to_json()
    assert "duration" not in first.to_json()


# Spec AC7: text is one line per task plus a summary with the tool count.
def test_the_text_is_one_line_per_task_plus_the_summary():
    report = probe(a_server(), (a_echo_task(),), a_agent(), timeout=5)

    assert report.render_text().splitlines() == [
        "PASS echo: echo:hello",
        "summary: 2 tools, 1 task, 1 passed, 0 failed",
    ]
    from tenon.probe.report import render_text

    assert render_text(report) == report.render_text()


# Spec AC7: a failed task's line names the call that failed.
def test_the_text_names_a_failed_call():
    task = Task("fail", "fail now", None)

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    assert report.render_text().splitlines() == [
        "FAIL fail: fail: isError: boom",
        "summary: 2 tools, 1 task, 0 passed, 1 failed",
    ]


# Spec AC5: an empty task list is valid and the summary is zero.
def test_an_empty_task_list_reports_zero():
    report = probe(a_server(), (), a_agent(), timeout=5)

    assert report.tasks == ()
    assert report.summary == Summary(0, 0, 0)
    assert report.to_dict()["summary"] == {"tasks": 0, "ok": 0, "failed": 0}
    assert report.render_text() == "summary: 2 tools, 0 tasks, 0 passed, 0 failed\n"


# Spec AC6: a connection/handshake failure is a ProbeError before any task.
@pytest.mark.parametrize(
    "server, reason",
    [(("--exit-after-first",), "server_exit"), (("--silent",), "timeout")],
)
def test_a_failed_handshake_is_a_probe_error_before_tasks(tmp_path, server, reason):
    capture = tmp_path / "request.json"
    command = a_server(*server)

    with pytest.raises(ProbeError) as caught:
        probe(
            command,
            (a_echo_task(),),
            a_agent("--capture", str(capture)),
            timeout=0.2,
        )

    assert caught.value.reason == reason
    assert not capture.exists()


# Spec AC6: an unreachable server command is a ProbeError, not a traceback.
def test_a_server_that_cannot_spawn_is_a_probe_error():
    with pytest.raises(ProbeError) as caught:
        probe(["/tenon-no-such-server-xyz"], (a_echo_task(),), a_agent(), timeout=5)

    assert caught.value.reason == "spawn_failed"


def a_recording_client(monkeypatch):
    made = []
    real = run_module.McpStdioClient

    class Recording(real):
        def __init__(self):
            super().__init__()
            self.closed = False
            made.append(self)

        def close(self):
            self.closed = True
            super().close()

    monkeypatch.setattr(run_module, "McpStdioClient", Recording)
    return made


# Spec AC8: the server is closed after a successful run.
def test_the_server_is_closed_on_success(monkeypatch):
    made = a_recording_client(monkeypatch)

    probe(a_server(), (a_echo_task(),), a_agent(), timeout=5)

    assert made and made[0].closed is True


# Spec AC8: the server is closed when the handshake fails before any task.
def test_the_server_is_closed_when_the_handshake_fails(monkeypatch):
    made = a_recording_client(monkeypatch)

    with pytest.raises(ProbeError):
        probe(a_server("--exit-after-first"), (a_echo_task(),), a_agent(), timeout=5)

    assert made and made[0].closed is True


# Spec AC7: descriptions and result excerpts are capped.
def test_descriptions_and_excerpts_are_capped():
    from tenon.probe.report import MAX_DESCRIPTION, MAX_EXCERPT

    tool = ToolInfo.from_tool(
        {"name": "echo", "description": "d" * 5000, "inputSchema": {}}
    )
    assert len(tool.to_dict()["description"]) == MAX_DESCRIPTION
    report = probe(
        a_server(), (Task("long", "long echo", None),), a_agent(), timeout=5
    )
    assert len(report.tasks[0].calls[0].result_excerpt) == MAX_EXCERPT


# Spec AC7/package: the public surface is exported from tenon.probe.
def test_the_package_exports_the_probe_surface():
    import tenon.probe as package

    for name in (
        "probe",
        "load_tasks",
        "ProbeError",
        "AgentError",
        "Task",
        "Expectation",
        "ServerInfo",
        "ToolInfo",
        "ExpectationReport",
        "CallReport",
        "TaskReport",
        "Summary",
        "ProbeReport",
    ):
        assert hasattr(package, name), name


# Spec AC2: every task's agent request carries the prompt and the server tools.
def test_the_agent_request_carries_the_task_and_tools(tmp_path):
    capture = tmp_path / "request.json"

    probe(
        a_server(), (a_echo_task(),), a_agent("--capture", str(capture)), timeout=5
    )

    request = json.loads(capture.read_text(encoding="utf-8"))
    assert request["task"] == "Echo hello"
    assert [tool["name"] for tool in request["tools"]] == ["echo", "fail"]
    assert request["tools"][0]["inputSchema"] == {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }


# Spec AC4: a call the server rejects is a failed call with its named reason;
# the later calls in the plan still run.
def test_a_probe_error_from_a_call_is_recorded_and_later_calls_run():
    task = Task("unknown", "unknown tool", None)

    report = probe(a_server(), (task,), a_agent(), timeout=5)

    [result] = report.tasks
    [rejected, echo] = result.calls
    assert rejected.tool == "nope"
    assert rejected.ok is False
    assert rejected.error.startswith("server_error:")
    assert "unknown tool: nope" in rejected.error
    assert echo.ok is True
    assert result.ok is False


# Spec AC4: an agent timeout is a failed task, not a fatal error.
def test_a_timed_out_agent_is_a_failed_task():
    report = probe(
        a_server(), (a_echo_task(),), a_agent("--silent"), timeout=0.2
    )

    [result] = report.tasks
    assert result.agent_ok is False
    assert result.error is not None and result.error.startswith("AGENT_TIMEOUT")
    assert report.summary == Summary(1, 0, 1)


# Spec AC6/PRD M7: an agent that cannot spawn is fatal, and the server closes.
def test_an_agent_that_cannot_spawn_is_an_agent_error(monkeypatch):
    from tenon.probe.agent import AgentError

    made = a_recording_client(monkeypatch)

    with pytest.raises(AgentError) as caught:
        probe(
            a_server(),
            (a_echo_task(),),
            ["/tenon-no-such-agent-xyz"],
            timeout=5,
        )

    assert caught.value.reason == "AGENT_SPAWN_FAILED"
    assert made and made[0].closed is True
