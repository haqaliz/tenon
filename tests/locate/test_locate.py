"""The public locate API over the committed fixture repositories."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import tenon.locate.resolve as resolve_module
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    LocateConfig,
    LocateReason,
    Site,
    SiteShape,
    locate,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
SDK_DECOY = FIXTURES / "sdk-decoy"
SDK_DYNAMIC = FIXTURES / "sdk-dynamic"
SDK_MULTIPLE = FIXTURES / "sdk-multiple"
STRIPE = LocateConfig(sdk_package="stripe")

CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGES_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/application~1json/schema/properties"
)
CHARGES_PARAMS = "#/paths/~1v1~1charges/post/parameters"


def a_change(
    kind,
    *,
    before=None,
    after=None,
    pointer="#/paths",
    method=None,
    path=None,
):
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=path),
        before=before,
        after=after,
    )


def payload(name):
    return {"name": name, "type": "string"}


def a_repo(tmp_path, source):
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    return tmp_path


# Phase 4: derive -> scan -> resolve through locate().
def test_a_component_rename_finds_the_rooted_keyword():
    change = a_change(ChangeKind.RENAMED, before="amount", pointer=CHARGE_PROPERTIES)

    result = locate(change, SDK_BASIC, STRIPE)

    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("acme/billing.py", 5, 23)
    ]
    assert result.certain[0].shape is SiteShape.KEYWORD
    # line_text can only come from the real scan, so the wiring is not faked.
    assert (
        result.certain[0].line_text
        == 'client.charges.create(amount=amount, currency="usd")'
    )
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC2: an operation-scoped rename is certain at the argument.
def test_an_operation_rename_finds_the_argument():
    change = a_change(
        ChangeKind.RENAMED,
        before="amount",
        pointer=CHARGES_BODY,
        method="post",
        path="/v1/charges",
    )

    result = locate(change, SDK_BASIC, STRIPE)

    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("acme/billing.py", 5, 23)
    ]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC1: the release gate, through the public API.
def test_the_decoy_is_never_certain():
    change = a_change(ChangeKind.RENAMED, before="amount", pointer=CHARGE_PROPERTIES)

    result = locate(change, SDK_DECOY, STRIPE)

    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("acme/mixed.py", 11, 23)
    ]
    assert len(result.ambiguous) == 1
    assert result.ambiguous[0].reason is AmbiguityReason.UNROOTED_RECEIVER
    assert [
        (site.path, site.line, site.column) for site in result.ambiguous[0].candidates
    ] == [("acme/mixed.py", 10, 8)]
    assert all(site.line != 10 for site in result.certain)


# Spec AC3: **kwargs hides the field, so only the call site is a candidate.
def test_star_kwargs_yields_a_dynamic_group_without_certainty(tmp_path):
    repo = a_repo(
        tmp_path,
        'from stripe import Stripe\n\nclient = Stripe()\n'
        "client.charges.create(**row)\n",
    )

    result = locate(
        a_change(
            ChangeKind.RENAMED,
            before="amount",
            pointer=CHARGES_BODY,
            method="post",
            path="/v1/charges",
        ),
        repo,
        STRIPE,
    )

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_KWARGS
    assert group.symbol == "amount"
    assert [
        (candidate.path, candidate.line, candidate.column, candidate.shape)
        for candidate in group.candidates
    ] == [("app.py", 4, 16, SiteShape.CALL)]


# Spec AC4: getattr is never a certain site, even with an explicit mapping.
def test_getattr_is_dynamic_and_never_certain(tmp_path):
    repo = a_repo(
        tmp_path,
        'from stripe import Stripe\n\nclient = Stripe()\n'
        'getattr(client.charges, "delete")("ch_1")\n',
    )
    config = LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.delete"},
    )

    result = locate(
        a_change(
            ChangeKind.ENDPOINT_REMOVED,
            before="/v1/charges/{id}",
            method="delete",
            path="/v1/charges/{id}",
        ),
        repo,
        config,
    )

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_GETATTR
    assert group.symbol == "delete"
    assert group.candidates == (
        Site("app.py", 4, 1, SiteShape.ATTRIBUTE, "delete"),
    )


# Spec AC5: both inferred candidates resolve, so both sites are kept.
def test_two_resolving_candidates_are_one_group():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        before="/v1/customers/{id}",
        method="get",
        path="/v1/customers/{id}",
    )

    result = locate(change, SDK_MULTIPLE, STRIPE)

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.MULTIPLE_CANDIDATES
    assert [
        (site.path, site.line, site.symbol) for site in group.candidates
    ] == [
        ("acme/clients.py", 5, "get"),
        ("acme/clients.py", 6, "retrieve"),
    ]


# Spec AC6: an added required parameter points at the calls to fix.
def test_a_required_parameter_returns_the_resolved_calls_as_certain():
    change = a_change(
        ChangeKind.PARAMETER_REQUIRED_ADDED,
        after=payload("idempotency_key"),
        pointer=CHARGES_PARAMS,
        method="post",
        path="/v1/charges",
    )

    result = locate(change, SDK_BASIC, STRIPE)

    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("acme/billing.py", 5, 16)
    ]
    assert result.certain[0].shape is SiteShape.CALL
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC7: unsupported kind and no sites are different named answers.
def test_an_unsupported_kind_short_circuits_without_scanning(monkeypatch):
    def no_scan(*args, **kwargs):
        raise AssertionError("an unsupported kind must not scan")

    monkeypatch.setattr(resolve_module, "scan", no_scan)
    change = a_change(
        ChangeKind.ENUM_NARROWED,
        before={"name": "status", "enum": ["open", "closed"]},
        after={"name": "status", "enum": ["open"]},
        pointer=CHARGE_PROPERTIES,
    )

    result = locate(change, SDK_BASIC, STRIPE)

    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND
    assert result.certain == ()
    assert result.ambiguous == ()


def test_a_change_with_no_matching_sites_has_no_sites():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED,
        before=payload("nonexistent"),
        pointer=CHARGE_PROPERTIES,
    )

    result = locate(change, SDK_BASIC, STRIPE)

    assert result.reason is LocateReason.NO_SITES
    assert result.reason is not LocateReason.UNSUPPORTED_CHANGE_KIND


def test_a_repository_without_the_sdk_has_no_import(tmp_path):
    repo = a_repo(tmp_path, "print('hello')\n")
    change = a_change(ChangeKind.RENAMED, before="amount", pointer=CHARGE_PROPERTIES)

    result = locate(change, repo, STRIPE)

    assert result.reason is LocateReason.NO_SDK_IMPORT


# Spec AC8: same inputs, byte-identical JSON.
def test_two_runs_produce_identical_json():
    change = a_change(ChangeKind.RENAMED, before="amount", pointer=CHARGE_PROPERTIES)

    first = locate(change, SDK_BASIC, STRIPE).to_json()
    second = locate(change, SDK_BASIC, STRIPE).to_json()

    assert first == second


SUBPROCESS_SCRIPT = """
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, locate

