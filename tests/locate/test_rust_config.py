"""The Rust locate config: one crate identifier and read-only mappings."""

import pytest

from tenon.locate.rust_config import RustLocateConfig


def a_config(**kwargs):
    return RustLocateConfig(**kwargs)


# Spec AC1: a valid crate loads with empty mappings.
def test_a_valid_crate_loads():
    config = a_config(sdk_package="stripe")

    assert config.sdk_package == "stripe"
    assert config.operations == {}
    assert config.fields == {}
    assert config.receivers == {}


def test_a_crate_with_underscores_and_digits_loads():
    config = a_config(sdk_package="async_stripe2")

    assert config.sdk_package == "async_stripe2"


# Spec AC1: a blank, a path, or a `::` path is a named ValueError.
@pytest.mark.parametrize(
    "name",
    ["", " ", "stripe::charge", "stripe/charge", "stripe.charge", "9stripe", "stripe-charge"],
)
def test_an_invalid_crate_is_a_named_value_error(name):
    with pytest.raises(ValueError, match="sdk_package"):
        a_config(sdk_package=name)


# Spec AC1: the mappings are read-only copies, not the caller's dicts.
def test_the_mappings_are_read_only_copies():
    operations = {"POST /v1/charges": "Charge.create"}
    fields = {"Charge.amount": "amount_cents"}
    config = a_config(sdk_package="stripe", operations=operations, fields=fields)

    operations["POST /v1/other"] = "Other.create"
    fields["Charge.amount"] = "changed"

    assert dict(config.operations) == {"POST /v1/charges": "Charge.create"}
    assert dict(config.fields) == {"Charge.amount": "amount_cents"}
    with pytest.raises(TypeError):
        config.operations["x"] = "y"
    with pytest.raises(TypeError):
        config.fields["x"] = "y"


def test_the_config_is_frozen_and_slotted():
    config = a_config(sdk_package="stripe")

    with pytest.raises((AttributeError, TypeError)):
        config.sdk_package = "other"
    assert not hasattr(config, "__dict__")


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
        ("stripe.NewClient", ""),
        ("stripe.NewClient", "Client Chain"),
        (1, "Client"),
        ("stripe.NewClient", 1),
    ],
)
def test_a_bad_receiver_entry_is_a_named_value_error(key, value):
    with pytest.raises(ValueError, match="receivers"):
        a_config(sdk_package="stripe", receivers={key: value})
