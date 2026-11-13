import hashlib
import hmac
import json
import sqlite3

import pytest

from tenon.service.api import Api, Response, resolve_bundle
from tenon.service.store import RunStore

TOKEN = "test-api-token"
SECRET = "test-webhook-secret"


def a_root(tmp_path):
    root = tmp_path / "bundles"
    root.mkdir()
    (root / "bundle.json").write_text("{}", encoding="utf-8")
    nested = root / "sub"
    nested.mkdir()
    (nested / "nested.json").write_text("{}", encoding="utf-8")
    return root


def an_api(tmp_path, *, secret=None, max_body=65536, token=TOKEN, workers=1, triggers=None):
    root = a_root(tmp_path)
    store = RunStore(tmp_path / "runs.db")
    return (
        Api(
            store,
            root,
            token,
            webhook_secret=secret,
            max_body=max_body,
            workers=workers,
            triggers=triggers,
        ),
        store,
        root,
    )


def a_call(api, method, path, body=b"", headers=None, token=TOKEN):
    values = dict(headers or {})
    if token is not None and "Authorization" not in values:
        values["Authorization"] = f"Bearer {token}"
    return api.handle(method, path, values, body)


def a_json(response):
    assert response.body.endswith(b"\n")
    return json.loads(response.body)


def a_response(payload, status, **headers):
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return Response(status, (text + "\n").encode("utf-8"), headers or None)


def a_signed(body, *, secret=SECRET, delivery="delivery-one", event="installation"):
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Delivery": delivery,
        "X-GitHub-Event": event,
    }


def an_event_rows(path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT delivery, event, action, installation, payload FROM events"
        ).fetchall()


# Spec AC3: health is 200 without auth and is canonical JSON.
def test_health_is_200_without_auth(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = api.handle("GET", "/health", {}, b"")

    assert response.status == 200
    assert response.body == b'{"status":"ok"}\n'
    assert response.headers["Content-Type"] == "application/json"


# Spec AC2: a usable store is ready without auth and in canonical JSON.
def test_ready_is_200_without_auth(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = api.handle("GET", "/ready", {}, b"")

    assert response.status == 200
    assert response.body == b'{"status":"ready"}\n'
    assert response.body == a_response({"status": "ready"}, 200).body
    assert response.headers["Content-Type"] == "application/json"


# Spec AC2: a closed store is unavailable, not an error.
def test_ready_is_503_on_a_closed_store(tmp_path):
    api, store, _root = an_api(tmp_path)
    store.close()

    response = api.handle("GET", "/ready", {}, b"")

    assert response.status == 503
    assert response.body == b'{"status":"unavailable"}\n'
    assert response.headers["Content-Type"] == "application/json"


# Spec AC2: an unknown path is a canonical 404 error.
def test_an_unknown_path_is_404(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "GET", "/nope")

    assert a_json(response) == {"error": "not found"}
    assert response.body == b'{"error":"not found"}\n'


# Spec AC2/AC3: a known path with the wrong method is 405.
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/runs"),
        ("POST", "/runs/abc"),
        ("POST", "/health"),
        ("POST", "/ready"),
        ("GET", "/webhooks/github"),
    ],
)
def test_a_wrong_method_is_405(tmp_path, method, path):
    api, _store, _root = an_api(tmp_path, secret=SECRET)

    response = a_call(api, method, path)

    assert response.status == 405
    assert a_json(response) == {"error": "method not allowed"}


# Spec AC2/AC5: a missing, malformed or wrong bearer token is 401.
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic test-api-token"},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Bearer "},
    ],
)
def test_bad_auth_is_401_with_www_authenticate(tmp_path, headers):
    api, store, _root = an_api(tmp_path)
    body = b'{"bundle":"bundle.json"}'

    response = api.handle("POST", "/runs", headers, body)

    assert response.status == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert a_json(response) == {"error": "unauthorized"}
    assert TOKEN not in response.body.decode()
    assert store.list() == ()


# Spec AC2/AC5: a correct bearer token queues the bundle.
def test_the_bearer_token_is_compared_and_queues_the_run(tmp_path):
    api, store, _root = an_api(tmp_path)

    response = a_call(
        api, "POST", "/runs", b'{"bundle":"bundle.json"}'
    )

    assert response.status == 201
    payload = a_json(response)
    (run,) = store.list()
    assert payload == {
        "id": run.id,
        "status": "queued",
        "bundle": "bundle.json",
    }
    assert response.body == a_response(payload, 201).body


