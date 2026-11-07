"""Token providers for the GitHub App remote."""

import json
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import jwt

from .remote import RemoteError

_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


class TokenProvider(Protocol):
    """Something that can produce a bearer token on demand."""

    def token(self) -> str: ...


@dataclass(frozen=True, slots=True)
class StaticToken:
    """A token minted elsewhere, for tests and short-lived operators."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("token must not be empty")

    def token(self) -> str:
        return self.value


def _api_message(body: str | None) -> str:
    """The API's own message, and never any other field of the body."""
    try:
        payload = json.loads(body or "")
    except (TypeError, ValueError):
        return ""
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        return payload["message"]
    return ""


class GitHubAppToken:
    """Mint an installation token from the app id and its private key."""

    def __init__(
        self,
        app_id: int | str,
        installation_id: int | str,
        private_key_pem: str,
        transport,
        api_url: str = "https://api.github.com",
        now: Callable[[], float] | None = None,
    ) -> None:
        self._app_id = app_id
        self._installation_id = installation_id
        self._private_key_pem = private_key_pem
        self._transport = transport
        self._api_url = api_url.rstrip("/")
        self._now = now or time.time

    def _signed_jwt(self) -> str:
        now = int(self._now())
        try:
            return jwt.encode(
                {"iss": str(self._app_id), "iat": now - 60, "exp": now + 600},
                self._private_key_pem,
                algorithm="RS256",
            )
        except Exception as exc:
            raise RemoteError(
                f"could not sign the app JWT: {type(exc).__name__}"
            ) from exc

    def token(self) -> str:
        signed = self._signed_jwt()
        url = (
            f"{self._api_url}/app/installations/"
            f"{self._installation_id}/access_tokens"
        )
        headers = {
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
            "Authorization": f"Bearer {signed}",
        }
        try:
            status, _headers, body = self._transport("POST", url, headers, None)
        except OSError as exc:
            raise RemoteError(
                f"GitHub App token exchange failed: {type(exc).__name__}"
            ) from exc

        if not 200 <= status < 300:
            message = _api_message(body)
            detail = f"GitHub App token exchange failed: HTTP {status}"
            if message:
                detail = f"{detail}: {message}"
            raise RemoteError(detail)

        try:
            payload = json.loads(body) if body else {}
        except (TypeError, ValueError):
            raise RemoteError(
                "GitHub App token exchange failed: invalid JSON"
            ) from None
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise RemoteError(
                "GitHub App token exchange failed: no token in the response"
            )
        return token
