"""The pure, guarded JSON request handler for the provider service."""

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import Run, RunStore

_JSON_HEADERS = {"Content-Type": "application/json"}


@dataclass(frozen=True, slots=True)
class Response:
    """One HTTP response, already encoded."""

    status: int
    body: bytes
    headers: dict[str, str] | None = None


def _json(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def _response(
    status: int, body: object, *, headers: dict[str, str] | None = None
) -> Response:
    values = dict(_JSON_HEADERS)
    if headers:
        values.update(headers)
    return Response(status, _json(body), values)


def _not_found() -> Response:
    return _response(404, {"error": "not found"})


def _method_not_allowed() -> Response:
    return _response(405, {"error": "method not allowed"})


def _unauthorized() -> Response:
    return _response(
        401,
        {"error": "unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )


# Spec AC2: a bundle name is a relative .json file confined to the root.
def resolve_bundle(root: Path, name: str) -> Path | None:
    """The named bundle under ``root``, or None if it escapes or is not a file."""
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        return None
    root = root.resolve()
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.suffix != ".json" or not candidate.is_file():
        return None
    return candidate


class Api:
    """Route one request to the store; no sockets and no secrets."""

    def __init__(
        self,
        store: RunStore,
        bundles: Path,
        token: str,
        *,
        webhook_secret: str | None = None,
        max_body: int = 65536,
        workers: int = 1,
        triggers: Mapping[tuple[str, str | None], str] | None = None,
    ) -> None:
        self._store = store
        self._bundles = Path(bundles)
        self._token = token
        self._webhook_secret = webhook_secret
        self._max_body = max_body
        self._workers = workers
        self._triggers = dict(triggers or {})

    @property
    def max_body(self) -> int:
        """The largest body the API accepts; the HTTP layer reads only this."""
        return self._max_body

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> Response:
        method = method.upper()
        values = {key.lower(): value for key, value in headers.items()}
        url = urlsplit(path)
        route = url.path

        # Spec AC3/AC5: health is public; the webhook is guarded by its HMAC.
        if route == "/health":
            if method != "GET":
                return _method_not_allowed()
            return _response(200, {"status": "ok"})
        # Spec AC2: readiness is public and reflects the store, not auth.
        if route == "/ready":
            if method != "GET":
                return _method_not_allowed()
            if self._store.ping():
                return _response(200, {"status": "ready"})
            return _response(503, {"status": "unavailable"})
        if route == "/webhooks/github":
            if method != "POST":
                return _method_not_allowed()
            return self._webhook(values, body)

        # Spec AC4: metrics is bearer-guarded like the run routes.
        if route == "/metrics":
            if not self._authorized(values):
                return _unauthorized()
            if method != "GET":
                return _method_not_allowed()
            return self._metrics()

        if route == "/runs":
            if not self._authorized(values):
                return _unauthorized()
            if method == "POST":
                return self._create_run(values, body)
            if method == "GET":
                return self._list_runs(url.query)
            return _method_not_allowed()

        # Spec AC2: /runs/{id}/cancel is one route, ahead of the record route.
        if route.startswith("/runs/"):
            rest = route[len("/runs/"):]
            if rest.endswith("/cancel") and "/" not in rest[:-len("/cancel")]:
                if not self._authorized(values):
                    return _unauthorized()
                if method != "POST":
                    return _method_not_allowed()
                return self._cancel(rest[: -len("/cancel")])
            if "/" not in rest:
                if not self._authorized(values):
                    return _unauthorized()
                if method != "GET":
                    return _method_not_allowed()
                return self._get_run(rest)

        return _not_found()

    def _authorized(self, headers: dict[str, str]) -> bool:
        value = headers.get("authorization")
        if value is None:
            return False
        scheme, _, provided = value.partition(" ")
        if scheme.lower() != "bearer":
            return False
        try:
            return hmac.compare_digest(provided, self._token)
        except TypeError:
            return False

    # Spec AC2: queue one confined bundle; an idempotency key replays the run.
    def _create_run(self, headers: dict[str, str], body: bytes) -> Response:
        if len(body) > self._max_body:
            return _response(413, {"error": "request body too large"})
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _response(400, {"error": "invalid JSON"})
        if not isinstance(payload, dict):
            return _response(400, {"error": "body must be a JSON object"})
        name = payload.get("bundle")
        if not isinstance(name, str) or not name.strip():
            return _response(
                400, {"error": "bundle must be a non-empty string"}
            )
        if resolve_bundle(self._bundles, name) is None:
            return _response(
                400,
                {"error": "bundle is not a .json file under the bundle directory"},
            )

        key = headers.get("idempotency-key")
        if key is not None:
            existing = self._store.find_by_idempotency_key(key)
            if existing is not None:
                return _response(200, self._run_summary(existing))
        run = self._store.create_run(name, idempotency_key=key)
        return _response(201, self._run_summary(run))

    @staticmethod
    def _run_summary(run: Run) -> dict:
        return {"id": run.id, "status": run.status, "bundle": run.bundle}

    # Spec AC3: one durable run, report included.
    def _get_run(self, run_id: str) -> Response:
        run = self._store.get(run_id)
        if run is None:
            return _not_found()
        return _response(200, run.to_dict())

    # Spec AC3: newest-first with a bounded limit.
    def _list_runs(self, query: str) -> Response:
        limit = 50
        values = parse_qs(query, keep_blank_values=True)
        if "limit" in values:
            try:
                limit = int(values["limit"][0])
            except ValueError:
                return _response(400, {"error": "limit must be 1..200"})
            if not 1 <= limit <= 200:
                return _response(400, {"error": "limit must be 1..200"})
        return _response(
            200, {"runs": [run.to_dict() for run in self._store.list(limit)]}
        )

    # Spec AC2: queued cancels now, running gets a flag, terminal is 409.
    def _cancel(self, run_id: str) -> Response:
        existing = self._store.get(run_id)
        if existing is None:
            return _not_found()
        if existing.status in ("succeeded", "failed", "cancelled"):
            return self._conflict(existing.status)
        run = self._store.request_cancel(run_id)
        if run is None:
            return _not_found()
        if run.status == "cancelled":
            return _response(202, {"id": run.id, "status": "cancelled"})
        if run.status in ("succeeded", "failed"):
            return self._conflict(run.status)
        return _response(202, {"id": run.id, "status": "cancelling"})

    @staticmethod
    def _conflict(status: str) -> Response:
        return _response(409, {"error": f"run is {status}", "status": status})

    # Spec AC4: five status gauges plus the configured worker count.
    def _metrics(self) -> Response:
        counts = self._store.counts()
        lines = [
            f'tenon_runs{{status="{status}"}} {counts[status]}'
            for status in (
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
            )
        ]
        lines.append(f"tenon_workers {self._workers}")
        return Response(
            200,
            ("\n".join(lines) + "\n").encode("utf-8"),
            {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
        )

    # Spec AC5: verify the HMAC before trusting any payload; only record.
    def _webhook(self, headers: dict[str, str], body: bytes) -> Response:
        if self._webhook_secret is None:
            return _not_found()
        if len(body) > self._max_body:
            return _response(413, {"error": "request body too large"})
        signature = headers.get("x-hub-signature-256")
        expected = "sha256=" + hmac.new(
            self._webhook_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        try:
            valid = signature is not None and hmac.compare_digest(
                signature, expected
            )
        except TypeError:
            valid = False
        if not valid:
            return _response(401, {"error": "invalid signature"})

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _response(400, {"error": "invalid JSON"})
        if not isinstance(payload, dict):
            return _response(400, {"error": "payload must be a JSON object"})
        delivery = headers.get("x-github-delivery")
        event = headers.get("x-github-event")
        if not delivery or not event:
            return _response(
                400, {"error": "X-GitHub-Delivery and X-GitHub-Event are required"}
            )

        action = payload.get("action")
        if not isinstance(action, str):
            action = None
        installation = payload.get("installation")
        installation_id = (
            installation.get("id") if isinstance(installation, dict) else None
        )
        self._store.record_event(
            delivery,
            event,
            action=action,
            installation=None if installation_id is None else str(installation_id),
            payload=payload,
        )
        # Spec AC1–AC3: an exact action wins; an actionless trigger is the fallback.
        bundle = self._triggers.get((event, action))
        if bundle is None:
            bundle = self._triggers.get((event, None))
        result: dict[str, object] = {"status": "recorded"}
        if bundle is not None:
            run = self._store.create_run(
                bundle, idempotency_key=f"webhook:{delivery}"
            )
            result["run"] = self._run_summary(run)
        return _response(202, result)
