import json
import re
from pathlib import Path

import pytest

from tenon.detect import RefusalCode, SpecRefusal
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


def a_refusal(text: str) -> SpecRefusal:
    with pytest.raises(SpecRefusal) as caught:
        parse_mcp(text, "<inline>")
    return caught.value


# Spec AC2: a malformed tool document is refused at its pointer.
@pytest.mark.parametrize(
    ("text", "pointer"),
    [
        ("null", "#"),
        ('"tools"', "#"),
        ("{}", "#/tools"),
        ('{"tools": {}}', "#/tools"),
        ('{"tools": [42]}', "#/tools/0"),
        ('{"tools": [{"name": ""}]}', "#/tools/0/name"),
        ('{"tools": [{"name": 7}]}', "#/tools/0/name"),
        ('{"tools": [{"inputSchema": {}}]}', "#/tools/0/name"),
        ('{"tools": [{"name": "a"}, {"name": "a"}]}', "#/tools/a"),
        ('{"tools": [{"name": "a/b"}, {"name": "a/b"}]}', "#/tools/a~1b"),
        ('{"tools": [{"name": "a", "inputSchema": []}]}', "#/tools/a/inputSchema"),
        (
            '{"tools": [{"name": "a", "outputSchema": "object"}]}',
            "#/tools/a/outputSchema",
        ),
    ],
)
def test_parse_mcp_refuses_a_malformed_document(text, pointer):
    refusal = a_refusal(text)

    assert refusal.code is RefusalCode.NOT_A_SPEC
    assert refusal.pointer == pointer
    assert "<inline>" in refusal.message


# Spec AC1/AC2: an empty tools list is a valid document.
def test_an_empty_tool_array_is_a_valid_document():
    assert parse_mcp("[]", "<inline>") == {"tools": {}}


# Spec AC3: an empty document is UNPARSEABLE.
@pytest.mark.parametrize("text", ["", " \n\t"])
def test_parse_mcp_refuses_an_empty_document(text):
    refusal = a_refusal(text)

    assert refusal.code is RefusalCode.UNPARSEABLE
    assert refusal.pointer is None


# Spec AC3: bad YAML/JSON names the line and column.
@pytest.mark.parametrize(
    "text",
    ['{"tools": [}', "tools:\n  - name: [\n", "tools:\n\t- name: x\n"],
)
def test_parse_mcp_refuses_bad_syntax_with_line_and_column(text):
    refusal = a_refusal(text)

    assert refusal.code is RefusalCode.UNPARSEABLE
    assert refusal.pointer is None
    assert re.search(r"line \d+, column \d+", refusal.message)


# Spec AC3/M1: an unreadable file is UNPARSEABLE naming the path.
def test_load_mcp_refuses_a_missing_file(tmp_path):
    missing = tmp_path / "missing.json"

    with pytest.raises(SpecRefusal) as caught:
        load_mcp(missing)

    assert caught.value.code is RefusalCode.UNPARSEABLE
    assert caught.value.pointer is None
    assert str(missing) in caught.value.message


# Spec AC3/M1: non-UTF-8 bytes are UNPARSEABLE naming the path.
def test_load_mcp_refuses_non_utf8(tmp_path):
    path = tmp_path / "latin-1.json"
    path.write_bytes(b'{"tools": [{"name": "\xff"}]}')

    with pytest.raises(SpecRefusal) as caught:
        load_mcp(path)

    assert caught.value.code is RefusalCode.UNPARSEABLE
    assert str(path) in caught.value.message
