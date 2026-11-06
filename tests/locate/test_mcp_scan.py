"""Evidence scan for MCP client tool calls over committed fixtures."""

from pathlib import Path

from tenon.locate import SiteShape
from tenon.locate.mcp_scan import (
    McpDynamic,
    McpHit,
    scan_mcp,
)
from tenon.locate.scan import DynamicKind

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
MCP_BASIC = FIXTURES / "mcp-basic"
MCP_ALIAS = FIXTURES / "mcp-alias"
MCP_DECOY = FIXTURES / "mcp-decoy"
MCP_DYNAMIC = FIXTURES / "mcp-dynamic"


def a_line(repo, path, line):
    return (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]


def a_hit(repo, path, line, column, shape, symbol, tool, rooted):
    return McpHit(
        path, line, column, shape, symbol, tool, rooted, a_line(repo, path, line)
    )


def a_call_hits(result):
    return [hit for hit in result.hits if hit.symbol == "call_tool"]


# Phase 1: evidence and reachability.
# Spec AC1: a file importing the client package is scanned.
def test_a_file_importing_the_client_package_is_scanned():
    result = scan_mcp(MCP_BASIC, "mcp")

    assert result.modules == ("client.py", "helper.py")


# Spec AC1: a transitive local importer is scanned.
def test_a_transitive_local_importer_is_scanned():
    result = scan_mcp(MCP_BASIC, "mcp")

    assert "helper.py" in result.modules


# Spec AC1: an unrelated file is not scanned.
def test_an_unrelated_file_is_not_scanned():
    result = scan_mcp(MCP_BASIC, "mcp")

    assert "unrelated.py" not in result.modules
    assert all(hit.path != "unrelated.py" for hit in result.hits)


