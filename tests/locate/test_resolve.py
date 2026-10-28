"""Certainty policy: one rule table from query plus scan evidence to a result.

Literal inputs on purpose for the rule matrix; the decoy, alias and unmapped
cases scan the committed fixtures, while ``test_locate.py`` proves the same
rules through the public API.
"""

from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    AmbiguousGroup,
    Dynamic,
    Hit,
    LocateConfig,
    LocateReason,
    Query,
    ScanResult,
    Site,
    SiteShape,
    scan,
)
from tenon.locate.resolve import _build, resolve
from tenon.locate.scan import DynamicKind

CONFIG = LocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
SDK_DECOY = FIXTURES / "sdk-decoy"
SDK_DYNAMIC = FIXTURES / "sdk-dynamic"


def a_change(
    kind=ChangeKind.ENDPOINT_REMOVED,
    *,
    before=None,
    after=None,
    pointer="#/paths",
    method="delete",
    path="/v1/charges/{id}",
):
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=path),
        before=before,
        after=after,
    )


def a_query(**overrides):
    values = {
        "scope": "operation",
        "kind": ChangeKind.ENDPOINT_REMOVED,
        "method": "delete",
        "path": "/v1/charges/{id}",
        "operation_candidates": ("charges.delete",),
        "field_name": None,
        "change_field": None,
        "field_presence": "absent",
        "origin": "inferred",
    }
    values.update(overrides)
    return Query(**values)


def a_scan(*hits, modules=("m.py",), dynamics=()):
    return ScanResult(modules=modules, hits=hits, dynamics=dynamics)


def a_hit(
    path="m.py",
    line=1,
    column=1,
    shape=SiteShape.CALL,
    symbol="delete",
    chain=("charges", "delete"),
    rooted=True,
    line_text=None,
):
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


def a_dynamic(path="m.py", line=1, column=1, kind=DynamicKind.STAR_KWARGS, symbol=None):
    return Dynamic(path, line, column, kind, symbol)


# Phase 1: result-level rules.
def test_an_unsupported_change_passes_its_reason_through():
    change = a_change(
        ChangeKind.ENUM_NARROWED,
        pointer=CHARGE_PROPERTIES,
        method=None,
        path=None,
    )
    query = a_query(
        scope="component",
        kind=ChangeKind.ENUM_NARROWED,
        method=None,
        path=None,
        operation_candidates=(),
        origin="none",
        reason=LocateReason.UNSUPPORTED_CHANGE_KIND,
    )

    result = resolve(change, query, a_scan(modules=()), CONFIG)

    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND
    assert result.certain == ()
    assert result.ambiguous == ()


def test_a_repository_that_never_reaches_the_sdk_has_no_import():
    result = resolve(a_change(), a_query(), a_scan(modules=()), CONFIG)

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


def test_an_operation_without_a_mapping_or_inference_is_not_mapped():
    query = a_query(operation_candidates=(), origin="none")

    result = resolve(a_change(), query, a_scan(), CONFIG)

    assert result.reason is LocateReason.OPERATION_NOT_MAPPED


def test_a_mapped_operation_with_no_rooted_calls_has_no_sites():
    unrooted = a_hit(line=3, column=10, rooted=False)

    result = resolve(a_change(), a_query(), a_scan(unrooted), CONFIG)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


def test_no_sites_and_unsupported_kind_are_distinguishable():
    no_sites = resolve(a_change(), a_query(), a_scan(), CONFIG)
    unsupported = resolve(
        a_change(),
        a_query(reason=LocateReason.UNSUPPORTED_CHANGE_KIND),
        a_scan(),
        CONFIG,
    )

    assert no_sites.reason is not unsupported.reason
    assert no_sites.reason is LocateReason.NO_SITES


# Phase 2: operation scope.
def test_a_single_resolved_operation_call_is_certain():
    call = a_hit(line=6, column=16, symbol="delete")

    result = resolve(a_change(), a_query(), a_scan(call), CONFIG)

    assert result.certain == (Site("m.py", 6, 16, SiteShape.CALL, "delete"),)
    assert result.ambiguous == ()
    assert result.reason is None


