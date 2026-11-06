import json
from pathlib import Path

from tenon.detect.mcp_ingest import load_mcp, parse_mcp

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mcp"


# Spec AC1: the tools/list envelope normalizes to a name-keyed mapping.
def test_load_mcp_loads_the_envelope_fixture():
    document = load_mcp(FIXTURES / "tools-v1.json")

    assert set(document) == {"tools"}
    assert set(document["tools"]) == {"read_file", "list_files"}
    assert document["tools"]["read_file"]["inputSchema"]["properties"]["path"] == {
        "type": "string"
    }


# Spec AC1: a bare array is the same document without the envelope.
def test_load_mcp_loads_the_bare_array_fixture():
    envelope = load_mcp(FIXTURES / "tools-v1.json")
    array = load_mcp(FIXTURES / "tools-array.json")

    assert array == envelope


# Spec AC1: JSON and YAML both parse.
def test_parse_mcp_loads_yaml():
    document = parse_mcp(
        "tools:\n"
        "  - name: ping\n"
        "    inputSchema: {type: object}\n"
        "nextCursor: page-2\n",
        "<inline>",
    )

    assert document == {
        "tools": {"ping": {"name": "ping", "inputSchema": {"type": "object"}}}
    }


# Spec AC1: nextCursor and unknown envelope keys are ignored.
def test_parse_mcp_ignores_next_cursor_and_extra_keys():
    document = parse_mcp(
        '{"tools": [{"name": "ping"}], "nextCursor": "abc", '
        '"serverInfo": {"name": "x"}}',
        "<inline>",
    )

    assert document == {"tools": {"ping": {"name": "ping"}}}


# Spec AC1: inputSchema, outputSchema and other tool keys survive normalization.
def test_parse_mcp_keeps_the_tool_object():
    tool = {
        "name": "ping",
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True},
    }

    document = parse_mcp(json.dumps({"tools": [tool]}), "<inline>")

    assert document["tools"]["ping"] == tool


# Spec AC5: reordering the tools does not change the normalized document.
def test_parse_mcp_is_stable_across_tool_order():
    first = parse_mcp(
        json.dumps({"tools": [{"name": "a"}, {"name": "b"}]}), "<inline>"
    )
    second = parse_mcp(
        json.dumps({"tools": [{"name": "b"}, {"name": "a"}]}), "<inline>"
    )

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# Spec AC5: load_mcp equals parse_mcp on the same bytes.
def test_load_mcp_matches_parse_mcp_on_the_same_bytes():
    source = str(FIXTURES / "tools-v1.json")
    text = (FIXTURES / "tools-v1.json").read_text(encoding="utf-8")

    assert load_mcp(FIXTURES / "tools-v1.json") == parse_mcp(text, source)
