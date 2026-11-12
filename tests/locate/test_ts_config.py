"""The TypeScript locate config and the shared query protocol."""

from types import MappingProxyType
from typing import get_type_hints

import pytest

import tenon.locate.query as query_module
import tenon.locate.resolve as resolve_module
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, TsLocateConfig, derive
from tenon.locate.query import QueryConfig

CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGES_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/application~1json/schema/properties"
)


def a_change(
    kind,
    *,
    before=None,
    after=None,
    pointer=CHARGE_PROPERTIES,
    method=None,
    path=None,
):
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=path),
        before=before,
        after=after,
    )


# Spec AC1: an npm name, scoped or not, constructs.
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("stripe", id="plain"),
        pytest.param("@scope/pkg", id="scoped"),
        pytest.param("left-pad", id="hyphen"),
        pytest.param("sdk.js", id="dot"),
        pytest.param("under_score", id="underscore"),
        pytest.param("sdk2", id="digit"),
        pytest.param("@my-scope/sdk.js", id="scoped_with_punctuation"),
    ],
)
def test_a_valid_npm_package_name_constructs(name):
    config = TsLocateConfig(sdk_package=name)

    assert config.sdk_package == name
    assert config.receivers == {}


# Spec AC1: empty, whitespace, path-like and malformed scopes are rejected.
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param(" stripe", id="leading_space"),
        pytest.param("stripe ", id="trailing_space"),
        pytest.param("strip e", id="inner_space"),
        pytest.param("foo/bar", id="path_like"),
        pytest.param("@scope", id="scope_without_package"),
        pytest.param("@scope/", id="empty_package"),
        pytest.param("@/pkg", id="empty_scope"),
        pytest.param("@scope/pkg/sub", id="subpath"),
        pytest.param("@scope/pk g", id="space_in_package"),
        pytest.param("foo\\bar", id="windows_path"),
    ],
)
def test_an_invalid_npm_package_name_raises_value_error(name):
    with pytest.raises(ValueError):
        TsLocateConfig(sdk_package=name)


# Spec AC1: mappings are immutable copies, like LocateConfig.
def test_the_mappings_are_immutable_copies():
    operations = {"POST /v1/charges": "charges.create"}
    fields = {"Charge.amount": "amount_cents"}

    config = TsLocateConfig(
        sdk_package="stripe", operations=operations, fields=fields
    )
    operations["DELETE /v1/charges/{id}"] = "charges.delete"
    fields["Charge.currency"] = "currency_code"

    assert config.operations == {"POST /v1/charges": "charges.create"}
    assert config.fields == {"Charge.amount": "amount_cents"}
    assert isinstance(config.operations, MappingProxyType)
    assert isinstance(config.fields, MappingProxyType)
    with pytest.raises(TypeError):
        config.operations["POST /v1/charges"] = "other"
    with pytest.raises(TypeError):
        config.fields["Charge.amount"] = "other"


def test_the_config_is_frozen():
    config = TsLocateConfig(sdk_package="stripe")

    with pytest.raises(AttributeError):
        config.sdk_package = "other"


# Spec AC1: a receiver mapping loads as a read-only copy.
def test_a_receiver_mapping_loads_read_only():
    receivers = {"stripe.NewClient": "Client"}
    config = TsLocateConfig(sdk_package="stripe", receivers=receivers)

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
        TsLocateConfig(sdk_package="stripe", receivers={key: value})


# Spec AC2/M2: derive sees the same Query through either config.
def test_derive_returns_the_same_query_for_both_configs():
    change = a_change(
        ChangeKind.RENAMED,
        before="amount",
        after="amount_cents",
        pointer=CHARGES_BODY,
        method="post",
        path="/v1/charges",
    )
    operations = {"POST /v1/charges": "charges.create"}
    fields = {"Charge.amount": "amount_cents"}

    ts_query = derive(
        change,
        TsLocateConfig(
            sdk_package="stripe", operations=operations, fields=fields
        ),
    )
    python_query = derive(
        change,
        LocateConfig(sdk_package="stripe", operations=operations, fields=fields),
    )

    assert ts_query == python_query


# Spec M2: the shared functions name only the two mappings, not a concrete config.
def test_the_shared_query_protocol_covers_both_configs():
    assert set(QueryConfig.__annotations__) == {"operations", "fields"}
    for function in (
        query_module.derive,
        query_module._mapped_operation,
        query_module._mapped_field,
        resolve_module.resolve,
    ):
        assert get_type_hints(function)["config"] is QueryConfig
