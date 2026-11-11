"""The Go locate config: one import root, an optional package name and mappings."""

import pytest

from tenon.locate.go_config import GoLocateConfig


def a_config(**kwargs):
    return GoLocateConfig(**kwargs)


# Spec AC1: a valid import root loads with empty mappings and no override.
def test_a_valid_import_root_loads():
    config = a_config(sdk_package="github.com/stripe/stripe-go/v76")

    assert config.sdk_package == "github.com/stripe/stripe-go/v76"
    assert config.package_name is None
    assert config.operations == {}
    assert config.fields == {}
    assert config.receivers == {}


# Spec AC1: a package-name override is an optional Go identifier.
def test_a_valid_package_name_loads():
    config = a_config(sdk_package="github.com/stripe/stripe-go/v76", package_name="stripe")

    assert config.package_name == "stripe"


# Spec AC1: a blank, whitespace, slash-edged or `::` root is a named ValueError.
@pytest.mark.parametrize(
    "root",
    [
        "",
        " ",
        "github.com/stripe stripe",
        " github.com/stripe",
        "github.com/stripe ",
        "/github.com/stripe",
        "github.com/stripe/",
        "github.com/stripe::charge",
    ],
)
def test_an_invalid_import_root_is_a_named_value_error(root):
    with pytest.raises(ValueError, match="sdk_package"):
        a_config(sdk_package=root)


# Spec AC1: a bad package name is a named ValueError.
@pytest.mark.parametrize("name", ["", "9stripe", "stripe-charge", "stripe.charge", "stripe charge"])
def test_a_bad_package_name_is_a_named_value_error(name):
    with pytest.raises(ValueError, match="package_name"):
        a_config(sdk_package="github.com/stripe/stripe-go/v76", package_name=name)


# Spec AC1: the mappings are read-only copies, not the caller's dicts.
def test_the_mappings_are_read_only_copies():
    operations = {"POST /v1/charges": "charge.New"}
    fields = {"ChargeParams.Amount": "AmountCents"}
    config = a_config(
        sdk_package="github.com/stripe/stripe-go/v76",
        operations=operations,
        fields=fields,
    )

    operations["POST /v1/other"] = "other.New"
    fields["ChargeParams.Amount"] = "changed"

    assert dict(config.operations) == {"POST /v1/charges": "charge.New"}
    assert dict(config.fields) == {"ChargeParams.Amount": "AmountCents"}
    with pytest.raises(TypeError):
        config.operations["x"] = "y"
    with pytest.raises(TypeError):
        config.fields["x"] = "y"


def test_the_config_is_frozen_and_slotted():
    config = a_config(sdk_package="github.com/stripe/stripe-go/v76")

    with pytest.raises((AttributeError, TypeError)):
        config.sdk_package = "other"
    assert not hasattr(config, "__dict__")


# Spec AC1: a receiver mapping loads as a read-only copy.
def test_a_receiver_mapping_loads_read_only():
    receivers = {"stripe.NewClient": "Client"}
    config = a_config(
        sdk_package="github.com/stripe/stripe-go/v76", receivers=receivers
    )

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
        a_config(
            sdk_package="github.com/stripe/stripe-go/v76",
            receivers={key: value},
        )