def test_two_resolved_operation_candidates_become_one_ambiguous_group():
    query = a_query(
        method="get",
        path="/v1/customers/{id}",
        operation_candidates=("customers.get", "customers.list", "customers.retrieve"),
    )
    get = a_hit(line=5, column=18, symbol="get", chain=("customers", "get"))
    retrieve = a_hit(line=6, column=18, symbol="retrieve", chain=("customers", "retrieve"))

    result = resolve(a_change(), query, a_scan(get, retrieve), CONFIG)

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.MULTIPLE_CANDIDATES
    assert group.symbol == "customers.get"
    assert group.candidates == (
        Site("m.py", 5, 18, SiteShape.CALL, "get"),
        Site("m.py", 6, 18, SiteShape.CALL, "retrieve"),
    )


def test_must_exist_certainty_is_the_matching_rooted_keyword():
    query = a_query(
        kind=ChangeKind.RENAMED,
        method="post",
        path="/v1/charges",
        operation_candidates=("charges.create",),
        field_name="amount",
        change_field="amount",
        field_presence="must_exist",
    )
    call = a_hit(line=5, column=16, symbol="create", chain=("charges", "create"))
    amount = a_hit(
        line=5,
        column=23,
        shape=SiteShape.KEYWORD,
        symbol="amount",
        chain=("charges", "create"),
    )
    currency = a_hit(
        line=5,
        column=38,
        shape=SiteShape.KEYWORD,
        symbol="currency",
        chain=("charges", "create"),
    )
    decoy = a_hit(
        line=9,
        column=8,
        shape=SiteShape.KEYWORD,
        symbol="amount",
        chain=(),
        rooted=False,
    )

    result = resolve(a_change(), query, a_scan(call, amount, currency, decoy), CONFIG)

    assert result.certain == (
        Site("m.py", 5, 23, SiteShape.KEYWORD, "amount"),
    )
    assert result.ambiguous == ()
    assert result.reason is None


def test_must_exist_with_star_kwargs_reports_the_call_site_only():
    query = a_query(
        kind=ChangeKind.RENAMED,
        field_name="amount",
        change_field="amount",
        field_presence="must_exist",
        operation_candidates=("charges.create",),
    )
    call = a_hit(line=7, column=27, symbol="create", chain=("charges", "create"))

    result = resolve(
        a_change(), query, a_scan(call, dynamics=(a_dynamic(line=7, column=34),)), CONFIG
    )

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_KWARGS
    assert group.symbol == "amount"
    assert group.candidates == (Site("m.py", 7, 27, SiteShape.CALL, "create"),)


def test_must_be_added_marks_the_resolved_call_sites_certain():
    query = a_query(
        kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
        field_name="idempotency_key",
        change_field="idempotency_key",
        field_presence="must_be_added",
        operation_candidates=("charges.create",),
    )
    first = a_hit(line=5, column=16, symbol="create", chain=("charges", "create"))
    second = a_hit(line=9, column=16, symbol="create", chain=("charges", "create"))

    result = resolve(a_change(), query, a_scan(first, second), CONFIG)

    assert result.certain == (
        Site("m.py", 5, 16, SiteShape.CALL, "create"),
        Site("m.py", 9, 16, SiteShape.CALL, "create"),
    )
    assert result.ambiguous == ()


def test_must_be_added_keeps_an_already_present_field_certain():
    query = a_query(
        kind=ChangeKind.PROPERTY_REQUIRED_ADDED,
        field_name="currency",
        change_field="currency",
        field_presence="must_be_added",
        operation_candidates=("charges.create",),
    )
    call = a_hit(line=5, column=16, symbol="create", chain=("charges", "create"))
    currency = a_hit(
        line=5,
        column=38,
        shape=SiteShape.KEYWORD,
        symbol="currency",
        chain=("charges", "create"),
    )

    result = resolve(a_change(), query, a_scan(call, currency), CONFIG)

    assert result.certain == (
        Site("m.py", 5, 16, SiteShape.CALL, "create"),
        Site("m.py", 5, 38, SiteShape.KEYWORD, "currency"),
    )


def test_an_unresolved_operation_with_getattr_naming_its_leaf_is_dynamic():
    getattr = a_dynamic(line=3, column=12, kind=DynamicKind.GETATTR, symbol="delete")

    result = resolve(a_change(), a_query(), a_scan(dynamics=(getattr,)), CONFIG)

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_GETATTR
    assert group.symbol == "delete"
    assert group.candidates == (Site("m.py", 3, 12, SiteShape.ATTRIBUTE, "delete"),)


