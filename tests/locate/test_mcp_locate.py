"""The MCP locate surface: change policy over the scan evidence."""

from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate.mcp_config import McpLocateConfig
from tenon.locate.mcp_locate import locate_mcp
from tenon.locate.mcp_scan import McpScan
from tenon.locate.result import LocateReason

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
MCP_BASIC = FIXTURES / "mcp-basic"
MCP_ALIAS = FIXTURES / "mcp-alias"
MCP_DECOY = FIXTURES / "mcp-decoy"
MCP_DYNAMIC = FIXTURES / "mcp-dynamic"


def a_change(
    kind=ChangeKind.ENDPOINT_REMOVED,
    *,
    tool="create_charge",
    pointer="#/tools/create_charge",
    method="tool",
    before=None,
    after=None,
):
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=tool),
        before=before,
        after=after,
    )


# Phase 1: the config and the tool gate.
# Spec AC1: the client package defaults to mcp.
def test_config_defaults_to_the_mcp_client_package():
    assert McpLocateConfig().client_package == "mcp"


# Spec AC1: a submodule of the client package is a valid package.
def test_config_accepts_a_submodule_package():
    config = McpLocateConfig(client_package="mcp.client")

    assert config.client_package == "mcp.client"


# Spec AC1: empty, whitespace and path-like names are refused.
@pytest.mark.parametrize(
    "name", ["", " ", "mcp/client", ".mcp", "mcp.", "mcp..client", "mcp client"]
)
def test_config_rejects_a_non_package_name(name):
    with pytest.raises(ValueError):
        McpLocateConfig(client_package=name)


# Spec AC5: a change that is not a tool is unsupported before the scan.
def test_a_non_tool_change_is_unsupported(monkeypatch):
    import tenon.locate.mcp_locate as mcp_locate_module

    monkeypatch.setattr(
        mcp_locate_module, "scan_mcp", lambda *args: pytest.fail("must not scan")
    )
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        tool="/v1/charges",
        pointer="#/paths",
        method="operation",
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC5: a tool change with no path is unsupported.
def test_a_tool_change_without_a_path_is_unsupported():
    change = a_change(tool="", pointer="#/tools")

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND


# Spec AC5: a tool change runs the scan with the configured package.
def test_a_tool_change_scans_the_repository(monkeypatch):
    import tenon.locate.mcp_locate as mcp_locate_module

    calls = []

    def a_scan(root, package):
        calls.append((root, package))
        return McpScan()

    monkeypatch.setattr(mcp_locate_module, "scan_mcp", a_scan)

    result = locate_mcp(
        a_change(), MCP_BASIC, McpLocateConfig(client_package="mcp.client")
    )

    assert calls == [(MCP_BASIC, "mcp.client")]
    assert result.reason is LocateReason.NO_SDK_IMPORT
