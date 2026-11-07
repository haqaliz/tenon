"""The probe report: what one local run observed, with no timestamps."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """The server command and the handshake's protocol/server identity."""

    command: tuple[str, ...]
    protocol_version: str
    name: str | None = None
    version: str | None = None


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


@dataclass(frozen=True, slots=True)
class ExpectationReport:
    """Which expectations were met; an empty one is vacuously met."""

    missing_tools: tuple[str, ...]
    result_contains: str | None
    result_contains_ok: bool


@dataclass(frozen=True, slots=True)
class CallReport:
    """One executed tool call and its honest outcome."""

    tool: str
    arguments: dict
    ok: bool
    error: str | None
    result_excerpt: str


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


@dataclass(frozen=True, slots=True)
class Summary:
    """The task counts for the run."""

    tasks: int
    ok: int
    failed: int


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """The whole observation: server, tools and every task's verdict."""

    server: ServerInfo
    tools: tuple[ToolInfo, ...]
    tasks: tuple[TaskReport, ...]
    summary: Summary
