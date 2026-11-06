"""The MCP locate surface: change policy over the scan evidence."""

from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location, diff_mcp
from tenon.locate.mcp_config import McpLocateConfig
from tenon.locate.mcp_locate import locate_mcp
from tenon.locate.mcp_scan import McpScan
from tenon.locate.result import (
    AmbiguityReason,
    LocateReason,
    Site,
    SiteShape,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
MCP_BASIC = FIXTURES / "mcp-basic"
MCP_ALIAS = FIXTURES / "mcp-alias"
MCP_DECOY = FIXTURES / "mcp-decoy"
MCP_DYNAMIC = FIXTURES / "mcp-dynamic"
PROPERTIES = "#/tools/create_charge/inputSchema/properties"


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


def a_payload(name, type_="integer", fmt=None):
    return {"type": type_, "format": fmt, "name": name}


def a_line(repo, path, line):
    return (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]


def a_site(repo, path, line, column, shape, symbol):
    return Site(path, line, column, shape, symbol, a_line(repo, path, line))


def a_group(result, reason):
    [group] = [group for group in result.ambiguous if group.reason is reason]
    return group


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


# Phase 2: certain calls and field keys.
# Spec AC2: a rooted async-with call is a certain call site at the method name.
def test_a_rooted_tool_call_is_certain():
    change = a_change()

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_BASIC, "client.py", 6, 23, SiteShape.CALL, "call_tool"),
    )
    assert result.ambiguous == ()
    assert result.reason is None
    assert result.change is change


# Spec AC2: an added tool locates the same rooted call.
def test_an_added_tool_call_is_certain():
    result = locate_mcp(
        a_change(ChangeKind.ENDPOINT_ADDED), MCP_BASIC, McpLocateConfig()
    )

    assert [(site.line, site.shape) for site in result.certain] == [
        (6, SiteShape.CALL)
    ]


# Spec AC2: an endpoint change matches only the changed tool.
def test_an_endpoint_change_matches_only_the_named_tool():
    result = locate_mcp(a_change(), MCP_BASIC, McpLocateConfig())

    assert [(site.line, site.symbol) for site in result.certain] == [
        (6, "call_tool")
    ]
    assert result.ambiguous == ()


# Spec AC3: a removed field is certain exactly at the rooted dict key.
def test_a_removed_field_returns_the_rooted_dict_key():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, pointer=PROPERTIES, before=a_payload("amount")
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_BASIC, "client.py", 6, 61, SiteShape.DICT_KEY, "amount"),
    )
    assert all(site.shape is not SiteShape.CALL for site in result.certain)
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC3: a renamed field uses the before name, the spelling in the code.
def test_a_renamed_field_uses_the_before_name():
    change = a_change(
        ChangeKind.RENAMED,
        pointer=PROPERTIES,
        before="amount",
        after="amount_cents",
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert [(site.column, site.shape, site.symbol) for site in result.certain] == [
        (61, SiteShape.DICT_KEY, "amount")
    ]


# Spec AC3: a type change locates the key, not the call.
def test_a_type_changed_field_returns_the_rooted_key():
    change = a_change(
        ChangeKind.PROPERTY_TYPE_CHANGED,
        pointer=PROPERTIES,
        before=a_payload("amount", "integer"),
        after=a_payload("amount", "string"),
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert [(site.shape, site.symbol) for site in result.certain] == [
        (SiteShape.DICT_KEY, "amount")
    ]


# Spec AC3: a narrowed enum uses the name carried by the payload.
def test_an_enum_narrowed_field_returns_the_rooted_key():
    change = a_change(
        ChangeKind.ENUM_NARROWED,
        pointer=PROPERTIES,
        before={"enum": ["usd", "eur"], "name": "currency"},
        after={"enum": ["usd"], "name": "currency"},
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_BASIC, "client.py", 6, 79, SiteShape.DICT_KEY, "currency"),
    )


# Spec AC3: a required-added field that is present is just its key.
def test_a_required_added_field_with_the_key_returns_the_key():
    change = a_change(
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        pointer=PROPERTIES,
        after=a_payload("amount"),
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert [(site.shape, site.symbol) for site in result.certain] == [
        (SiteShape.DICT_KEY, "amount")
    ]


# Spec AC3: a required-added field with no key says "add it at the call".
def test_a_required_added_field_absent_returns_the_call_sites():
    change = a_change(
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        pointer=PROPERTIES,
        after=a_payload("path", "string"),
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_BASIC, "client.py", 6, 23, SiteShape.CALL, "call_tool"),
    )


# Spec AC3: a dict(...) argument is a certain keyword site.
def test_a_dict_call_keyword_is_certain():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, pointer=PROPERTIES, before=a_payload("amount")
    )

    result = locate_mcp(change, MCP_DYNAMIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_DYNAMIC, "app.py", 8, 55, SiteShape.KEYWORD, "amount"),
        a_site(MCP_DYNAMIC, "app.py", 12, 24, SiteShape.DICT_KEY, "amount"),
    )
    assert result.reason is None


# Phase 3: ambiguity, reasons and output.
# Spec AC4: a variable tool name is a DYNAMIC_GETATTR group holding the call.
def test_a_dynamic_tool_call_is_dynamic_getattr():
    result = locate_mcp(
        a_change(tool="other_tool", pointer="#/tools/other_tool"),
        MCP_DYNAMIC,
        McpLocateConfig(),
    )

    assert result.certain == ()
    assert result.reason is None
    group = a_group(result, AmbiguityReason.DYNAMIC_GETATTR)
    assert group.symbol == "other_tool"
    assert group.candidates == (
        a_site(MCP_DYNAMIC, "app.py", 6, 23, SiteShape.CALL, "call_tool"),
    )


