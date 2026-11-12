"""The C# locate config: a namespace root and the shared mappings."""

import pytest

from tenon.locate.csharp_config import CSharpLocateConfig


def a_config(**kwargs):
    return CSharpLocateConfig(**kwargs)


# Spec AC1: a valid dotted namespace loads with empty mappings.
def test_a_valid_namespace_loads():
    config = a_config(sdk_package="Stripe")

    assert config.sdk_package == "Stripe"
    assert config.operations == {}
    assert config.fields == {}
    assert config.receivers == {}


# Spec AC1: a dotted root and underscore segments are namespaces too.
def test_a_dotted_namespace_loads():
    config = a_config(sdk_package="Stripe.Services")

    assert config.sdk_package == "Stripe.Services"


# Spec AC1: a blank, whitespace, path or `::` root is a named ValueError.
@pytest.mark.parametrize(
    "root",
    [
        "",
        " ",
        "Stripe Services",
        " Stripe",
        "Stripe ",
        "Stripe.Services.",
        ".Stripe",
        "/Stripe",
        "Stripe/Services",
        "Stripe::Services",
        "9Stripe",
    ],
)
def test_an_invalid_namespace_is_a_named_value_error(root):
    with pytest.raises(ValueError, match="sdk_package"):
        a_config(sdk_package=root)


# Spec AC1: the mappings are read-only copies, not the caller's dicts.
def test_the_mappings_are_read_only_copies():
    operations = {"POST /v1/charges": "ChargeService.Create"}
    fields = {"ChargeCreateOptions.AmountCents": "AmountCents"}
    config = a_config(
        sdk_package="Stripe",
        operations=operations,
        fields=fields,
    )

    operations["POST /v1/other"] = "OtherService.Create"
    fields["ChargeCreateOptions.AmountCents"] = "changed"

    assert dict(config.operations) == {"POST /v1/charges": "ChargeService.Create"}
    assert dict(config.fields) == {"ChargeCreateOptions.AmountCents": "AmountCents"}
    with pytest.raises(TypeError):
        config.operations["x"] = "y"
    with pytest.raises(TypeError):
        config.fields["x"] = "y"


def test_the_config_is_frozen_and_slotted():
    config = a_config(sdk_package="Stripe")

    with pytest.raises((AttributeError, TypeError)):
        config.sdk_package = "Other"
    assert not hasattr(config, "__dict__")


# Spec AC1: a receiver mapping loads as a read-only copy.
def test_a_receiver_mapping_loads_read_only():
    receivers = {"stripe.NewClient": "Client"}
    config = a_config(sdk_package="Stripe", receivers=receivers)

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
        a_config(sdk_package="Stripe", receivers={key: value})