def test_a_getattr_without_a_name_is_not_attributed_to_a_field():
    unnamed = a_dynamic(kind=DynamicKind.GETATTR, symbol=None)

    result = resolve(a_change(), a_query(), a_scan(dynamics=(unnamed,)), CONFIG)

    assert result.reason is LocateReason.NO_SITES


def test_a_site_cannot_be_certain_and_a_candidate():
    site = Site("m.py", 1, 1, SiteShape.CALL, "delete")
    group = AmbiguousGroup(
        AmbiguityReason.MULTIPLE_CANDIDATES, "delete", (site,)
    )

    with pytest.raises(AssertionError):
        _build(a_change(), certain=(site,), groups=(group,))


# Phase 3: component scope and the decoy.
def a_component_query(field_name, *, change_field=None, origin="inferred"):
    return a_query(
        scope="component",
        kind=ChangeKind.RENAMED,
        method=None,
        path=None,
        operation_candidates=(),
        field_name=field_name,
        change_field=field_name if change_field is None else change_field,
        field_presence="must_exist",
        origin=origin,
    )


def test_a_rooted_component_field_is_certain():
    change = a_change(
        ChangeKind.RENAMED,
        before="amount",
        pointer=CHARGE_PROPERTIES,
        method=None,
        path=None,
    )

    result = resolve(
        change, a_component_query("amount"), scan(SDK_BASIC, "stripe"), CONFIG
    )

    assert [
        (site.path, site.line, site.column, site.shape)
        for site in result.certain
    ] == [("acme/billing.py", 5, 23, SiteShape.KEYWORD)]
    assert result.ambiguous == ()
    assert result.reason is None


def test_the_decoy_keyword_is_never_certain():
    scan_result = scan(SDK_DECOY, "stripe")

    result = resolve(
        a_change(pointer=CHARGE_PROPERTIES, method=None, path=None),
        a_component_query("amount"),
        scan_result,
        CONFIG,
    )

    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("acme/mixed.py", 11, 23)
    ]
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert [(site.path, site.line, site.column) for site in group.candidates] == [
        ("acme/mixed.py", 10, 8)
    ]
    # The release gate: the unrooted call is the only `amount=` on line 10 and
    # may never be reported as certain, whatever else the result contains.
    assert all(site.line != 10 for site in result.certain)


def test_a_field_named_like_a_method_is_not_a_component_site():
    result = resolve(
        a_change(pointer=CHARGE_PROPERTIES, method=None, path=None),
        a_component_query("delete"),
        scan(SDK_BASIC, "stripe"),
        CONFIG,
    )

    assert result.certain == ()
    assert result.reason is LocateReason.NO_SITES


def test_an_alias_chain_for_the_field_is_a_group_not_a_site():
    result = resolve(
        a_change(pointer=CHARGE_PROPERTIES, method=None, path=None),
        a_component_query("d"),
        scan(SDK_DYNAMIC, "stripe"),
        CONFIG,
    )

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.ALIAS_CHAIN
    assert group.symbol == "d"
    assert group.candidates == (
        Site("acme/flows.py", 17, 1, SiteShape.ATTRIBUTE, "d"),
    )


def test_a_mapped_spelling_absent_from_the_repo_names_the_repo_spelling():
    result = resolve(
        a_change(pointer=CHARGE_PROPERTIES, method=None, path=None),
        a_component_query("amount_cents", change_field="amount", origin="mapping"),
        scan(SDK_BASIC, "stripe"),
        CONFIG,
    )

    assert result.certain == ()
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNMAPPED_SYMBOL
    assert group.symbol == "amount"
    assert [(site.path, site.line, site.column) for site in group.candidates] == [
        ("acme/billing.py", 5, 23)
    ]


def test_without_the_mapping_the_different_spelling_is_no_sites():
    query = a_component_query("amount_cents", change_field="amount", origin="inferred")

    result = resolve(
        a_change(pointer=CHARGE_PROPERTIES, method=None, path=None),
        query,
        scan(SDK_BASIC, "stripe"),
        CONFIG,
    )

    assert result.reason is LocateReason.NO_SITES
    assert result.ambiguous == ()
