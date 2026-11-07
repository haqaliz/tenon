"""Probe tasks: a typed task file with named validation errors."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Expectation:
    """What a passing task must show: tools called and a result substring."""

    tools: tuple[str, ...]
    result_contains: str | None = None


@dataclass(frozen=True, slots=True)
class Task:
    """One probe task: a prompt for the agent and an optional expectation."""

    name: str
    prompt: str
    expect: Expectation | None = None


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _expectation(task: dict, name: str) -> Expectation | None:
    if "expect" not in task:
        return None
    raw = task["expect"]
    if not isinstance(raw, dict):
        raise ValueError(f"task {name!r}: expect must be an object")
    tools = raw.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError(f"task {name!r}: expect.tools must be a list")
    for index, tool in enumerate(tools):
        if not _non_empty(tool):
            raise ValueError(
                f"task {name!r}: expect.tools[{index}] must be a non-empty string"
            )
    result_contains = raw.get("result_contains")
    if "result_contains" in raw and not _non_empty(result_contains):
        raise ValueError(
            f"task {name!r}: expect.result_contains must be a non-empty string"
        )
    return Expectation(tuple(tools), result_contains)


def load_tasks(path: str | Path) -> tuple[Task, ...]:
    """Read ``{"tasks": [...]}``; every malformed shape names its task and key."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"tasks: invalid JSON: {exc.msg}") from None
    if not isinstance(payload, dict):
        raise ValueError("tasks: the file must be an object with a 'tasks' list")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("tasks: must be a list")
    tasks: list[Task] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_tasks):
        if not isinstance(raw, dict):
            raise ValueError(f"task {index}: must be an object")
        name = raw.get("name")
        if not _non_empty(name):
            raise ValueError(f"task {index}: name must be a non-empty string")
        if name in names:
            raise ValueError(f"task {name!r}: duplicate name")
        names.add(name)
        prompt = raw.get("prompt")
        if not _non_empty(prompt):
            raise ValueError(f"task {name!r}: prompt must be a non-empty string")
        tasks.append(Task(name, prompt, _expectation(raw, name)))
    return tuple(tasks)
