"""The probe report: what one local run observed, with no timestamps."""

import json
from dataclasses import dataclass

MAX_DESCRIPTION = 500
MAX_EXCERPT = 500


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """The server command and the handshake's protocol/server identity."""

    command: tuple[str, ...]
    protocol_version: str
    name: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "command": list(self.command),
            "protocol_version": self.protocol_version,
            "name": self.name,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ToolInfo:
    """One tool as the server listed it."""

    name: str
    description: str
    input_schema: dict

    @classmethod
    def from_tool(cls, tool: dict) -> "ToolInfo":
        name = tool.get("name")
        description = tool.get("description")
        schema = tool.get("inputSchema")
        return cls(
            name=name if isinstance(name, str) else "",
            description=description if isinstance(description, str) else "",
            input_schema=schema if isinstance(schema, dict) else {},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description[:MAX_DESCRIPTION],
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True, slots=True)
class ExpectationReport:
    """Which expectations were met; an empty one is vacuously met."""

    missing_tools: tuple[str, ...]
    result_contains: str | None
    result_contains_ok: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "missing_tools": list(self.missing_tools),
            "result_contains": self.result_contains,
            "result_contains_ok": self.result_contains_ok,
        }


@dataclass(frozen=True, slots=True)
class CallReport:
    """One executed tool call and its honest outcome."""

    tool: str
    arguments: dict
    ok: bool
    error: str | None
    result_excerpt: str

    def to_dict(self) -> dict[str, object]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "ok": self.ok,
            "error": self.error,
            "result_excerpt": self.result_excerpt,
        }


@dataclass(frozen=True, slots=True)
class TaskReport:
    """One task's plan, calls, expectation results and final verdict."""

    name: str
    prompt: str
    agent_ok: bool
    plan: tuple[dict[str, object], ...] | None
    calls: tuple[CallReport, ...]
    expectations: ExpectationReport
    ok: bool
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "prompt": self.prompt,
            "agent_ok": self.agent_ok,
            "plan": None if self.plan is None else list(self.plan),
            "calls": [call.to_dict() for call in self.calls],
            "expectations": self.expectations.to_dict(),
            "ok": self.ok,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class Summary:
    """The task counts for the run."""

    tasks: int
    ok: int
    failed: int

    def to_dict(self) -> dict[str, object]:
        return {"tasks": self.tasks, "ok": self.ok, "failed": self.failed}


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """The whole observation: server, tools and every task's verdict."""

    server: ServerInfo
    tools: tuple[ToolInfo, ...]
    tasks: tuple[TaskReport, ...]
    summary: Summary

    def to_dict(self) -> dict[str, object]:
        return {
            "server": self.server.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "tasks": [task.to_dict() for task in self.tasks],
            "summary": self.summary.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def render_text(self) -> str:
        return render_text(self)


def _count(count: int, singular: str) -> str:
    return f"{count} {singular if count == 1 else singular + 's'}"


def _task_detail(task: TaskReport) -> str:
    failure = next((call for call in task.calls if not call.ok), None)
    if failure is not None:
        return f"{failure.tool}: {failure.error or failure.result_excerpt or 'failed'}"
    if task.error is not None:
        return task.error
    if task.calls and task.calls[-1].result_excerpt:
        return task.calls[-1].result_excerpt
    return "ok"


def render_text(report: ProbeReport) -> str:
    """One line per task, then the tool count and the task counts."""
    lines = [
        f"{'PASS' if task.ok else 'FAIL'} {task.name}: {_task_detail(task)}"
        for task in report.tasks
    ]
    lines.append(
        f"summary: {_count(len(report.tools), 'tool')}, "
        f"{_count(report.summary.tasks, 'task')}, "
        f"{report.summary.ok} passed, {report.summary.failed} failed"
    )
    return "\n".join(lines) + "\n"
