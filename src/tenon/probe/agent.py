"""The probe agent contract: one JSON request on stdin, one plan on stdout."""

import json
import subprocess
from dataclasses import dataclass
from typing import Sequence

from tenon.prove import tail

AGENT_SPAWN_FAILED = "AGENT_SPAWN_FAILED"
AGENT_EXIT = "AGENT_EXIT"
AGENT_INVALID = "AGENT_INVALID"
AGENT_TIMEOUT = "AGENT_TIMEOUT"


class AgentError(Exception):
    """One agent failure: a stable reason and a capped detail."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = tail(detail)
        text = f"{reason}: {self.detail}" if self.detail else reason
        super().__init__(text)


@dataclass(frozen=True, slots=True)
class PlanCall:
    """One tool call the agent planned."""

    tool: str
    arguments: dict


def _invalid(detail: str) -> AgentError:
    return AgentError(AGENT_INVALID, detail)


def _plan(stdout: str) -> tuple[PlanCall, ...]:
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise _invalid(f"invalid JSON: {exc.msg}: {stdout.strip()}") from None
    if not isinstance(response, dict):
        raise _invalid("the response must be an object")
    raw_calls = response.get("calls")
    if not isinstance(raw_calls, list):
        raise _invalid("the response has no 'calls' list")
    calls: list[PlanCall] = []
    for index, raw in enumerate(raw_calls):
        if not isinstance(raw, dict):
            raise _invalid(f"calls[{index}]: must be an object")
        tool = raw.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            raise _invalid(f"calls[{index}]: tool must be a non-empty string")
        arguments = raw.get("arguments")
        if not isinstance(arguments, dict):
            raise _invalid(f"calls[{index}]: arguments must be an object")
        calls.append(PlanCall(tool, dict(arguments)))
    return tuple(calls)


def run_agent(
    command: Sequence[str], request: dict, timeout: float
) -> tuple[PlanCall, ...]:
    """Run the user's agent once and validate the plan it writes to stdout."""
    if isinstance(command, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    command = list(command)
    if not command:
        raise AgentError(AGENT_SPAWN_FAILED, "the command is empty")
    payload = json.dumps(request, separators=(",", ":"), ensure_ascii=False) + "\n"
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise AgentError(AGENT_SPAWN_FAILED, f"{command[0]!r}: {exc}") from exc
    try:
        stdout, stderr = process.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        detail = f"no plan within {timeout}s"
        if stderr.strip():
            detail = f"{detail}: {stderr}"
        raise AgentError(AGENT_TIMEOUT, detail) from None
    if process.returncode != 0:
        code = process.returncode
        detail = f"the agent exited with code {code}"
        if stderr.strip():
            detail = f"{detail}: {stderr}"
        raise AgentError(AGENT_EXIT, detail)
    return _plan(stdout)
