"""The probe agent contract: one JSON request in, a validated plan out."""

import json
import sys
import time
from pathlib import Path

import pytest

from tenon.probe.agent import AgentError, PlanCall, run_agent

AGENT = Path(__file__).parent.parent / "fixtures" / "mcp" / "probe_agent.py"

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
        },
    },
    {
        "name": "fail",
        "description": "Always returns an isError result.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def a_agent(*args):
    return [sys.executable, str(AGENT), *args]


def a_request(task="Echo hello", tools=None):
    return {"task": task, "tools": TOOLS if tools is None else tools}


# Spec AC2: a valid plan becomes the typed calls in order.
def test_a_valid_plan_is_returned():
    calls = run_agent(a_agent(), a_request("Echo hello"), timeout=5)

    assert calls == (PlanCall("echo", {"text": "hello"}),)


# Spec AC2: the request carries the task and every tool with its schema.
def test_the_request_carries_the_task_and_tool_schemas(tmp_path):
    capture = tmp_path / "request.json"

    run_agent(a_agent("--capture", str(capture)), a_request("Echo it"), timeout=5)

    request = json.loads(capture.read_text(encoding="utf-8"))
    assert request["task"] == "Echo it"
    assert request["tools"] == TOOLS


# Spec AC2: a plan may be empty; the run is still valid.
def test_an_empty_plan_is_valid():
    assert run_agent(a_agent(), a_request("empty"), timeout=5) == ()


# Spec AC2: a non-zero exit is a named agent failure with a capped detail.
def test_a_non_zero_exit_is_an_agent_error():
    with pytest.raises(AgentError) as caught:
        run_agent(a_agent("--exit-code", "3"), a_request(), timeout=5)

    assert caught.value.reason == "AGENT_EXIT"
    assert "3" in caught.value.detail
    assert len(caught.value.detail) <= 2000


# Spec AC2: invalid JSON is AGENT_INVALID, never a traceback.
@pytest.mark.parametrize("args", [("--malformed",), ()])
def test_invalid_json_is_agent_invalid(args):
    request = a_request("bad") if not args else a_request()

    with pytest.raises(AgentError) as caught:
        run_agent(a_agent(*args), request, timeout=5)

    assert caught.value.reason == "AGENT_INVALID"
    assert len(caught.value.detail) <= 2000


@pytest.mark.parametrize(
    "flag, named",
    [
        ("--no-calls", "calls"),
        ("--calls-not-list", "calls"),
        ("--bad-tool", "tool"),
        ("--bad-arguments", "arguments"),
    ],
)
# Spec AC2: a missing/non-list calls or a bad call shape is AGENT_INVALID.
def test_a_bad_plan_shape_is_agent_invalid(flag, named):
    with pytest.raises(AgentError) as caught:
        run_agent(a_agent(flag), a_request(), timeout=5)

    assert caught.value.reason == "AGENT_INVALID"
    assert named in caught.value.detail


# Spec AC2: a silent agent times out and is killed; nothing hangs.
def test_a_timeout_is_a_named_agent_failure():
    started = time.monotonic()

    with pytest.raises(AgentError) as caught:
        run_agent(a_agent("--silent"), a_request(), timeout=0.2)

    assert caught.value.reason == "AGENT_TIMEOUT"
    assert time.monotonic() - started < 5


# Spec AC2: an unreachable agent command is a spawn failure, not a traceback.
def test_a_command_that_cannot_spawn_is_an_agent_error():
    with pytest.raises(AgentError) as caught:
        run_agent(["/tenon-no-such-agent-xyz"], a_request(), timeout=5)

    assert caught.value.reason == "AGENT_SPAWN_FAILED"
    assert "tenon-no-such-agent-xyz" in caught.value.detail


def test_a_string_command_is_rejected():
    with pytest.raises(ValueError):
        run_agent(f"{sys.executable} {AGENT}", a_request(), timeout=5)


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        run_agent(a_agent(), a_request(), timeout=timeout)
