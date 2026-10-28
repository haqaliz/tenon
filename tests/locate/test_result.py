import json

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    AmbiguousGroup,
    LocateConfig,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
)

SHAPES = ["call", "keyword", "dict_key", "attribute"]


def a_site(**overrides):
    values = {
        "path": "billing.py",
        "line": 42,
        "column": 25,
        "shape": "keyword",
        "symbol": "amount",
    }
    values.update(overrides)
    return Site(**values)


def a_change():
    return Change(
        kind=ChangeKind.PROPERTY_REMOVED,
        location=Location(pointer="#/components/schemas/Charge"),
        before={"name": "amount", "type": "integer"},
    )


# Spec AC1: every shape is constructible, stored as a string enum, and JSON-safe.
@pytest.mark.parametrize("shape", SHAPES)
def test_site_accepts_every_shape(shape):
    site = a_site(shape=shape)
    assert site.shape is SiteShape(shape)
    assert json.loads(json.dumps(site.shape)) == shape


def test_site_keeps_line_text_optional():
    assert a_site().line_text is None
    assert a_site(line_text="create(amount=1)").line_text == "create(amount=1)"


# Spec AC6: an empty sdk_package is a ValueError.
def test_locate_config_rejects_an_empty_sdk_package():
    with pytest.raises(ValueError):
        LocateConfig(sdk_package="")


@pytest.mark.parametrize(
    "package", [" stripe", "stripe.", "stripe..charges", "9stripe", "stripe charges"]
)
def test_locate_config_rejects_a_malformed_sdk_package(package):
    with pytest.raises(ValueError):
        LocateConfig(sdk_package=package)


def test_locate_config_accepts_a_dotted_package_with_empty_mappings():
    config = LocateConfig(sdk_package="google.cloud.storage")
    assert config.sdk_package == "google.cloud.storage"
    assert config.operations == {}
    assert config.fields == {}


def test_locate_config_mappings_cannot_be_mutated():
    config = LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.delete"},
        fields={"Charge.amount": "amount_cents"},
    )
    with pytest.raises(TypeError):
        config.operations["GET /v1/charges"] = "charges.list"
    with pytest.raises(TypeError):
        config.fields["Charge.id"] = "charge_id"


# Spec AC1: every reason value is reachable and spelled exactly as the contract says.
def test_locate_reason_values_are_the_closed_four():
    assert [reason.value for reason in LocateReason] == [
        "UNSUPPORTED_CHANGE_KIND",
        "NO_SDK_IMPORT",
        "OPERATION_NOT_MAPPED",
        "NO_SITES",
    ]


def test_ambiguity_reason_values_are_the_closed_six():
    assert [reason.value for reason in AmbiguityReason] == [
        "DYNAMIC_KWARGS",
        "DYNAMIC_GETATTR",
        "ALIAS_CHAIN",
        "UNROOTED_RECEIVER",
        "MULTIPLE_CANDIDATES",
        "UNMAPPED_SYMBOL",
    ]


# Spec AC5: a group with zero candidates raises ValueError.
def test_ambiguous_group_rejects_zero_candidates():
    with pytest.raises(ValueError):
        AmbiguousGroup(
            reason=AmbiguityReason.DYNAMIC_KWARGS, symbol="amount", candidates=()
        )


def test_locate_result_carries_a_change_and_a_named_reason():
    result = LocateResult(
        change=a_change(), certain=(), ambiguous=(), reason=LocateReason.NO_SITES
    )
    assert result.change.kind is ChangeKind.PROPERTY_REMOVED
    assert result.reason is LocateReason.NO_SITES
