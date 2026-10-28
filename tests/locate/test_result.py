import json
import os
import subprocess
import sys

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


def a_group(
    reason=AmbiguityReason.MULTIPLE_CANDIDATES, symbol="amount", candidates=None
):
    return AmbiguousGroup(
        reason=reason, symbol=symbol, candidates=candidates or (a_site(),)
    )


def a_result(certain=(), ambiguous=(), reason=None):
    return LocateResult(
        change=a_change(),
        certain=list(certain),
        ambiguous=list(ambiguous),
        reason=reason,
    )


def some_sites():
    return [
        a_site(path="z.py", line=3, column=1, symbol="delete"),
        a_site(path="a.py", line=9, column=10, symbol="amount"),
        a_site(path="a.py", line=9, column=3, symbol="amount"),
    ]


def some_groups():
    return [
        a_group(
            reason=AmbiguityReason.UNMAPPED_SYMBOL,
            symbol="amount",
            candidates=(a_site(path="b.py"), a_site(path="a.py")),
        ),
        a_group(
            reason=AmbiguityReason.DYNAMIC_KWARGS,
            symbol="zeta",
            candidates=(a_site(path="c.py"),),
        ),
        a_group(
            reason=AmbiguityReason.DYNAMIC_KWARGS,
            symbol="alpha",
            candidates=(a_site(path="d.py"),),
        ),
    ]


# Spec AC4: a reason means "no sites", so a reason with certain sites is an error.
def test_locate_result_rejects_a_reason_with_certain_sites():
    with pytest.raises(ValueError):
        a_result(certain=(a_site(),), reason=LocateReason.NO_SITES)


# Spec AC4: the same for ambiguity groups.
def test_locate_result_rejects_a_reason_with_ambiguous_groups():
    with pytest.raises(ValueError):
        a_result(ambiguous=(a_group(),), reason=LocateReason.NO_SITES)


# Spec AC4: an empty result must name why it is empty.
def test_locate_result_rejects_an_empty_result_without_a_reason():
    with pytest.raises(ValueError):
        a_result()


def test_certain_sites_are_sorted_by_path_line_column_symbol():
    result = a_result(
        certain=some_sites() + [a_site(path="a.py", line=9, column=3, symbol="create")]
    )
    assert isinstance(result.certain, tuple)
    assert [
        (site.path, site.line, site.column, site.symbol) for site in result.certain
    ] == [
        ("a.py", 9, 3, "amount"),
        ("a.py", 9, 3, "create"),
        ("a.py", 9, 10, "amount"),
        ("z.py", 3, 1, "delete"),
    ]


def test_certain_sites_with_identical_coordinates_order_by_shape():
    sites = [a_site(shape=shape) for shape in SHAPES]
    first = a_result(certain=sites)
    second = a_result(certain=list(reversed(sites)))
    assert first.certain == second.certain
    assert [site.shape.value for site in first.certain] == sorted(SHAPES)


def test_ambiguous_groups_and_their_candidates_are_canonically_ordered():
    result = a_result(ambiguous=some_groups())
    assert [(group.reason.value, group.symbol) for group in result.ambiguous] == [
        ("DYNAMIC_KWARGS", "alpha"),
        ("DYNAMIC_KWARGS", "zeta"),
        ("UNMAPPED_SYMBOL", "amount"),
    ]
    unmapped = result.ambiguous[-1]
    assert isinstance(unmapped.candidates, tuple)
    assert [site.path for site in unmapped.candidates] == ["a.py", "b.py"]


# Spec AC2: insertion order must not leak into the serialised bytes.
def test_to_json_is_identical_for_any_insertion_order():
    expected = a_result(some_sites(), some_groups()).to_json()
    reversed_result = a_result(reversed(some_sites()), reversed(some_groups()))
    assert reversed_result.to_json() == expected
    rotated_sites = some_sites()[1:] + some_sites()[:1]
    rotated_groups = some_groups()[1:] + some_groups()[:1]
    assert a_result(rotated_sites, rotated_groups).to_json() == expected


# Spec AC1: every shape survives to_dict() -> JSON as a plain string.
@pytest.mark.parametrize("shape", SHAPES)
def test_site_round_trips_every_shape_through_json(shape):
    result = a_result(certain=(a_site(shape=shape),))
    parsed = json.loads(result.to_json())
    assert parsed == result.to_dict()
    assert parsed["certain"][0]["shape"] == shape


# Spec AC1: every LocateReason is constructible and survives to_dict() -> JSON.
@pytest.mark.parametrize("reason", list(LocateReason))
def test_reason_only_result_round_trips_every_reason(reason):
    result = a_result(reason=reason)
    assert isinstance(result.certain, tuple)
    parsed = json.loads(result.to_json())
    assert parsed == result.to_dict()
    assert parsed["reason"] == reason.value
    assert parsed["certain"] == []
    assert parsed["ambiguous"] == []


# Spec AC1: every AmbiguityReason is constructible and survives to_dict() -> JSON.
@pytest.mark.parametrize("reason", list(AmbiguityReason))
def test_group_round_trips_every_ambiguity_reason(reason):
    result = a_result(ambiguous=(a_group(reason=reason),))
    parsed = json.loads(result.to_json())
    assert parsed == result.to_dict()
    assert parsed["ambiguous"][0]["reason"] == reason.value


# Spec AC3: no tuple, set, enum object or dataclass repr reaches the payload.
def test_to_json_holds_only_json_primitives():
    result = a_result(some_sites(), some_groups())
    text = result.to_json()
    assert json.loads(text) == result.to_dict()
    assert json.loads(text)["reason"] is None
    for leak in (
        "SiteShape.",
        "LocateReason.",
        "AmbiguityReason.",
        "Site(",
        "AmbiguousGroup(",
        "LocateResult(",
        "Change(",
        "Location(",
    ):
        assert leak not in text


SUBPROCESS_SCRIPT = """
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import AmbiguityReason, AmbiguousGroup, LocateResult, Site

certain_sites = [
    Site(path=f"pkg/{name}.py", line=1, column=1, shape=shape, symbol=name)
    for name in {"zeta", "alpha", "mu", "beta"}
    for shape in {"attribute", "call", "keyword"}
]
ambiguous_sites = [
    Site(path=f"other/{name}.py", line=2, column=3, shape=shape, symbol=name)
    for name in {"omega", "gamma"}
    for shape in {"dict_key", "keyword"}
]
groups = [
    AmbiguousGroup(reason=reason, symbol=name, candidates=tuple(ambiguous_sites))
    for reason in {AmbiguityReason.UNROOTED_RECEIVER, AmbiguityReason.DYNAMIC_KWARGS}
    for name in {"zeta", "alpha"}
]
result = LocateResult(
    change=Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer="#"),
        before="amount",
        after="amount_cents",
    ),
    certain=tuple(certain_sites),
    ambiguous=tuple(groups),
)
print(result.to_json(), end="")
"""


def to_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC3: byte-identical output across hash seeds.
def test_to_json_is_byte_stable_across_hash_seeds():
    assert to_json_with_hash_seed("0") == to_json_with_hash_seed("1")
