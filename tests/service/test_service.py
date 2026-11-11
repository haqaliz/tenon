import json

from tenon.service.api import Api
from tenon.service.runner import Outcome
from tenon.service.store import RunStore
from tenon.service.worker import Worker

TOKEN = "e2e-api-token"


# Spec AC7: POST -> one worker run -> GET returns the same fan-out envelope.
def test_post_run_once_get_returns_the_same_report(tmp_path):
    root = tmp_path / "bundles"
    root.mkdir()
    (root / "stripe-v2500-v2596.json").write_text("{}", encoding="utf-8")
    store = RunStore(tmp_path / "runs.db")
    api = Api(store, root, TOKEN)
    report = {
        "command": "provider",
        "provider": "stripe",
        "migration": "v2500-v2596",
        "repos": [
            {
                "repo": "acme/one",
                "results": [],
                "summary": {"total": 1, "passed": 1},
                "exit": 0,
                "error": None,
            },
            {
                "repo": "acme/two",
                "results": [],
                "summary": {"total": 0, "passed": 0},
                "exit": 1,
                "error": "could not clone acme/two: boom",
            },
        ],
        "summary": {"repos": 2, "passed": 1, "failed": 1},
    }
    executed = []

    def execute(run):
        executed.append(run.bundle)
        return Outcome(1, report, None)

    worker = Worker(store, execute)
    auth = {"Authorization": f"Bearer {TOKEN}"}

    queued = api.handle(
        "POST",
        "/runs",
        auth,
        json.dumps({"bundle": "stripe-v2500-v2596.json"}).encode(),
    )

    assert queued.status == 201
    run_id = json.loads(queued.body)["id"]
    assert worker.run_once() is True
    assert executed == ["stripe-v2500-v2596.json"]

    fetched = api.handle("GET", f"/runs/{run_id}", auth, b"")

    payload = json.loads(fetched.body)
    assert fetched.status == 200
    assert payload["id"] == run_id
    assert payload["bundle"] == "stripe-v2500-v2596.json"
    assert payload["status"] == "failed"
    assert payload["exit"] == 1
    assert payload["report"] == report
    assert payload["error"] is None
    assert payload["started_at"] is not None
    assert payload["finished_at"] is not None

    listed = api.handle("GET", "/runs?limit=1", auth, b"")

    assert json.loads(listed.body) == {"runs": [payload]}
