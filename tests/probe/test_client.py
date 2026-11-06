"""The MCP stdio client: handshake, tools, calls and named connection errors."""

import sys
from pathlib import Path

import pytest

from tenon.probe import McpStdioClient, ProbeError

SERVER = Path(__file__).parent.parent / "fixtures" / "mcp" / "probe_server.py"


def a_server(*args):
    return [sys.executable, str(SERVER), *args]


@pytest.fixture
def client():
    client = McpStdioClient()
    yield client
    client.close()


# Spec AC1: the fake server starts; initialize carries the required fields and
# returns its protocol version and server info.
def test_initialize_returns_the_handshake_and_keeps_the_server_info(client):
    client.start(a_server(), timeout=5)

    result = client.initialize()

    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"] == {"name": "fake", "version": "1"}
    assert client.protocol_version == "2025-06-18"
    assert client.server_info == {"name": "fake", "version": "1"}


# Spec AC1: the server's returned protocol version wins over the requested one.
def test_initialize_accepts_the_servers_protocol_version(client):
    client.start(a_server("--protocol-version", "2024-11-05"), timeout=5)

    client.initialize()

    assert client.protocol_version == "2024-11-05"


# Spec AC1: notifications/initialized is sent before the first tools/list.
def test_initialize_sends_initialized_before_tools_list(client):
    client.start(a_server(), timeout=5)
    client.initialize()

    # The fake server answers tools/list only after notifications/initialized.
    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["echo", "fail"]


# Spec AC2: list_tools follows nextCursor and returns every page's tools.
def test_list_tools_follows_the_cursor_across_pages(client):
    client.start(a_server(), timeout=5)
    client.initialize()

    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["echo", "fail"]
    assert tools[0]["description"] == "Echo the text back."
    assert tools[0]["inputSchema"] == {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }
    assert tools[1]["description"] == "Always returns an isError result."


# Spec AC1: a server notification before the response is ignored.
def test_a_server_notification_is_ignored_during_a_request(client):
    client.start(a_server("--notify"), timeout=5)

    result = client.initialize()

    assert result["protocolVersion"] == "2025-06-18"


# Spec AC6: close stops the process and keeps a capped stderr tail.
def test_close_stops_the_server_and_captures_the_stderr_tail(client):
    client.start(a_server(), timeout=5)
    client.initialize()
    process = client._process

    client.close()

    assert process.poll() is not None
    assert "fake server starting" in client.stderr_tail
    assert len(client.stderr_tail) <= 2000


# Spec AC4: an unreachable command is a spawn failure, not a traceback.
def test_a_command_that_cannot_spawn_raises_probe_error(client):
    with pytest.raises(ProbeError) as caught:
        client.start(["/tenon-no-such-server-xyz"], timeout=5)

    assert caught.value.reason == "spawn_failed"
    assert "tenon-no-such-server-xyz" in caught.value.detail


# Spec AC4: an empty command is a spawn failure, not an IndexError.
def test_an_empty_command_is_a_spawn_failure(client):
    with pytest.raises(ProbeError) as caught:
        client.start([], timeout=5)

    assert caught.value.reason == "spawn_failed"


# Spec AC4: a request after close is a closed pipe, not a hang.
def test_a_request_after_close_is_a_closed_pipe(client):
    client.start(a_server(), timeout=5)
    client.initialize()
    client.close()

    with pytest.raises(ProbeError) as caught:
        client.initialize()

    assert caught.value.reason == "closed_pipe"


def test_a_string_command_is_rejected(client):
    with pytest.raises(ValueError):
        client.start(f"{sys.executable} {SERVER}", timeout=5)


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_is_rejected(client, timeout):
    with pytest.raises(ValueError):
        client.start(a_server(), timeout=timeout)