# Spec AC4: a variable or ** payload is DYNAMIC_KWARGS with the rooted calls.
def test_a_variable_or_star_payload_is_dynamic_kwargs():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, pointer=PROPERTIES, before=a_payload("amount")
    )

    result = locate_mcp(change, MCP_DYNAMIC, McpLocateConfig())

    group = a_group(result, AmbiguityReason.DYNAMIC_KWARGS)
    assert group.symbol == "amount"
    assert group.candidates == (
        a_site(MCP_DYNAMIC, "app.py", 7, 23, SiteShape.CALL, "call_tool"),
        a_site(MCP_DYNAMIC, "app.py", 8, 23, SiteShape.CALL, "call_tool"),
        a_site(MCP_DYNAMIC, "app.py", 9, 23, SiteShape.CALL, "call_tool"),
        a_site(MCP_DYNAMIC, "app.py", 10, 23, SiteShape.CALL, "call_tool"),
        a_site(MCP_DYNAMIC, "app.py", 14, 23, SiteShape.CALL, "call_tool"),
    )
    assert result.reason is None


# Spec AC4: an unrooted call is a group with the call and its candidate key.
def test_an_unrooted_matching_call_is_an_unrooted_receiver():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, pointer=PROPERTIES, before=a_payload("amount")
    )

    result = locate_mcp(change, MCP_DECOY, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_DECOY, "app.py", 12, 51, SiteShape.DICT_KEY, "amount"),
    )
    group = a_group(result, AmbiguityReason.UNROOTED_RECEIVER)
    assert group.symbol == "amount"
    assert group.candidates == (
        a_site(MCP_DECOY, "app.py", 10, 19, SiteShape.CALL, "call_tool"),
        a_site(MCP_DECOY, "app.py", 10, 47, SiteShape.DICT_KEY, "amount"),
    )
    assert result.reason is None


# Spec AC4: an unrooted endpoint call is only a candidate.
def test_an_unrooted_endpoint_call_is_a_candidate_only():
    result = locate_mcp(a_change(), MCP_DECOY, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_DECOY, "app.py", 12, 23, SiteShape.CALL, "call_tool"),
    )
    group = a_group(result, AmbiguityReason.UNROOTED_RECEIVER)
    assert group.symbol == "create_charge"
    assert group.candidates == (
        a_site(MCP_DECOY, "app.py", 10, 19, SiteShape.CALL, "call_tool"),
    )


# Spec AC4: a second-hop alias is ALIAS_CHAIN, never an unrooted receiver.
def test_a_second_hop_alias_is_an_alias_chain():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, pointer=PROPERTIES, before=a_payload("amount")
    )

    result = locate_mcp(change, MCP_ALIAS, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_ALIAS, "app.py", 6, 47, SiteShape.DICT_KEY, "amount"),
        a_site(MCP_ALIAS, "app.py", 7, 62, SiteShape.DICT_KEY, "amount"),
    )
    group = a_group(result, AmbiguityReason.ALIAS_CHAIN)
    assert group.symbol == "amount"
    assert group.candidates == (
        a_site(MCP_ALIAS, "app.py", 9, 17, SiteShape.CALL, "call_tool"),
        a_site(MCP_ALIAS, "app.py", 9, 45, SiteShape.DICT_KEY, "amount"),
    )
    assert all(
        group.reason is not AmbiguityReason.UNROOTED_RECEIVER
        for group in result.ambiguous
    )


# Spec AC5: a repository with no client import is named, not empty.
def test_a_repository_without_the_client_package_has_no_import(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")

    result = locate_mcp(a_change(), tmp_path, McpLocateConfig())

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC5: a tool nobody calls is NO_SITES.
def test_a_change_with_no_matching_tool_is_no_sites():
    result = locate_mcp(
        a_change(tool="delete_everything", pointer="#/tools/delete_everything"),
        MCP_BASIC,
        McpLocateConfig(),
    )

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC5: a schema-level kind is not this locator's.
def test_a_schema_kind_is_unsupported():
    change = a_change(
        ChangeKind.SCHEMA_ADDED, pointer="#/tools/create_charge/inputSchema"
    )

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND


def a_output_document(receipt_type):
    return {
        "tools": {
            "create_charge": {
                "name": "create_charge",
                "inputSchema": {
                    "type": "object",
                    "properties": {"amount": {"type": "integer"}},
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {"receipt": {"type": receipt_type}},
                },
            }
        }
    }


# Spec AC6: an output-schema property change stops at the call site.
def test_an_output_schema_property_change_returns_the_call_site_only():
    [change] = diff_mcp(
        a_output_document("string"), a_output_document("integer")
    ).changes
    assert "/outputSchema" in change.location.pointer

    result = locate_mcp(change, MCP_BASIC, McpLocateConfig())

    assert result.certain == (
        a_site(MCP_BASIC, "client.py", 6, 23, SiteShape.CALL, "call_tool"),
    )
    assert all(site.shape is SiteShape.CALL for site in result.certain)
    assert result.ambiguous == ()
    assert result.reason is None