# Spec AC1: no import -> empty modules.
def test_a_repository_without_the_import_has_no_modules(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")

    result = scan_mcp(tmp_path, "mcp")

    assert result.modules == ()
    assert result.hits == ()
    assert result.dynamics == ()


def test_a_syntax_error_skips_the_file_and_keeps_the_scan():
    result = scan_mcp(MCP_BASIC, "mcp")

    assert "broken.py" not in result.modules
    assert "client.py" in result.modules


def test_a_submodule_client_package_is_honored():
    result = scan_mcp(MCP_ALIAS, "mcp.client")

    assert result.modules == ("app.py",)


# Phase 2: client rooting.
# Spec AC2: async with ClientSession(...) as session is rooted.
def test_an_async_with_session_is_rooted():
    result = scan_mcp(MCP_BASIC, "mcp")

    [async_call] = [hit for hit in a_call_hits(result) if hit.line == 6]

    assert async_call.rooted is True


# Spec AC2: plain with ClientSession(...) as session is rooted.
def test_a_plain_with_session_is_rooted():
    result = scan_mcp(MCP_BASIC, "mcp")

    [sync_call] = [hit for hit in a_call_hits(result) if hit.line == 11]

    assert sync_call.rooted is True


# Spec AC2: a one-hop constructor alias is rooted.
def test_a_constructor_alias_is_rooted():
    result = scan_mcp(MCP_ALIAS, "mcp")

    rooted = {hit.line: hit.rooted for hit in a_call_hits(result)}

    assert rooted[6] is True
    assert rooted[7] is True


def test_a_package_qualified_constructor_is_rooted(tmp_path):
    (tmp_path / "app.py").write_text(
        "import mcp\n"
        "\n"
        "async def run():\n"
        "    session = mcp.ClientSession(None, None)\n"
        '    await session.call_tool("create_charge", {"amount": 1})\n',
        encoding="utf-8",
    )

    result = scan_mcp(tmp_path, "mcp")

    [call] = a_call_hits(result)
    assert call.rooted is True


# Spec AC2: a direct ClientSession(...).call_tool(...) receiver is rooted.
def test_a_direct_constructor_receiver_is_rooted(tmp_path):
    (tmp_path / "app.py").write_text(
        "from mcp import ClientSession\n"
        "\n"
        "async def run():\n"
        '    await ClientSession(None, None).call_tool("create_charge", {"amount": 1})\n',
        encoding="utf-8",
    )

    result = scan_mcp(tmp_path, "mcp")

    [call] = a_call_hits(result)
    assert call.rooted is True


# Spec AC2: a parameter receiver is unrooted; the rooted call stays rooted.
def test_a_parameter_receiver_is_unrooted():
    result = scan_mcp(MCP_DECOY, "mcp")

    assert [(hit.line, hit.rooted) for hit in a_call_hits(result)] == [
        (10, False),
        (12, True),
    ]


# Spec AC2: a second hop is an alias chain, and the hop receiver is unrooted.
def test_a_second_hop_alias_is_an_alias_chain():
    result = scan_mcp(MCP_ALIAS, "mcp")

    assert result.dynamics == (
        McpDynamic("app.py", 8, 5, DynamicKind.ALIAS_CHAIN, None, "other"),
    )
    [chained] = [hit for hit in a_call_hits(result) if hit.line == 9]
    assert chained.rooted is False


# Phase 3: call_tool, tool name and argument keys.
# Spec AC3/AC4: the exact call, literal tool and dict keys at the quote.
def test_the_async_with_call_carries_the_literal_tool_and_dict_keys():
    result = scan_mcp(MCP_BASIC, "mcp")

    assert result.hits == (
        a_hit(MCP_BASIC, "client.py", 6, 23, SiteShape.CALL, "call_tool", "create_charge", True),
        a_hit(MCP_BASIC, "client.py", 6, 61, SiteShape.DICT_KEY, "amount", "create_charge", True),
        a_hit(MCP_BASIC, "client.py", 6, 79, SiteShape.DICT_KEY, "currency", "create_charge", True),
        a_hit(MCP_BASIC, "client.py", 11, 17, SiteShape.CALL, "call_tool", "other_tool", True),
        a_hit(MCP_BASIC, "client.py", 11, 42, SiteShape.DICT_KEY, "amount", "other_tool", True),
    )
    assert result.hits[0].line_text == (
        '        await session.call_tool("create_charge", arguments='
        '{"amount": amount, "currency": "usd"})'
    )


# Spec AC3/AC4: name= supplies the tool; a second positional dict is the arguments.
def test_a_name_keyword_and_a_second_positional_dict_are_recorded():
    result = scan_mcp(MCP_ALIAS, "mcp")

    assert result.hits == (
        a_hit(MCP_ALIAS, "app.py", 6, 19, SiteShape.CALL, "call_tool", "create_charge", True),
        a_hit(MCP_ALIAS, "app.py", 6, 47, SiteShape.DICT_KEY, "amount", "create_charge", True),
        a_hit(MCP_ALIAS, "app.py", 7, 19, SiteShape.CALL, "call_tool", "create_charge", True),
        a_hit(MCP_ALIAS, "app.py", 7, 62, SiteShape.DICT_KEY, "amount", "create_charge", True),
        a_hit(MCP_ALIAS, "app.py", 9, 17, SiteShape.CALL, "call_tool", "create_charge", False),
        a_hit(MCP_ALIAS, "app.py", 9, 45, SiteShape.DICT_KEY, "amount", "create_charge", False),
    )


# Spec AC3: a variable tool name is a GETATTR dynamic, not a literal.
def test_a_variable_tool_name_is_a_getattr_dynamic():
    result = scan_mcp(MCP_DYNAMIC, "mcp")

    [call] = [hit for hit in a_call_hits(result) if hit.line == 6]

    assert call.tool is None
    assert McpDynamic("app.py", 6, 23, DynamicKind.GETATTR, None, "call_tool") in (
        result.dynamics
    )


# Spec AC4: dict(...) emits keyword hits at the argument name.
def test_a_dict_call_emits_keyword_hits():
    result = scan_mcp(MCP_DYNAMIC, "mcp")

    assert (
        a_hit(MCP_DYNAMIC, "app.py", 8, 55, SiteShape.KEYWORD, "amount", "create_charge", True)
        in result.hits
    )


# Spec AC4: a nested object under a key is not walked.
def test_a_nested_object_key_is_not_walked():
    result = scan_mcp(MCP_DYNAMIC, "mcp")

    keys = [
        (hit.line, hit.symbol, hit.column)
        for hit in result.hits
        if hit.shape is SiteShape.DICT_KEY
    ]

    assert keys == [(6, "amount", 40), (12, "amount", 24), (12, "currency", 49)]
    assert all(hit.symbol != "nested" for hit in result.hits)


# Phase 4: dynamics, columns, determinism.
# Spec AC4: a variable payload, **payload and a dict unpack are STAR_KWARGS with the tool.
def test_a_variable_or_star_payload_is_a_star_kwargs_dynamic():
    result = scan_mcp(MCP_DYNAMIC, "mcp")

    assert result.dynamics == (
        McpDynamic("app.py", 6, 23, DynamicKind.GETATTR, None, "call_tool"),
        McpDynamic("app.py", 7, 50, DynamicKind.STAR_KWARGS, "create_charge"),
        McpDynamic("app.py", 9, 50, DynamicKind.STAR_KWARGS, "create_charge"),
        McpDynamic("app.py", 14, 63, DynamicKind.STAR_KWARGS, "create_charge"),
    )


# Spec AC5: columns are characters, not UTF-8 bytes.
def test_columns_are_characters_not_utf8_bytes(tmp_path):
    (tmp_path / "app.py").write_text(
        "from mcp import ClientSession\n"
        "\n"
        "async def run(read, write):\n"
        "    session = ClientSession(read, write)\n"
        '    "héllo"; await session.call_tool("create_charge", '
        '{"héllo": 1, "amount": 2})\n',
        encoding="utf-8",
    )

    result = scan_mcp(tmp_path, "mcp")

    line = a_line(tmp_path, "app.py", 5)
    call = a_call_hits(result)[0]
    [amount] = [hit for hit in result.hits if hit.symbol == "amount"]
    assert call.column == line.index("call_tool") + 1
    assert call.column != len(line[: line.index("call_tool")].encode("utf-8")) + 1
    assert amount.column == line.index('"amount"') + 1
    assert amount.line_text == line


# Spec AC5: canonical order.
def test_hits_and_dynamics_are_canonically_ordered():
    result = scan_mcp(MCP_DYNAMIC, "mcp")

    assert result.hits == tuple(
        sorted(result.hits, key=lambda hit: (hit.path, hit.line, hit.column))
    )
    assert result.dynamics == tuple(
        sorted(result.dynamics, key=lambda dynamic: (dynamic.path, dynamic.line, dynamic.column))
    )


# Spec AC5: two scans are identical.
def test_two_scans_are_identical():
    assert scan_mcp(MCP_BASIC, "mcp") == scan_mcp(MCP_BASIC, "mcp")


# Spec AC5: the scan never modifies the tree.
def test_scan_never_modifies_the_scanned_tree():
    def snapshot():
        return {
            path.relative_to(MCP_BASIC).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in MCP_BASIC.rglob("*")
            if path.is_file()
        }

    before = snapshot()

    scan_mcp(MCP_BASIC, "mcp")

    assert snapshot() == before
