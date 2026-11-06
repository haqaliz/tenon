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
# Phase 3: call_tool, tool name and argument keys.
# Phase 4: dynamics, columns, determinism.
