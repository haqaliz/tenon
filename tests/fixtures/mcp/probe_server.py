#!/usr/bin/env python3
"""A fake MCP stdio server for the probe tests: newline JSON-RPC, no network."""

import argparse
import json
import sys
import time

ECHO = {
    "name": "echo",
    "description": "Echo the text back.",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
}
FAIL = {
    "name": "fail",
    "description": "Always returns an isError result.",
    "inputSchema": {"type": "object", "properties": {}},
}

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
NOT_INITIALIZED = -32000


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def send_error(request_id, code, message):
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def answer_server_request(pending_id):
    """Ask the client an unknown method and require its -32601 reply."""
    send(
        {
            "jsonrpc": "2.0",
            "id": "server-1",
            "method": "probe/unknown",
            "params": {},
        }
    )
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict) or message.get("id") != "server-1":
            continue
        error = message.get("error") or {}
        if error.get("code") == METHOD_NOT_FOUND:
            return True
        send_error(pending_id, NOT_INITIALIZED, "client did not answer -32601")
        return False
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-version", default="2025-06-18")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--malformed", action="store_true")
    parser.add_argument("--wrong-id", action="store_true")
    parser.add_argument("--exit-after-first", action="store_true")
    parser.add_argument("--ask-client", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args(argv)

    sys.stderr.write("fake server starting\n")
    sys.stderr.flush()
    if args.silent:
        time.sleep(30)
        return 0

    initialized = False
    first = True
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        request_id = message.get("id")
        if method is None:
            continue  # a response to a server request we already handled
        if first:
            first = False
            if args.exit_after_first:
                return 0
            if args.malformed:
                sys.stdout.write("not json " + "x" * 5000 + "\n")
                sys.stdout.flush()
                return 0

        if method == "notifications/initialized":
            initialized = True
            continue

        if method == "initialize":
            params = message.get("params") or {}
            client = params.get("clientInfo") or {}
            if (
                params.get("protocolVersion") != "2025-06-18"
                or params.get("capabilities") != {}
                or client.get("name") != "tenon"
                or not client.get("version")
            ):
                send_error(request_id, INVALID_PARAMS, "bad initialize params")
                continue
            if args.notify:
                send(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/message",
                        "params": {"level": "info"},
                    }
                )
            response_id = request_id
            if args.wrong_id and isinstance(request_id, int):
                response_id = request_id + 1
            send(
                {
                    "jsonrpc": "2.0",
                    "id": response_id,
                    "result": {
                        "protocolVersion": args.protocol_version,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake", "version": "1"},
                    },
                }
            )
            continue

        if method == "tools/list":
            if not initialized:
                send_error(
                    request_id, NOT_INITIALIZED, "notifications/initialized missing"
                )
                continue
            if args.ask_client and not answer_server_request(request_id):
                continue
            cursor = (message.get("params") or {}).get("cursor")
            if cursor is None:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": [ECHO], "nextCursor": "p2"},
                    }
                )
            elif cursor == "p2":
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": [FAIL]},
                    }
                )
            else:
                send_error(request_id, INVALID_PARAMS, f"unknown cursor: {cursor!r}")
            continue

        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name == "echo":
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": "echo:" + str(arguments.get("text", "")),
                        }
                    ],
                    "isError": False,
                }
            elif name == "fail":
                result = {
                    "content": [{"type": "text", "text": "boom"}],
                    "isError": True,
                }
            else:
                send_error(request_id, INVALID_PARAMS, f"unknown tool: {name}")
                continue
            send({"jsonrpc": "2.0", "id": request_id, "result": result})
            continue

        send_error(request_id, METHOD_NOT_FOUND, f"unknown method: {method}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
