"""The GitHub App auth surface: a fixed token and a JWT exchange; no network."""

import pytest

from tenon.pr.app import StaticToken


# Spec AC3: the static provider returns exactly the token it was given.
def test_a_static_token_returns_its_value():
    assert StaticToken("t").token() == "t"


# Spec AC3: an empty token is refused before it can be sent.
def test_a_static_token_refuses_an_empty_token():
    with pytest.raises(ValueError):
        StaticToken("")
