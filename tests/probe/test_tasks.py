"""Probe task files: a typed view and named validation errors."""

import json
from pathlib import Path

import pytest

from tenon.probe.tasks import Expectation, Task, load_tasks

TASKS = Path(__file__).parent.parent / "fixtures" / "mcp" / "probe_tasks.json"


def a_tasks_file(tmp_path, payload):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def a_valid_task(name="echo", prompt="Echo hello", expect=None):
    task = {"name": name, "prompt": prompt}
    if expect is not None:
        task["expect"] = expect
    return task


# Spec AC1: the fixture loads into the typed tasks with their expectations.
def test_load_tasks_reads_the_fixture():
    tasks = load_tasks(TASKS)

    assert [task.name for task in tasks] == ["echo", "fail"]
    assert tasks[0] == Task("echo", "Echo hello", Expectation(("echo",), "echo:hello"))
    assert tasks[1] == Task("fail", "Use the fail tool", Expectation(("fail",), None))


# Spec AC1: expect is optional; an empty task list is valid.
def test_a_task_without_expect_loads_and_an_empty_list_is_valid(tmp_path):
    path = a_tasks_file(tmp_path, {"tasks": [a_valid_task()]})

    assert load_tasks(path) == (Task("echo", "Echo hello", None),)
    assert load_tasks(a_tasks_file(tmp_path, {"tasks": []})) == ()


# Spec AC1: a non-list tasks value is a ValueError naming the key.
def test_a_non_list_tasks_value_is_rejected(tmp_path):
    path = a_tasks_file(tmp_path, {"tasks": {}})

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "tasks" in str(caught.value)
    assert "list" in str(caught.value)


# Spec AC1: duplicate names are rejected, naming the task.
def test_duplicate_task_names_are_rejected(tmp_path):
    path = a_tasks_file(
        tmp_path, {"tasks": [a_valid_task(), a_valid_task(prompt="again")]}
    )

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "echo" in str(caught.value)
    assert "duplicate" in str(caught.value)


@pytest.mark.parametrize(
    "task, named",
    [
        ({"prompt": "go"}, "name"),
        ({"name": "  ", "prompt": "go"}, "name"),
        ({"name": "echo"}, "prompt"),
        ({"name": "echo", "prompt": "  "}, "prompt"),
    ],
)
# Spec AC1: missing or blank name/prompt is a ValueError naming the field.
def test_missing_or_blank_fields_are_rejected(tmp_path, task, named):
    path = a_tasks_file(tmp_path, {"tasks": [task]})

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert named in str(caught.value)


# Spec AC1: a non-object expect is rejected, naming the task and key.
def test_a_non_object_expect_is_rejected(tmp_path):
    path = a_tasks_file(
        tmp_path, {"tasks": [a_valid_task(expect=["echo"])]}
    )

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "echo" in str(caught.value)
    assert "expect" in str(caught.value)


# Spec AC1: a non-list tools value is rejected, naming the key.
def test_a_non_list_expect_tools_is_rejected(tmp_path):
    path = a_tasks_file(
        tmp_path, {"tasks": [a_valid_task(expect={"tools": "echo"})]}
    )

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "echo" in str(caught.value)
    assert "expect.tools" in str(caught.value)


@pytest.mark.parametrize("tools", [["echo", 3], ["echo", "  "]])
# Spec AC1: every expected tool is a non-empty string.
def test_a_bad_expect_tool_is_rejected(tmp_path, tools):
    path = a_tasks_file(tmp_path, {"tasks": [a_valid_task(expect={"tools": tools})]})

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "expect.tools" in str(caught.value)


@pytest.mark.parametrize("value", [3, None, "", "  "])
# Spec AC1: result_contains is a non-empty string when present.
def test_a_bad_result_contains_is_rejected(tmp_path, value):
    path = a_tasks_file(
        tmp_path, {"tasks": [a_valid_task(expect={"result_contains": value})]}
    )

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "echo" in str(caught.value)
    assert "result_contains" in str(caught.value)


# Spec AC1: a task that is not an object is rejected by index.
def test_a_non_object_task_is_rejected(tmp_path):
    path = a_tasks_file(tmp_path, {"tasks": ["echo"]})

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "task 0" in str(caught.value)


# Spec AC1: malformed JSON is a ValueError, not a traceback.
def test_malformed_json_is_a_value_error(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        load_tasks(path)

    assert "tasks" in str(caught.value)
