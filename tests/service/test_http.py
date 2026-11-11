import http.client
import threading
from http.server import ThreadingHTTPServer

from tenon.service.api import Api
from tenon.service.http import serve
from tenon.service.store import RunStore


def an_api(tmp_path):
    root = tmp_path / "bundles"
    root.mkdir()
    (root / "bundle.json").write_text("{}", encoding="utf-8")
    store = RunStore(tmp_path / "runs.db")
    return Api(store, root, "test-api-token"), store


# Spec AC2/AC3: serve returns an unstarted stdlib server; its handler proxies
# the API, reads Content-Length and writes the canonical body.
def test_serve_returns_a_server_that_answers_over_loopback(tmp_path, capsys):
    api, store = an_api(tmp_path)
    server = serve(api, "127.0.0.1", 0)

    assert isinstance(server, ThreadingHTTPServer)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(host, port, timeout=2)

        connection.request("GET", "/health")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/json"
        assert response.read() == b'{"status":"ok"}\n'

        connection.request(
            "POST",
            "/runs",
            body=b'{"bundle":"bundle.json"}',
            headers={"Authorization": "Bearer test-api-token"},
        )
        response = connection.getresponse()
        assert response.status == 201
        assert b'"status":"queued"' in response.read()

        connection.request("POST", "/runs", body=b"{}")
        response = connection.getresponse()
        assert response.status == 401
        assert response.getheader("WWW-Authenticate") == "Bearer"
        assert b'"error":"unauthorized"' in response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        store.close()

    # Spec AC6: the request log is silent, so no method or path leaks.
    assert capsys.readouterr().err == ""
