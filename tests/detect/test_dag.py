"""A shared schema graph resolves once per raw node, not once per reference."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tenon.detect.ingest import load

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def distinct_nodes(document: object) -> int:
    """Count dict/list objects by identity, so shared subtrees count once."""
    seen: set[int] = set()
    stack = [document]
    while stack:
        node = stack.pop()
        if not isinstance(node, (dict, list)) or id(node) in seen:
            continue
        seen.add(id(node))
        stack.extend(node.values() if isinstance(node, dict) else node)
    return len(seen)


def test_the_thirty_level_dag_resolves_to_a_linear_number_of_nodes():
    document = load(FIXTURES / "dag-old.yaml")

    assert distinct_nodes(document) < 100


def test_two_refs_to_the_same_schema_are_one_object():
    document = load(FIXTURES / "dag-old.yaml")

    properties = document["components"]["schemas"]["L0"]["properties"]
    assert properties["a"] is properties["b"]


@pytest.mark.xfail(
    strict=True,
    reason="aspect 2 replaces canonical hashing; json.dumps expands a DAG",
)
def test_diffing_the_dag_reports_the_deep_change_once():
    # Out of process so the current exponential hash fails instead of hanging
    # the suite; aspect 2 makes the in-process diff linear.
    script = textwrap.dedent(
        f"""
        from tenon.detect import ChangeKind, diff
        from tenon.detect.ingest import load

        old = load({str(FIXTURES / "dag-old.yaml")!r})
        new = load({str(FIXTURES / "dag-new.yaml")!r})
        changes = [
            change
            for change in diff(old, new).changes
            if change.kind is ChangeKind.PROPERTY_TYPE_CHANGED
        ]
        print(len(changes), changes[0].location.pointer if changes else "")
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )

    assert completed.stdout.strip() == "1 #/components/schemas/L30/properties"
