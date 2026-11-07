"""The GitHub App auth surface: a fixed token and a JWT exchange; no network."""

import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tenon.pr.app import GitHubAppToken, StaticToken
from tenon.pr.remote import RemoteError

NOW = 1_800_000_000
API = "https://api.github.com"
APP_ID = 123
INSTALLATION_ID = 456


def a_key_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


PRIVATE_KEY_PEM, PUBLIC_KEY = a_key_pair()


class FakeTransport:
    """Records every call and returns queued ``(status, headers, body)``."""

    def __init__(self, *responses):
        self.calls = []
        self.responses = list(responses)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def an_app_token(transport, *, private_key_pem=PRIVATE_KEY_PEM):
    return GitHubAppToken(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=private_key_pem,
        transport=transport,
        now=lambda: NOW,
    )


# Spec AC3: the static provider returns exactly the token it was given.
def test_a_static_token_returns_its_value():
    assert StaticToken("t").token() == "t"


# Spec AC3: an empty token is refused before it can be sent.
def test_a_static_token_refuses_an_empty_token():
    with pytest.raises(ValueError):
        StaticToken("")


# Spec AC1: the JWT names the app, is backdated 60 s and expires 10 min ahead,
# and only the generated private key signs it under RS256.
def test_the_app_jwt_has_the_expected_claims_and_rs256_signature():
    transport = FakeTransport((201, {}, json.dumps({"token": "ghs_installation"})))

    assert an_app_token(transport).token() == "ghs_installation"

    headers = transport.calls[0][2]
    signed = headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(
        signed,
        PUBLIC_KEY,
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["iss"] == str(APP_ID)
    assert claims["iat"] == NOW - 60
    assert claims["exp"] == NOW + 600
    assert jwt.get_unverified_header(signed)["alg"] == "RS256"


# Spec AC2/AC5: the exchange is one POST with the bearer JWT and API headers,
# no body, to the installation's access_tokens endpoint.
def test_the_exchange_posts_the_jwt_and_returns_the_installation_token():
    transport = FakeTransport((201, {}, json.dumps({"token": "ghs_installation"})))

    assert an_app_token(transport).token() == "ghs_installation"

    method, url, headers, body = transport.calls[0]
    assert method == "POST"
    assert url == f"{API}/app/installations/{INSTALLATION_ID}/access_tokens"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["Authorization"].startswith("Bearer ")
    assert body is None


# Spec AC2: a 401 or 500 is a RemoteError with the API message and neither the
# JWT nor the installation token in the detail.
@pytest.mark.parametrize("status", [401, 500])
def test_a_failed_exchange_is_a_remote_error_without_secrets(status):
    body = json.dumps({"message": "Bad credentials", "token": "ghs_secret"})
    transport = FakeTransport((status, {}, body))

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport).token()

    signed = transport.calls[0][2]["Authorization"].removeprefix("Bearer ")
    assert "Bad credentials" in raised.value.detail
    assert signed not in raised.value.detail
    assert "ghs_secret" not in raised.value.detail


# Spec AC2: a long API message cannot grow the error beyond the house cap.
def test_a_long_exchange_error_is_capped():
    transport = FakeTransport((500, {}, json.dumps({"message": "x" * 3000})))

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport).token()

    assert len(raised.value.detail) <= 2000


# Spec AC2: a 2xx body that is not JSON is a RemoteError, and its raw text is
# not copied into the detail.
def test_an_invalid_json_exchange_body_is_a_remote_error():
    transport = FakeTransport((201, {}, "ghs_secret not json"))

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport).token()

    assert "JSON" in raised.value.detail
    assert "ghs_secret" not in raised.value.detail


# Spec AC2: a 2xx JSON body without a token is a RemoteError.
def test_a_missing_installation_token_is_a_remote_error():
    transport = FakeTransport((201, {}, json.dumps({"expires_at": "later"})))

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport).token()

    assert "token" in raised.value.detail


# Spec AC2: a PEM that cannot sign is a RemoteError, not a PyJWT/cryptography
# exception, and it names no key material.
def test_a_bad_private_key_is_a_remote_error():
    transport = FakeTransport()

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport, private_key_pem="not a pem").token()

    assert "JWT" in raised.value.detail
    assert "not a pem" not in raised.value.detail
    assert transport.calls == []


# Spec AC2: a transport that cannot reach GitHub is still a RemoteError.
def test_a_transport_failure_is_a_remote_error():
    transport = FakeTransport(OSError("network down"))

    with pytest.raises(RemoteError) as raised:
        an_app_token(transport).token()

    assert "network down" not in raised.value.detail
    assert "OSError" in raised.value.detail
