import os
import subprocess
import sys

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, LocateReason, Query, derive

CONFIG = LocateConfig(sdk_package="stripe")

CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGES_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/application~1json/schema/properties"
)
CHARGES_PARAMS = "#/paths/~1v1~1charges/get/parameters"


def payload(name, type_="string", fmt=None, where=None):
    data = {"name": name, "type": type_, "format": fmt}
    if where is not None:
        data["in"] = where
    return data


def a_change(
    kind, *, before=None, after=None, pointer=CHARGE_PROPERTIES, method=None, path=None
):
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=path),
        before=before,
        after=after,
    )


# Spec AC1: all 13 kinds, realistic T1 payloads, never an exception.
@pytest.mark.parametrize(
    "change, expected",
    [
        pytest.param(
            a_change(
                ChangeKind.ENDPOINT_REMOVED,
                pointer="#/paths",
                before="/v1/charges/{id}",
                method="delete",
                path="/v1/charges/{id}",
            ),
            {
                "scope": "operation",
                "field_name": None,
                "change_field": None,
                "field_presence": "absent",
                "reason": None,
            },
            id="endpoint_removed",
        ),
        pytest.param(
            a_change(
                ChangeKind.ENDPOINT_ADDED,
                pointer="#/paths",
                after="/v1/charges",
                method="post",
                path="/v1/charges",
            ),
            {
                "scope": "operation",
                "field_name": None,
                "change_field": None,
                "field_presence": "absent",
                "reason": None,
            },
            id="endpoint_added",
        ),
        pytest.param(
            a_change(
                ChangeKind.PARAMETER_REMOVED,
                pointer=CHARGES_PARAMS,
                method="get",
                path="/v1/charges",
                before=payload("limit", "integer", where="query"),
            ),
            {
                "scope": "operation",
                "field_name": "limit",
                "change_field": "limit",
                "field_presence": "must_exist",
                "reason": None,
            },
            id="parameter_removed",
        ),
        pytest.param(
            a_change(
                ChangeKind.PARAMETER_REQUIRED_ADDED,
                pointer=CHARGES_PARAMS,
                method="get",
                path="/v1/charges",
                after=payload("expand", where="query"),
            ),
            {
                "scope": "operation",
                "field_name": "expand",
                "change_field": "expand",
                "field_presence": "must_be_added",
                "reason": None,
            },
            id="parameter_required_added",
        ),
        pytest.param(
            a_change(
                ChangeKind.PARAMETER_TYPE_CHANGED,
                pointer=CHARGES_PARAMS,
                method="get",
                path="/v1/charges",
                before=payload("limit", "integer", where="query"),
                after=payload("limit", "string", where="query"),
            ),
            {
                "scope": "operation",
                "field_name": "limit",
                "change_field": "limit",
                "field_presence": "must_exist",
                "reason": None,
            },
            id="parameter_type_changed",
        ),
        pytest.param(
            a_change(
                ChangeKind.PROPERTY_REMOVED, before=payload("amount", "integer")
            ),
            {
                "scope": "component",
                "field_name": "amount",
                "change_field": "amount",
                "field_presence": "must_exist",
                "reason": None,
            },
            id="property_removed",
        ),
        pytest.param(
            a_change(ChangeKind.PROPERTY_ADDED, after=payload("nickname")),
            {
                "scope": "component",
                "field_name": "nickname",
                "change_field": "nickname",
                "field_presence": "must_be_added",
                "reason": None,
            },
            id="property_added",
        ),
        pytest.param(
            a_change(ChangeKind.PROPERTY_REQUIRED_ADDED, after=payload("currency")),
            {
                "scope": "component",
                "field_name": "currency",
                "change_field": "currency",
                "field_presence": "must_be_added",
                "reason": None,
            },
            id="property_required_added",
        ),
        pytest.param(
            a_change(
                ChangeKind.PROPERTY_TYPE_CHANGED,
                before=payload("amount", "integer"),
                after=payload("amount", "string"),
            ),
            {
                "scope": "component",
                "field_name": "amount",
                "change_field": "amount",
                "field_presence": "must_exist",
                "reason": None,
            },
            id="property_type_changed",
        ),
        pytest.param(
            a_change(
                ChangeKind.ENUM_NARROWED,
                before={"enum": ["open", "closed"], "name": "status"},
                after={"enum": ["open"], "name": "status"},
            ),
            {
                "scope": "component",
                "field_name": None,
                "change_field": None,
                "field_presence": "absent",
                "reason": LocateReason.UNSUPPORTED_CHANGE_KIND,
            },
            id="enum_narrowed",
        ),
        pytest.param(
            a_change(
                ChangeKind.SCHEMA_REMOVED, pointer="#/components/schemas", before="Old"
            ),
            {
                "scope": "component",
                "field_name": None,
                "change_field": None,
                "field_presence": "absent",
                "reason": LocateReason.UNSUPPORTED_CHANGE_KIND,
            },
            id="schema_removed",
        ),
        pytest.param(
            a_change(
                ChangeKind.SCHEMA_ADDED, pointer="#/components/schemas", after="New"
            ),
            {
                "scope": "component",
                "field_name": None,
                "change_field": None,
                "field_presence": "absent",
                "reason": LocateReason.UNSUPPORTED_CHANGE_KIND,
            },
            id="schema_added",
        ),
        pytest.param(
            a_change(ChangeKind.RENAMED, before="amount", after="amount_cents"),
            {
                "scope": "component",
                "field_name": "amount",
                "change_field": "amount",
                "field_presence": "must_exist",
                "reason": None,
            },
            id="renamed",
        ),
    ],
)
def test_every_change_kind_yields_a_query_or_a_named_reason(change, expected):
    query = derive(change, CONFIG)

    assert isinstance(query, Query)
    assert query.kind is change.kind
    assert query.scope == expected["scope"]
    assert query.field_name == expected["field_name"]
    assert query.change_field == expected["change_field"]
    assert query.field_presence == expected["field_presence"]
    assert query.reason is expected["reason"]


