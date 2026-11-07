"""The small GitHub REST client the app remote needs."""

import json
import urllib.error
import urllib.request

from .remote import RemoteError

_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


class GitHubApiError(RemoteError):
    """One REST call failed; ``status`` is None when no response arrived."""

    def __init__(self, detail: str, status: int | None = None) -> None:
        self.status = status
        super().__init__(detail)


def _api_message(body: str | None) -> str:
    """The API's own message, and never any other field of the body."""
    try:
        payload = json.loads(body or "")
    except (TypeError, ValueError):
        return ""
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        return payload["message"]
    return ""


class GitHubApi:
    """JSON in, JSON out; the transport is injectable and offline in tests."""

    def __init__(
        self,
        api_url: str = "https://api.github.com",
        transport=None,
        timeout: float = 30,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport or self._urllib

    def _urllib(self, method, url, headers, body):
        request = urllib.request.Request(
            url,
            data=body.encode("utf-8") if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return (
                    response.status,
                    dict(response.headers),
                    response.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                dict(exc.headers or {}),
                exc.read().decode("utf-8", errors="replace"),
            )

    def request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict | None = None,
    ) -> dict:
        headers = {
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
            "Authorization": f"Bearer {token}",
        }
        sent = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            sent = json.dumps(body)
        url = f"{self._api_url}/{path.lstrip('/')}"
        try:
            status, _headers, response_body = self._transport(
                method, url, headers, sent
            )
        except OSError as exc:
            raise GitHubApiError(
                f"{method} {path} failed: {type(exc).__name__}"
            ) from exc

        if not 200 <= status < 300:
            message = _api_message(response_body)
            detail = f"{method} {path} failed: HTTP {status}"
            if message:
                detail = f"{detail}: {message}"
            raise GitHubApiError(detail, status=status)

        if not response_body:
            return {}
        try:
            payload = json.loads(response_body)
        except (TypeError, ValueError):
            raise GitHubApiError(
                f"{method} {path} returned invalid JSON", status=status
            ) from None
        if not isinstance(payload, dict):
            raise GitHubApiError(
                f"{method} {path} returned invalid JSON", status=status
            ) from None
        return payload
