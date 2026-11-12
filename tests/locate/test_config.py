import re
from pathlib import Path

import pytest

from tenon.locate import LocateConfig, load_config

FIXTURE = Path(__file__).parent.parent / "fixtures" / "tenon.toml"


def a_config(**kwargs):
    return LocateConfig(**kwargs)


# Spec AC7: all three tables round-trip from a fixture tenon.toml.
def test_load_config_reads_all_three_tables():
    assert load_config(FIXTURE) == LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.delete"},
        fields={"Charge.amount": "amount_cents"},
    )


# Spec AC7: a bad file is refused with the missing key named.
@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[other]\nx = 1\n", "[locate]"),
        ("[locate]\noperations = {}\n", "sdk_package"),
    ],
)
def test_load_config_names_the_missing_key(tmp_path, text, key):
    path = tmp_path / "tenon.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=re.escape(key)):
        load_config(path)


# Spec AC1: a valid package loads with empty mappings.
def test_a_valid_config_loads_with_empty_receivers():
    config = a_config(sdk_package="stripe")

    assert config.receivers == {}


# Spec AC1: a receiver mapping loads as a read-only copy.
def test_a_receiver_mapping_loads_read_only():
    receivers = {"stripe.NewClient": "Client"}
    config = a_config(sdk_package="stripe", receivers=receivers)

    receivers["stripe.NewOther"] = "Other"

    assert dict(config.receivers) == {"stripe.NewClient": "Client"}
    with pytest.raises(TypeError):
        config.receivers["x"] = "y"


# Spec AC1: a blank or split receiver key or value is a named ValueError.
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("", "Client"),
        ("stripe NewClient", "Client"),
        (" Client", "Client"),
        ("Client ", "Client"),
        ("stripe.NewClient", ""),
        ("stripe.NewClient", "Client Chain"),
        ("stripe.NewClient", " Client"),
        ("stripe.NewClient", "Client "),
        (1, "Client"),
        ("stripe.NewClient", 1),
    ],
)
def test_a_bad_receiver_entry_is_a_named_value_error(key, value):
    with pytest.raises(ValueError, match="receivers"):
        a_config(sdk_package="stripe", receivers={key: value})