# Spec §parameter_required_added: the existing item only became required.
def test_a_property_that_merely_became_required_is_a_field_query():
    change = a_change(
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        before=payload("currency"),
        after=payload("currency"),
    )

    query = derive(change, CONFIG)

    assert query.scope == "component"
    assert query.field_name == "currency"
    assert query.change_field == "currency"
    assert query.field_presence == "must_be_added"


def test_a_renamed_property_under_an_operation_keeps_the_operation_scope():
    change = a_change(
        ChangeKind.RENAMED,
        pointer=CHARGES_BODY,
        method="post",
        path="/v1/charges",
        before="amount",
        after="amount_cents",
    )

    query = derive(change, CONFIG)

    assert query.scope == "operation"
    assert query.field_name == "amount"
    assert query.change_field == "amount"


# Spec edge case: an endpoint rename has no field; the old path is for reporting.
def test_a_renamed_endpoint_has_no_field_name_and_reports_the_old_path():
    change = a_change(
        ChangeKind.RENAMED,
        pointer="#/paths",
        method="get",
        path="/v2/users",
        before="/v1/users",
        after="/v2/users",
    )

    query = derive(change, CONFIG)

    assert query.scope == "operation"
    assert query.method == "get"
    assert query.path == "/v2/users"
    assert query.field_name is None
    assert query.change_field == "/v1/users"
    assert query.field_presence == "absent"


MALFORMED = [
    pytest.param(
        a_change(ChangeKind.PROPERTY_REMOVED, before=None),
        id="property_removed_without_before",
    ),
    pytest.param(
        a_change(ChangeKind.PROPERTY_REMOVED, before={"type": "string"}),
        id="property_removed_without_name",
    ),
    pytest.param(
        a_change(ChangeKind.PROPERTY_REMOVED, before="amount"),
        id="property_removed_before_is_a_string",
    ),
    pytest.param(
        a_change(ChangeKind.PROPERTY_REMOVED, before={"name": 42}),
        id="property_removed_name_is_not_a_string",
    ),
    pytest.param(
        a_change(ChangeKind.PROPERTY_ADDED, after=None),
        id="property_added_without_after",
    ),
    pytest.param(
        a_change(ChangeKind.PROPERTY_ADDED, after=["amount"]),
        id="property_added_after_is_a_list",
    ),
    pytest.param(
        a_change(
            ChangeKind.PARAMETER_REMOVED,
            pointer=CHARGES_PARAMS,
            method="get",
            path="/v1/charges",
            before=["limit"],
        ),
        id="parameter_removed_before_is_a_list",
    ),
    pytest.param(
        a_change(ChangeKind.RENAMED, before=None, after="amount_cents"),
        id="renamed_without_before",
    ),
    pytest.param(
        a_change(ChangeKind.RENAMED, before="", after="amount_cents"),
        id="renamed_with_an_empty_before",
    ),
]


