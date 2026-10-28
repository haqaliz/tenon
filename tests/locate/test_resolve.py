"""Certainty policy: one rule table from query plus scan evidence to a result.

Literal inputs on purpose: every rule is exercised without a filesystem, while
``test_locate.py`` proves the same rules through the public API.
"""

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    Dynamic,
    Hit,
    LocateConfig,
    LocateReason,
    Query,
    ScanResult,
    SiteShape,
)
from tenon.locate.resolve import resolve
from tenon.locate.scan import DynamicKind

CONFIG = LocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGES_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/application~1json/schema/properties"
)


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