# Spec AC5: the header names are case-insensitive.
def test_header_names_are_case_insensitive(tmp_path):
    api, store, _root = an_api(tmp_path)

    response = api.handle(
        "POST",
        "/runs",
        {
            "authorization": f"Bearer {TOKEN}",
            "idempotency-key": "key-one",
        },
        b'{"bundle":"bundle.json"}',
    )
    second = api.handle(
        "POST",
        "/runs",
        {
            "AUTHORIZATION": f"Bearer {TOKEN}",
            "IDEMPOTENCY-KEY": "key-one",
        },
        b'{"bundle":"bundle.json"}',
    )

    assert response.status == 201
    assert second.status == 200
    assert a_json(second)["id"] == a_json(response)["id"]
    assert len(store.list()) == 1


# Spec AC2: a valid nested relative bundle queues.
def test_a_nested_relative_bundle_queues(tmp_path):
    api, store, _root = an_api(tmp_path)

    response = a_call(api, "POST", "/runs", b'{"bundle":"sub/nested.json"}')

    assert response.status == 201
    assert store.list()[0].bundle == "sub/nested.json"


# Spec AC2: an idempotency key returns the existing run with 200.
def test_an_idempotency_key_returns_the_existing_run(tmp_path):
    api, store, _root = an_api(tmp_path)
    headers = {"Idempotency-Key": "key-one"}
    body = b'{"bundle":"bundle.json"}'

    first = a_call(api, "POST", "/runs", body, headers=headers)
    second = a_call(api, "POST", "/runs", body, headers=headers)

    assert first.status == 201
    assert second.status == 200
    assert a_json(second) == a_json(first)
    assert len(store.list()) == 1
    assert store.find_by_idempotency_key("key-one").id == a_json(first)["id"]


# Spec AC2: distinct idempotency keys create distinct runs.
def test_distinct_idempotency_keys_create_distinct_runs(tmp_path):
    api, store, _root = an_api(tmp_path)
    body = b'{"bundle":"bundle.json"}'

    first = a_call(
        api, "POST", "/runs", body, headers={"Idempotency-Key": "key-one"}
    )
    second = a_call(
        api, "POST", "/runs", body, headers={"Idempotency-Key": "key-two"}
    )

    assert first.status == second.status == 201
    assert a_json(first)["id"] != a_json(second)["id"]
    assert len(store.list()) == 2


# Spec AC2: a body over max_body is 413 and queues nothing.
def test_a_body_over_max_body_is_413(tmp_path):
    api, store, _root = an_api(tmp_path, max_body=8)
    body = b'{"bundle":"bundle.json"}'

    response = a_call(api, "POST", "/runs", body)

    assert response.status == 413
    assert a_json(response) == {"error": "request body too large"}
    assert store.list() == ()


# Spec AC2: a body exactly at max_body is read, not rejected as too large.
def test_a_body_at_max_body_is_not_413(tmp_path):
    body = b'{"bundle":"bundle.json"}'
    api, _store, _root = an_api(tmp_path, max_body=len(body))

    response = a_call(api, "POST", "/runs", body)

    assert response.status == 201


# Spec AC2: a non-JSON or non-object body is 400.
@pytest.mark.parametrize("body", [b"not json", b"[]", b'"bundle"', b"null"])
def test_a_non_object_body_is_400(tmp_path, body):
    api, store, _root = an_api(tmp_path)

    response = a_call(api, "POST", "/runs", body)

    assert response.status == 400
    assert "error" in a_json(response)
    assert store.list() == ()


# Spec AC2: a missing or non-string bundle is 400.
@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"bundle":null}',
        b'{"bundle":3}',
        b'{"bundle":""}',
        b'{"bundle":"   "}',
    ],
)
def test_a_missing_or_non_string_bundle_is_400(tmp_path, body):
    api, store, _root = an_api(tmp_path)

    response = a_call(api, "POST", "/runs", body)

    assert response.status == 400
    assert "error" in a_json(response)
    assert store.list() == ()


# Spec AC2: traversal, absolute, missing, non-file and non-JSON are 400.
@pytest.mark.parametrize(
    "name",
    [
        "../outside.json",
        "sub/../../outside.json",
        "/etc/passwd.json",
        "missing.json",
        "bundle.txt",
        "sub",
    ],
)
def test_an_unsafe_bundle_name_is_400(tmp_path, name):
    api, store, root = an_api(tmp_path)
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    (root / "bundle.txt").write_text("{}", encoding="utf-8")
    body = json.dumps({"bundle": name}).encode()

    response = a_call(api, "POST", "/runs", body)

    assert response.status == 400
    assert "error" in a_json(response)
    assert store.list() == ()