# Spec AC1: a malformed payload is a named non-result, never KeyError/AttributeError.
@pytest.mark.parametrize("change", MALFORMED)
def test_a_malformed_payload_is_unsupported_never_an_exception(change):
    query = derive(change, CONFIG)

    assert query.reason is LocateReason.UNSUPPORTED_CHANGE_KIND
    assert query.field_name is None
    assert query.change_field is None
    assert query.field_presence == "absent"


def test_query_is_frozen():
    query = derive(
        a_change(ChangeKind.PROPERTY_REMOVED, before=payload("amount")), CONFIG
    )

    with pytest.raises(AttributeError):
        query.field_name = "other"


# Spec AC2: an explicit operation mapping wins for an endpoint change.
def test_an_explicit_operation_mapping_resolves_an_endpoint_change():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/v1/charges/{id}",
        method="delete",
        path="/v1/charges/{id}",
    )
    config = LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.remove"},
    )

    query = derive(change, config)

    assert query.operation_candidates == ("charges.remove",)
    assert query.origin == "mapping"


# Spec AC2: the exact METHOD /path key matches whatever the method's case.
@pytest.mark.parametrize(
    "key, method",
    [
        pytest.param("DELETE /v1/charges/{id}", "delete", id="uppercase_key"),
        pytest.param("delete /v1/charges/{id}", "DELETE", id="lowercase_key"),
    ],
)
def test_operation_mapping_method_match_is_case_insensitive(key, method):
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/v1/charges/{id}",
        method=method,
        path="/v1/charges/{id}",
    )

    query = derive(
        change, LocateConfig(sdk_package="stripe", operations={key: "charges.delete"})
    )

    assert query.operation_candidates == ("charges.delete",)
    assert query.origin == "mapping"


# Spec AC2: the mapped Python name replaces the spec name, which stays for reporting.
def test_an_explicit_field_mapping_renames_the_python_field():
    change = a_change(ChangeKind.PROPERTY_REMOVED, before=payload("amount", "integer"))
    config = LocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    query = derive(change, config)

    assert query.field_name == "amount_cents"
    assert query.change_field == "amount"
    assert query.origin == "mapping"


# Spec AC2: a mapping for one schema must not apply to another.
def test_a_field_mapping_does_not_bleed_into_another_schema():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED,
        pointer="#/components/schemas/Customer/properties",
        before=payload("amount", "integer"),
    )
    config = LocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    query = derive(change, config)

    assert query.field_name == "amount"
    assert query.origin == "inferred"


# Plan §Phase 2: RFC 6901 tokens are unescaped before the mapping lookup.
def test_the_schema_name_is_unescaped_from_the_pointer():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED,
        pointer="#/components/schemas/My~1Schema/properties",
        before=payload("amount", "integer"),
    )
    config = LocateConfig(
        sdk_package="stripe", fields={"My/Schema.amount": "amount_cents"}
    )

    query = derive(change, config)

    assert query.field_name == "amount_cents"
    assert query.origin == "mapping"


def test_a_field_mapping_uses_the_old_name_of_a_rename():
    change = a_change(ChangeKind.RENAMED, before="amount", after="amount_cents")
    config = LocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    query = derive(change, config)

    assert query.field_name == "amount_cents"
    assert query.change_field == "amount"
    assert query.origin == "mapping"


def test_an_unmapped_field_keeps_the_spec_name_verbatim():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED, before=payload("amountCents", "integer")
    )

    query = derive(change, CONFIG)

    assert query.field_name == "amountCents"
    assert query.origin == "inferred"


# Plan edge case: a pointer outside components/schemas skips the mapping, never crashes.
def test_a_pointer_outside_components_schemas_skips_the_field_mapping():
    change = a_change(
        ChangeKind.PROPERTY_REMOVED,
        pointer="#/definitions/Charge/properties",
        before=payload("amount", "integer"),
    )
    config = LocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    query = derive(change, config)

    assert query.field_name == "amount"
    assert query.origin == "inferred"


