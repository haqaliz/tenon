"""Run every probe task against one MCP session and evaluate expectations."""

from typing import Sequence

from tenon.probe.agent import AGENT_SPAWN_FAILED, AgentError, PlanCall, run_agent
from tenon.probe.client import McpStdioClient, ProbeError
from tenon.probe.report import (
    CallReport,
    ExpectationReport,
    ProbeReport,
    ServerInfo,
    Summary,
    TaskReport,
    ToolInfo,
)
from tenon.probe.tasks import Task

__all__ = ["probe"]


def _optional_text(info: dict, key: str) -> str | None:
    value = info.get(key)
    return value if isinstance(value, str) else None


def _request_tools(tools: Sequence[ToolInfo]) -> list[dict[str, object]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        for tool in tools
    ]


def _result_text(result: dict) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        entry["text"]
        for entry in content
        if isinstance(entry, dict)
        and entry.get("type") == "text"
        and isinstance(entry.get("text"), str)
    ]
    return "\n".join(parts)


def _error_text(error: ProbeError | AgentError) -> str:
    return f"{error.reason}: {error.detail}" if error.detail else error.reason


def _call_report(client: McpStdioClient, call: PlanCall) -> CallReport:
    try:
        result = client.call_tool(call.tool, call.arguments)
    except ProbeError as exc:
        return CallReport(call.tool, call.arguments, False, _error_text(exc), "")
    excerpt = _result_text(result)
    if result.get("isError") is True:
        detail = f"isError: {excerpt}" if excerpt else "isError"
        return CallReport(call.tool, call.arguments, False, detail, excerpt)
    return CallReport(call.tool, call.arguments, True, None, excerpt)


def _agent_failed(task: Task, error: AgentError) -> TaskReport:
    return TaskReport(
        name=task.name,
        prompt=task.prompt,
        agent_ok=False,
        plan=None,
        calls=(),
        expectations=ExpectationReport((), None, True),
        ok=False,
        error=_error_text(error),
    )


def _task_report(
    client: McpStdioClient,
    task: Task,
    tools: Sequence[ToolInfo],
    agent_cmd: Sequence[str],
    timeout: float,
) -> TaskReport:
    request = {"task": task.prompt, "tools": _request_tools(tools)}
    try:
        planned = run_agent(agent_cmd, request, timeout)
    except AgentError as exc:
        if exc.reason == AGENT_SPAWN_FAILED:
            raise
        return _agent_failed(task, exc)

    plan = tuple({"tool": call.tool, "arguments": call.arguments} for call in planned)
    calls = tuple(_call_report(client, call) for call in planned)
    expected = task.expect
    called = {call.tool for call in planned}
    missing = (
        ()
        if expected is None
        else tuple(tool for tool in expected.tools if tool not in called)
    )
    needle = None if expected is None else expected.result_contains
    contains_ok = needle is None or any(needle in call.result_excerpt for call in calls)
    failures = [call for call in calls if not call.ok]
    error: str | None = None
    if failures:
        error = failures[0].error or "call_failed"
    elif missing:
        error = "missing_tools: " + ", ".join(missing)
    elif not contains_ok:
        error = f"result_contains: {needle!r}"
    return TaskReport(
        name=task.name,
        prompt=task.prompt,
        agent_ok=True,
        plan=plan,
        calls=calls,
        expectations=ExpectationReport(missing, needle, contains_ok),
        ok=not failures and not missing and contains_ok,
        error=error,
    )


def probe(
    server_cmd: Sequence[str],
    tasks: Sequence[Task],
    agent_cmd: Sequence[str],
    timeout: float,
) -> ProbeReport:
    """Connect once, run every task, and report exactly what happened."""
    client = McpStdioClient()
    reports: tuple[TaskReport, ...] = ()
    try:
        client.start(server_cmd, timeout)
        client.initialize()
        tools = tuple(ToolInfo.from_tool(tool) for tool in client.list_tools())
        server = ServerInfo(
            command=tuple(server_cmd),
            protocol_version=client.protocol_version,
            name=_optional_text(client.server_info, "name"),
            version=_optional_text(client.server_info, "version"),
        )
        reports = tuple(
            _task_report(client, task, tools, agent_cmd, timeout) for task in tasks
        )
    finally:
        client.close()
    summary = Summary(
        tasks=len(reports),
        ok=sum(1 for report in reports if report.ok),
        failed=sum(1 for report in reports if not report.ok),
    )
    return ProbeReport(server, tools, reports, summary)