# Spec AC2: a symlink that resolves outside the bundle root is 400.
def test_a_symlink_escape_is_400(tmp_path):
    api, store, root = an_api(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (root / "escape.json").symlink_to(outside)

    response = a_call(api, "POST", "/runs", b'{"bundle":"escape.json"}')

    assert response.status == 400
    assert store.list() == ()


# Spec AC2: resolve_bundle is the confinement helper.
def test_resolve_bundle_confines_the_name(tmp_path):
    root = a_root(tmp_path)
    (root / "bundle.txt").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (root / "escape.json").symlink_to(outside)

    assert resolve_bundle(root, "bundle.json") == root / "bundle.json"
    assert resolve_bundle(root, "sub/nested.json") == root / "sub" / "nested.json"
    assert resolve_bundle(root, "../outside.json") is None
    assert resolve_bundle(root, str(outside)) is None
    assert resolve_bundle(root, "missing.json") is None
    assert resolve_bundle(root, "bundle.txt") is None
    assert resolve_bundle(root, "escape.json") is None
    assert resolve_bundle(root, "sub") is None


# Spec AC3: GET one run returns its durable record.
def test_get_one_run_returns_the_record(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")

    response = a_call(api, "GET", f"/runs/{run.id}")

    assert response.status == 200
    assert a_json(response) == run.to_dict()


# Spec AC3/AC7: a finished run returns the stored report and exit.
def test_get_one_run_includes_the_finished_report(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")
    store.claim_next()
    report = {"command": "provider", "summary": {"repos": 1, "passed": 1}}
    store.finish(run.id, status="succeeded", exit=0, report=report)

    response = a_call(api, "GET", f"/runs/{run.id}")

    payload = a_json(response)
    assert response.status == 200
    assert payload["status"] == "succeeded"
    assert payload["exit"] == 0
    assert payload["report"] == report
    assert payload["error"] is None


# Spec AC3: an unknown run id is 404.
def test_get_an_unknown_run_is_404(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "GET", "/runs/" + "f" * 32)

    assert response.status == 404
    assert a_json(response) == {"error": "not found"}


# Spec AC3: list returns newest-first under a runs key.
def test_list_returns_the_newest_first(tmp_path):
    api, store, _root = an_api(tmp_path)
    runs = [store.create_run(f"bundle-{number}.json") for number in range(3)]

    response = a_call(api, "GET", "/runs")

    payload = a_json(response)
    assert response.status == 200
    assert [run["id"] for run in payload["runs"]] == [
        runs[2].id,
        runs[1].id,
        runs[0].id,
    ]


# Spec AC3: limit is a query parameter with a 1..200 bound.
def test_list_respects_the_limit(tmp_path):
    api, store, _root = an_api(tmp_path)
    for number in range(3):
        store.create_run(f"bundle-{number}.json")

    assert len(a_json(a_call(api, "GET", "/runs?limit=2"))["runs"]) == 2
    assert len(a_json(a_call(api, "GET", "/runs?limit=1"))["runs"]) == 1
    assert a_call(api, "GET", "/runs?limit=200").status == 200


# Spec AC3: a bad limit is 400.
@pytest.mark.parametrize("value", ["0", "201", "-1", "abc", "", "1.5"])
def test_a_bad_limit_is_400(tmp_path, value):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "GET", f"/runs?limit={value}")

    assert response.status == 400
    assert "error" in a_json(response)


# Spec AC5: without a configured secret the webhook route is 404.
def test_a_webhook_without_a_secret_is_404(tmp_path):
    api, _store, _root = an_api(tmp_path)
    body = b'{"action":"created"}'

    response = api.handle(
        "POST", "/webhooks/github", a_signed(body), body
    )

    assert response.status == 404


# Spec AC5: a missing, malformed or wrong signature is 401.
@pytest.mark.parametrize(
    "signature",
    [None, "", "sha256=", "sha256=nope", "sha1=abcd", "not-a-signature"],
)
def test_a_bad_webhook_signature_is_401(tmp_path, signature):
    api, store, _root = an_api(tmp_path, secret=SECRET)
    body = b'{"action":"created"}'
    headers = a_signed(body)
    if signature is None:
        del headers["X-Hub-Signature-256"]
    else:
        headers["X-Hub-Signature-256"] = signature

    response = api.handle("POST", "/webhooks/github", headers, body)

    assert response.status == 401
    assert "error" in a_json(response)
    assert SECRET not in response.body.decode()
    assert an_event_rows(tmp_path / "runs.db") == []


# Spec AC5: a valid signature records the delivery and payload once.
def test_a_valid_webhook_is_recorded(tmp_path):
    api, _store, _root = an_api(tmp_path, secret=SECRET)
    payload = {
        "action": "created",
        "installation": {"id": 42},
        "repositories": [{"full_name": "acme/one"}],
    }
    body = json.dumps(payload).encode()
    headers = a_signed(body, delivery="delivery-one", event="installation")

    response = api.handle("POST", "/webhooks/github", headers, body)

    assert response.status == 202
    assert a_json(response) == {"status": "recorded"}
    rows = an_event_rows(tmp_path / "runs.db")
    assert len(rows) == 1
    delivery, event, action, installation, stored = rows[0]
    assert (delivery, event, action, installation) == (
        "delivery-one",
        "installation",
        "created",
        "42",
    )
    assert json.loads(stored) == payload


# Spec AC5: a duplicate delivery is 202 and leaves one row.
def test_a_duplicate_webhook_is_202_with_one_row(tmp_path):
    api, _store, _root = an_api(tmp_path, secret=SECRET)
    first = b'{"action":"created"}'
    second = b'{"action":"deleted"}'

    one = api.handle(
        "POST", "/webhooks/github", a_signed(first, delivery="same"), first
    )
    two = api.handle(
        "POST", "/webhooks/github", a_signed(second, delivery="same"), second
    )

    assert one.status == 202
    assert two.status == 202
    rows = an_event_rows(tmp_path / "runs.db")
    assert len(rows) == 1
    assert json.loads(rows[0][4]) == {"action": "created"}


# Spec AC1: a matching trigger queues one run and the 202 names it.
def test_a_matching_webhook_queues_a_run(tmp_path):
    api, store, _root = an_api(
        tmp_path,
        secret=SECRET,
        triggers={("installation_repositories", "added"): "bundle.json"},
    )
    body = json.dumps({"action": "added"}).encode()
    headers = a_signed(
        body, event="installation_repositories", delivery="delivery-trigger"
    )

    response = api.handle("POST", "/webhooks/github", headers, body)

    assert response.status == 202
    payload = a_json(response)
    assert payload["status"] == "recorded"
    assert payload["run"]["bundle"] == "bundle.json"
    stored = store.get(payload["run"]["id"])
    assert stored.status == "queued"
    assert stored.idempotency_key == "webhook:delivery-trigger"


# Spec AC2: a non-matching event is recorded only.
def test_a_non_matching_webhook_records_only(tmp_path):
    api, store, _root = an_api(
        tmp_path, secret=SECRET, triggers={("push", None): "bundle.json"}
    )
    body = b'{"action":"created"}'
    headers = a_signed(body, event="installation", delivery="delivery-no")

    response = api.handle("POST", "/webhooks/github", headers, body)

    assert a_json(response) == {"status": "recorded"}
    assert store.list() == ()


# Spec AC3: an exact action wins over the actionless fallback.
def test_an_exact_action_wins_over_the_actionless_trigger(tmp_path):
    api, store, _root = an_api(
        tmp_path,
        secret=SECRET,
        triggers={
            ("push", "created"): "bundle.json",
            ("push", None): "sub/nested.json",
        },
    )
    body = b'{"action":"created"}'

    response = api.handle(
        "POST", "/webhooks/github", a_signed(body, event="push"), body
    )

    payload = a_json(response)
    assert payload["run"]["bundle"] == "bundle.json"
    assert store.get(payload["run"]["id"]).bundle == "bundle.json"


# Spec AC3: an actionless trigger matches any action as the fallback.
def test_an_actionless_trigger_matches_any_action(tmp_path):
    api, store, _root = an_api(
        tmp_path, secret=SECRET, triggers={("push", None): "bundle.json"}
    )
    body = b'{"action":"deleted"}'

    response = api.handle(
        "POST", "/webhooks/github", a_signed(body, event="push"), body
    )

    payload = a_json(response)
    assert payload["run"]["bundle"] == "bundle.json"
    assert len(store.list()) == 1


# Spec AC4: a duplicate delivery returns the same run and leaves one row.
def test_a_duplicate_triggered_delivery_is_one_run(tmp_path):
    api, store, _root = an_api(
        tmp_path, secret=SECRET, triggers={("push", None): "bundle.json"}
    )
    first = b'{"action":"created"}'
    second = b'{"action":"created"}'

    one = api.handle(
        "POST",
        "/webhooks/github",
        a_signed(first, event="push", delivery="delivery-same"),
        first,
    )
    two = api.handle(
        "POST",
        "/webhooks/github",
        a_signed(second, event="push", delivery="delivery-same"),
        second,
    )

    assert one.status == 202
    assert two.status == 202
    assert a_json(one)["run"]["id"] == a_json(two)["run"]["id"]
    assert len(store.list()) == 1


# Spec AC5: a bundle deleted after startup queues; the worker fails it, not the webhook.
def test_a_deleted_bundle_is_a_failed_run_not_a_webhook_error(tmp_path):
    from tenon.cli.main import _serve_execute
    from tenon.service.worker import Worker

    api, store, root = an_api(
        tmp_path, secret=SECRET, triggers={("push", None): "bundle.json"}
    )
    (root / "bundle.json").unlink()
    body = b'{"action":"created"}'

    response = api.handle(
        "POST", "/webhooks/github", a_signed(body, event="push"), body
    )

    assert response.status == 202
    run_id = a_json(response)["run"]["id"]

    class FakeRunner:
        def run(self, path):
            raise AssertionError("a missing bundle must not reach the runner")

    worker = Worker(store, _serve_execute(FakeRunner(), root))
    assert worker.run_once() is True

    stored = store.get(run_id)
    assert stored.status == "failed"
    assert "bundle is not available" in stored.error


# Spec AC6: a triggered run is visible through the normal run API.
def test_a_triggered_run_is_readable(tmp_path):
    api, _store, _root = an_api(
        tmp_path, secret=SECRET, triggers={("push", None): "bundle.json"}
    )
    body = b'{"action":"created"}'
    queued = a_json(
        api.handle(
            "POST", "/webhooks/github", a_signed(body, event="push"), body
        )
    )
    run_id = queued["run"]["id"]

    response = a_call(api, "GET", f"/runs/{run_id}")

    assert response.status == 200
    assert a_json(response)["status"] == "queued"
    assert a_json(response)["id"] == run_id


# Spec AC5: malformed JSON or a non-object is 400, not recorded.
@pytest.mark.parametrize("body", [b"not json", b"[]", b'"payload"', b"null"])
def test_a_malformed_webhook_is_400(tmp_path, body):
    api, _store, _root = an_api(tmp_path, secret=SECRET)

    response = api.handle("POST", "/webhooks/github", a_signed(body), body)

    assert response.status == 400
    assert "error" in a_json(response)
    assert an_event_rows(tmp_path / "runs.db") == []


# Spec AC5: the delivery and event headers are required.
@pytest.mark.parametrize(
    "omitted", ["X-GitHub-Delivery", "X-GitHub-Event"]
)
def test_a_webhook_missing_a_header_is_400(tmp_path, omitted):
    api, _store, _root = an_api(tmp_path, secret=SECRET)
    body = b'{"action":"created"}'
    headers = a_signed(body)
    del headers[omitted]

    response = api.handle("POST", "/webhooks/github", headers, body)

    assert response.status == 400
    assert an_event_rows(tmp_path / "runs.db") == []


# Spec AC6: the token and secret never appear in any error body.
def test_the_token_and_secret_never_appear_in_errors(tmp_path):
    api, _store, _root = an_api(tmp_path, secret=SECRET)
    body = b'{"action":"created"}'

    responses = [
        api.handle("POST", "/runs", {}, body),
        api.handle("POST", "/webhooks/github", {}, body),
        api.handle("GET", "/runs/unknown", {}, b""),
        api.handle("DELETE", "/runs", {"Authorization": f"Bearer {TOKEN}"}, b""),
    ]

    for response in responses:
        assert TOKEN not in response.body.decode()
        assert SECRET not in response.body.decode()
        assert TOKEN not in response.headers.values()
        assert SECRET not in response.headers.values()


# Spec AC2: cancelling a queued run marks it cancelled now.
def test_cancel_a_queued_run_is_202_cancelled(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")

    response = a_call(api, "POST", f"/runs/{run.id}/cancel")

    assert response.status == 202
    assert a_json(response) == {"id": run.id, "status": "cancelled"}
    assert response.body == a_response(
        {"id": run.id, "status": "cancelled"}, 202
    ).body
    finished = store.get(run.id)
    assert finished.status == "cancelled"
    assert finished.finished_at is not None


# Spec AC2: cancelling a running run flags it and answers cancelling.
def test_cancel_a_running_run_is_202_cancelling(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")
    store.claim_next()

    response = a_call(api, "POST", f"/runs/{run.id}/cancel")

    assert response.status == 202
    assert a_json(response) == {"id": run.id, "status": "cancelling"}
    assert store.cancel_requested(run.id) is True
    assert store.get(run.id).status == "running"


# Spec AC2: a terminal run is 409 with its status.
@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_cancel_a_finished_run_is_409(tmp_path, status):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")
    store.claim_next()
    store.finish(run.id, status=status, exit=0, report={})

    response = a_call(api, "POST", f"/runs/{run.id}/cancel")

    assert response.status == 409
    assert a_json(response) == {
        "error": f"run is {status}",
        "status": status,
    }


# Spec AC2: an already-cancelled run is 409, the same terminal rule.
def test_cancel_an_already_cancelled_run_is_409(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")
    store.request_cancel(run.id)

    response = a_call(api, "POST", f"/runs/{run.id}/cancel")

    assert response.status == 409
    assert a_json(response) == {
        "error": "run is cancelled",
        "status": "cancelled",
    }


# Spec AC2: cancelling an unknown run is 404.
def test_cancel_an_unknown_run_is_404(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "POST", "/runs/" + "f" * 32 + "/cancel")

    assert response.status == 404
    assert a_json(response) == {"error": "not found"}


# Spec AC2: cancel is bearer-guarded.
def test_cancel_requires_the_bearer_token(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")

    response = api.handle("POST", f"/runs/{run.id}/cancel", {}, b"")

    assert response.status == 401
    assert store.get(run.id).status == "queued"


# Spec AC2: a non-POST cancel is 405.
def test_a_non_post_cancel_is_405(tmp_path):
    api, store, _root = an_api(tmp_path)
    run = store.create_run("bundle.json")

    response = a_call(api, "GET", f"/runs/{run.id}/cancel")

    assert response.status == 405
    assert store.get(run.id).status == "queued"


# Spec AC4: metrics reports every status, the worker count and the type.
def test_metrics_reports_all_statuses_and_workers(tmp_path):
    api, store, _root = an_api(tmp_path, workers=2)
    succeeded = store.create_run("succeeded.json")
    store.claim_next()
    store.finish(succeeded.id, status="succeeded", exit=0, report={})
    failed = store.create_run("failed.json")
    store.claim_next()
    store.finish(failed.id, status="failed", exit=2, report=None)
    cancelled = store.create_run("cancelled.json")
    store.request_cancel(cancelled.id)
    running = store.create_run("running.json")
    store.claim_next()
    store.create_run("queued.json")

    response = a_call(api, "GET", "/metrics")

    assert response.status == 200
    assert response.headers["Content-Type"] == (
        "text/plain; version=0.0.4; charset=utf-8"
    )
    assert response.body == (
        b'tenon_runs{status="queued"} 1\n'
        b'tenon_runs{status="running"} 1\n'
        b'tenon_runs{status="succeeded"} 1\n'
        b'tenon_runs{status="failed"} 1\n'
        b'tenon_runs{status="cancelled"} 1\n'
        b"tenon_workers 2\n"
    )
    assert store.get(running.id).status == "running"


# Spec AC4: an empty store still reports every status as zero.
def test_metrics_reports_zero_counts_and_the_default_worker(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "GET", "/metrics")

    assert response.body == (
        b'tenon_runs{status="queued"} 0\n'
        b'tenon_runs{status="running"} 0\n'
        b'tenon_runs{status="succeeded"} 0\n'
        b'tenon_runs{status="failed"} 0\n'
        b'tenon_runs{status="cancelled"} 0\n'
        b"tenon_workers 1\n"
    )


# Spec AC4: metrics is bearer-guarded.
def test_metrics_requires_the_bearer_token(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = api.handle("GET", "/metrics", {}, b"")

    assert response.status == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


# Spec AC4: a non-GET metrics request is 405.
def test_a_non_get_metrics_is_405(tmp_path):
    api, _store, _root = an_api(tmp_path)

    response = a_call(api, "POST", "/metrics")

    assert response.status == 405
    assert a_json(response) == {"error": "method not allowed"}
