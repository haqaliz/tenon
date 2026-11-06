"""Evidence scan for MCP client tool calls over committed fixtures."""

from pathlib import Path

import pytest

from tenon.locate import SiteShape
from tenon.locate.mcp_scan import (
    McpDynamic,
    McpHit,
    McpScan,
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
# Phase 4: dynamics, columns, determinism.
