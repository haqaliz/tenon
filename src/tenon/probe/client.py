"""A small MCP client: newline-delimited JSON-RPC over a child process's stdio."""

import json
import queue
import subprocess
import threading
from collections import deque
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence

from tenon.prove import tail

SPAWN_FAILED = "spawn_failed"
CLOSED_PIPE = "closed_pipe"
TIMEOUT = "timeout"
INVALID_JSON = "invalid_json"
PROTOCOL_ERROR = "protocol_error"
SERVER_EXIT = "server_exit"
SERVER_ERROR = "server_error"

PROTOCOL_VERSION = "2025-06-18"


def _package_version() -> str:
    """The installed distribution version, or a fixed fallback."""
    try:
        return version("tenonhq") or "0.0.0"
    except PackageNotFoundError:
        return "0.0.0"


def _error_detail(error: object) -> str:
    """A JSON-RPC error as ``code: message`` for the capped detail."""
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message") or ""
        return f"{code}: {message}" if code is not None else str(message)
    return str(error)


class ProbeError(Exception):
    """One probe connection failure: a stable reason and a capped detail."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = tail(detail)
        text = f"{reason}: {self.detail}" if self.detail else reason
        super().__init__(text)


class McpStdioClient:
    """One MCP server over newline JSON-RPC on its stdin and stdout."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._timeout = 0.0
        self._next_id = 0
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: deque[str] = deque(maxlen=20)
        self._stdout_reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self.protocol_version = ""
        self.server_info: dict = {}

    def start(self, command: Sequence[str], timeout: float) -> None:
        if isinstance(command, str):
            raise ValueError("command must be a sequence of arguments, not a string")
        if timeout is None or timeout <= 0:
            raise ValueError(f"timeout must be positive: {timeout!r}")
        command = list(command)
        if not command:
            raise ProbeError(SPAWN_FAILED, "the command is empty")
        self._timeout = timeout
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=False,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise ProbeError(SPAWN_FAILED, f"{command[0]!r}: {exc}") from exc
        process = self._process
        self._stdout_reader = threading.Thread(
            target=self._read_stdout, args=(process.stdout,), daemon=True
        )
        self._stdout_reader.start()
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, args=(process.stderr,), daemon=True
        )
        self._stderr_reader.start()

    def initialize(self) -> dict:
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "tenon", "version": _package_version()},
            },
        )
        self.protocol_version = result.get("protocolVersion") or ""
        info = result.get("serverInfo")
        self.server_info = info if isinstance(info, dict) else {}
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def list_tools(self) -> tuple[dict, ...]:
        """Every tool the server lists, following ``nextCursor`` to the end."""
        tools: list[dict] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            params = {} if cursor is None else {"cursor": cursor}
            result = self._request("tools/list", params)
            page = result.get("tools")
            if not isinstance(page, list) or not all(
                isinstance(tool, dict) for tool in page
            ):
                raise ProbeError(PROTOCOL_ERROR, "tools/list: tools must be objects")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tuple(tools)
            if cursor in seen:
                raise ProbeError(PROTOCOL_ERROR, "tools/list: repeated nextCursor")
            seen.add(cursor)

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call one tool and return its MCP result; a JSON-RPC error raises."""
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self._stop()
        self._process = None
        if self._stdout_reader is not None:
            self._stdout_reader.join(timeout=1)
        if self._stderr_reader is not None:
            self._stderr_reader.join(timeout=1)

    @property
    def stderr_tail(self) -> str:
        """The capped last lines the server wrote to stderr."""
        return tail("\n".join(self._stderr_lines))

    def _stop(self) -> None:
        process = self._process
        if process is None:
            return
        for stop in (process.terminate, process.kill):
            try:
                stop()
            except OSError:
                pass
            try:
                process.wait(timeout=1)
                return
            except subprocess.TimeoutExpired:
                continue

    def _read_stdout(self, stream) -> None:
        try:
            for line in stream:
                self._lines.put(line)
        finally:
            self._lines.put(None)

    def _read_stderr(self, stream) -> None:
        for line in stream:
            self._stderr_lines.append(line.rstrip("\n")[:2000])

    def _send(self, message: dict) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise ProbeError(CLOSED_PIPE, "the MCP session is not running")
        line = json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n"
        try:
            process.stdin.write(line)
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ProbeError(CLOSED_PIPE, str(exc)) from exc

    def _receive(self) -> dict:
        try:
            line = self._lines.get(timeout=self._timeout)
        except queue.Empty:
            raise ProbeError(TIMEOUT, f"no response within {self._timeout}s") from None
        if line is None:
            raise ProbeError(CLOSED_PIPE, "the server closed its stdout")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ProbeError(PROTOCOL_ERROR, "the message is not an object")
        if "method" in message:
            return self._receive()  # a notification carries no response
        return message

    def _request(self, method: str, params: dict) -> dict:
        if self._process is None:
            raise ProbeError(CLOSED_PIPE, "the MCP session is not running")
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": method,
                "params": params,
            }
        )
        response = self._receive()
        error = response.get("error")
        if error is not None:
            raise ProbeError(SERVER_ERROR, _error_detail(error))
        result = response.get("result")
        if not isinstance(result, dict):
            raise ProbeError(PROTOCOL_ERROR, f"{method}: no result object")
        return result
