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