change = Change(
    kind=ChangeKind.RENAMED,
    location=Location(pointer="#/components/schemas/Charge/properties"),
    before="amount",
    after="amount_cents",
)
print(locate(change, {repo!r}, LocateConfig(sdk_package="stripe")).to_json(), end="")
"""


def locate_with_hash_seed(seed):
    script = SUBPROCESS_SCRIPT.format(repo=str(SDK_BASIC))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_locate_is_identical_across_hash_seeds():
    assert locate_with_hash_seed("0") == locate_with_hash_seed("1")


# Spec AC9: every supported kind and shape produces a contract-valid result.
KINDS = (
    ChangeKind.ENDPOINT_REMOVED,
    ChangeKind.ENDPOINT_ADDED,
    ChangeKind.RENAMED,
    ChangeKind.PROPERTY_REMOVED,
    ChangeKind.PROPERTY_ADDED,
    ChangeKind.PROPERTY_REQUIRED_ADDED,
    ChangeKind.PROPERTY_TYPE_CHANGED,
    ChangeKind.PARAMETER_REMOVED,
    ChangeKind.PARAMETER_REQUIRED_ADDED,
    ChangeKind.PARAMETER_TYPE_CHANGED,
)

SHAPES = (
    SiteShape.CALL,
    SiteShape.KEYWORD,
    SiteShape.DICT_KEY,
    SiteShape.ATTRIBUTE,
)


def a_change_for(kind, shape):
    if kind is ChangeKind.ENDPOINT_REMOVED:
        return a_change(
            kind,
            before="/v1/charges/{id}",
            method="delete",
            path="/v1/charges/{id}",
        )
    if kind is ChangeKind.ENDPOINT_ADDED:
        return a_change(
            kind,
            after="/v1/charges",
            method="post",
            path="/v1/charges",
        )
    if kind is ChangeKind.RENAMED:
        return a_change(kind, before="amount", after="amount_cents", pointer=CHARGE_PROPERTIES)
    if kind.name.startswith("PARAMETER_"):
        return a_change(
            kind,
            before=payload("amount"),
            after=payload("amount"),
            pointer=CHARGES_PARAMS,
            method="post",
            path="/v1/charges",
        )
    return a_change(kind, before=payload("amount"), after=payload("amount"), pointer=CHARGE_PROPERTIES)


def a_repo_for(shape):
    """The fixture that carries evidence in that shape for the queried names."""
    return {
        SiteShape.CALL: SDK_BASIC,
        SiteShape.KEYWORD: SDK_BASIC,
        SiteShape.DICT_KEY: SDK_DYNAMIC,
        SiteShape.ATTRIBUTE: SDK_DYNAMIC,
    }[shape]


@pytest.mark.parametrize("kind", KINDS, ids=lambda kind: kind.value)
@pytest.mark.parametrize("shape", SHAPES, ids=lambda shape: shape.value)
def test_every_supported_kind_and_shape_returns_a_valid_result(kind, shape):
    result = locate(a_change_for(kind, shape), a_repo_for(shape), STRIPE)

    if result.reason is not None:
        assert isinstance(result.reason, LocateReason)
        assert result.certain == ()
        assert result.ambiguous == ()
    else:
        assert result.certain or result.ambiguous

    certain_keys = {
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    }
    for group in result.ambiguous:
        assert isinstance(group.reason, AmbiguityReason)
        assert group.symbol
        assert group.candidates
        for candidate in group.candidates:
            assert candidate.shape in SHAPES
            assert (
                candidate.path,
                candidate.line,
                candidate.column,
                candidate.shape,
                candidate.symbol,
            ) not in certain_keys
    for site in result.certain:
        assert site.shape in SHAPES


def test_locate_never_modifies_the_scanned_tree():
    def snapshot():
        return {
            path.relative_to(SDK_BASIC).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in SDK_BASIC.rglob("*")
            if path.is_file()
        }

    before = snapshot()

    locate(
        a_change(ChangeKind.RENAMED, before="amount", pointer=CHARGE_PROPERTIES),
        SDK_BASIC,
        STRIPE,
    )

    assert snapshot() == before
