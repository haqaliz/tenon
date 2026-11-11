"""The stdlib HTTP listener around the pure Api handler."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .api import Api


class _Server(ThreadingHTTPServer):
    api: Api


class _Handler(BaseHTTPRequestHandler):
    """One request: read Content-Length, call the API, write its response."""

    server_version = "tenon"
    sys_version = ""

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def _handle(self) -> None:
        api = self.server.api
        try:
            length = max(0, int(self.headers.get("Content-Length") or 0))
        except ValueError:
            length = 0
        # Spec AC2/AC6: cap the read; a larger body is the API's 413.
        body = self.rfile.read(min(length, api.max_body + 1)) if length else b""
        response = api.handle(
            self.command, self.path, dict(self.headers.items()), body
        )
        self.send_response(response.status)
        for name, value in (response.headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    # Spec AC6: no request path or header reaches the log.
    def log_message(self, format: str, *args) -> None:
        pass


def serve(api: Api, host: str, port: int) -> ThreadingHTTPServer:
    """Build the listener; the caller starts it."""
    server = _Server((host, port), _Handler)
    server.api = api
    return server