# Spec AC3: the exact candidates and their order, not a set.
@pytest.mark.parametrize(
    "method, path, expected",
    [
        pytest.param(
            "delete", "/v1/charges/{id}", ("charges.delete",), id="delete"
        ),
        pytest.param(
            "GET",
            "/v1/customers/{id}",
            ("customers.get", "customers.list", "customers.retrieve"),
            id="get",
        ),
        pytest.param(
            "post",
            "/v2/files/{id}/refunds",
            ("files.refunds.create",),
            id="post_keeps_intermediate_segment",
        ),
        pytest.param("put", "/v1/charges/{id}", ("charges.update",), id="put"),
        pytest.param(
            "patch", "/v1/charges/{id}", ("charges.update",), id="patch"
        ),
    ],
)
def test_operation_candidates_are_inferred_from_path_and_verb(method, path, expected):
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before=path,
        method=method,
        path=path,
    )

    query = derive(change, CONFIG)

    assert query.operation_candidates == expected
    assert query.origin == "inferred"


# Plan §Phase 3: one-segment path with a verb name is still a candidate.
def test_a_one_segment_path_still_yields_a_verb_candidate():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/legacy",
        method="delete",
        path="/legacy",
    )

    query = derive(change, CONFIG)

    assert query.operation_candidates == ("legacy.delete",)


def test_the_leading_version_and_path_parameters_are_dropped():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/v1/{tenant}/customers/{id}",
        method="get",
        path="/v1/{tenant}/customers/{id}",
    )

    query = derive(change, CONFIG)

    assert query.operation_candidates == (
        "customers.get",
        "customers.list",
        "customers.retrieve",
    )


# Plan §Phase 3: no verb mapping means no candidates, and no invented reason.
def test_an_unknown_verb_yields_no_candidates_and_no_reason():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/v1/charges",
        method="trace",
        path="/v1/charges",
    )

    query = derive(change, CONFIG)

    assert query.operation_candidates == ()
    assert query.origin == "none"
    assert query.reason is None


def test_an_operation_mapping_beats_inference():
    change = a_change(
        ChangeKind.ENDPOINT_REMOVED,
        pointer="#/paths",
        before="/v1/charges/{id}",
        method="delete",
        path="/v1/charges/{id}",
    )
    config = LocateConfig(
        sdk_package="stripe",
        operations={"DELETE /v1/charges/{id}": "charges.remove"},
    )

    query = derive(change, config)

    assert query.operation_candidates == ("charges.remove",)
    assert query.origin == "mapping"


def test_an_operation_scoped_field_change_carries_both_candidates_and_the_name():
    change = a_change(
        ChangeKind.PROPERTY_TYPE_CHANGED,
        pointer=CHARGES_BODY,
        method="post",
        path="/v1/charges",
        before=payload("amount", "integer"),
        after=payload("amount", "string"),
    )

    query = derive(change, CONFIG)

    assert query.operation_candidates == ("charges.create",)
    assert query.field_name == "amount"
    assert query.origin == "inferred"


# Spec: a genuinely new required property points at the enclosing operation.
def test_a_brand_new_required_property_uses_the_enclosing_operation():
    change = a_change(
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        pointer=CHARGES_BODY,
        method="post",
        path="/v1/charges",
        after=payload("currency"),
    )

    query = derive(change, CONFIG)

    assert query.scope == "operation"
    assert query.operation_candidates == ("charges.create",)
    assert query.field_name == "currency"
    assert query.field_presence == "must_be_added"


SUBPROCESS_SCRIPT = """
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, derive

change = Change(
    kind=ChangeKind.ENDPOINT_REMOVED,
    location=Location(
        pointer="#/paths", method="get", path="/v1/customers/{id}"
    ),
    before="/v1/customers/{id}",
)
print(repr(derive(change, LocateConfig(sdk_package="stripe"))), end="")
"""


def derive_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC6: same input, identical Query across runs and hash seeds.
def test_the_query_is_identical_across_hash_seeds():
    assert derive_with_hash_seed("0") == derive_with_hash_seed("1")
