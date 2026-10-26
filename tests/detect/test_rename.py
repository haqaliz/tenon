from tenon.detect import Change, ChangeKind, Location, diff
from tenon.detect.rename import infer_renames

PROPS = "#/paths/~1users/post/requestBody/content/application~1json/schema/properties"


def payload(name, type_="string", fmt=None):
    return {"name": name, "type": type_, "format": fmt}


def prop_removed(name, type_="string", fmt=None, pointer=PROPS, method="post"):
    return Change(
        kind=ChangeKind.PROPERTY_REMOVED,
        location=Location(pointer=pointer, method=method, path="/users"),
        before=payload(name, type_, fmt),
        breaking=True,
    )


def prop_added(name, type_="string", fmt=None, pointer=PROPS, required=False, method="post"):
    return Change(
        kind=(
            ChangeKind.PROPERTY_REQUIRED_ADDED if required else ChangeKind.PROPERTY_ADDED
        ),
        location=Location(pointer=pointer, method=method, path="/users"),
        after=payload(name, type_, fmt),
        breaking=required,
    )


def test_one_removed_and_one_added_property_becomes_one_inferred_rename():
    result = infer_renames([prop_removed("nickname"), prop_added("handle")])

    assert len(result) == 1
    change = result[0]
    assert change.kind is ChangeKind.RENAMED
    assert change.before == "nickname"
    assert change.after == "handle"
    assert change.location.pointer == PROPS
    assert change.location.method == "post"
    assert change.breaking is True
    assert change.confidence == "inferred"


def test_two_added_candidates_keep_all_three_records_certain():
    records = [prop_removed("a"), prop_added("b"), prop_added("c")]

    result = infer_renames(records)

    assert result == records
    assert all(change.confidence == "certain" for change in result)


def test_two_removed_candidates_keep_all_three_records_certain():
    records = [prop_removed("a"), prop_removed("b"), prop_added("c")]

    assert infer_renames(records) == records


def test_a_type_mismatch_is_not_a_rename():
    records = [prop_removed("nickname", "string"), prop_added("handle", "integer")]

    assert infer_renames(records) == records


def test_a_format_mismatch_is_not_a_rename():
    records = [
        prop_removed("nickname", "string", "uuid"),
        prop_added("handle", "string"),
    ]

    assert infer_renames(records) == records


def test_the_same_name_with_a_different_type_is_not_a_rename():
    records = [
        prop_removed("nickname", "string"),
        prop_added("nickname", "integer"),
    ]

    assert infer_renames(records) == records


def test_the_same_shape_under_a_different_parent_pointer_is_not_a_rename():
    records = [
        prop_removed("nickname"),
        prop_added("handle", pointer=f"{PROPS}/address/properties"),
    ]

    assert infer_renames(records) == records


def test_a_brand_new_required_property_can_be_renamed():
    result = infer_renames([prop_removed("nickname"), prop_added("handle", required=True)])

    assert len(result) == 1
    assert result[0].kind is ChangeKind.RENAMED
    assert result[0].after == "handle"


def test_an_existing_property_becoming_required_is_not_a_candidate():
    became_required = Change(
        kind=ChangeKind.PROPERTY_REQUIRED_ADDED,
        location=Location(pointer=PROPS, method="post", path="/users"),
        before=payload("age"),
        after=payload("age"),
        breaking=True,
    )
    records = [prop_removed("nickname"), became_required]

    assert infer_renames(records) == records


def test_renames_never_cross_families():
    removed = prop_removed("nickname")
    added = Change(
        kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
        location=Location(pointer=PROPS, method="post", path="/users"),
        after={"name": "handle", "in": "query", "type": "string", "format": None},
        breaking=True,
    )
    records = [removed, added]

    assert infer_renames(records) == records


def test_the_same_shape_in_a_different_operation_is_not_a_rename():
    records = [prop_removed("nickname"), prop_added("handle", method="put")]

    assert infer_renames(records) == records


def test_unrelated_records_pass_through_untouched():
    type_changed = Change(
        kind=ChangeKind.PROPERTY_TYPE_CHANGED,
        location=Location(pointer=PROPS, method="post", path="/users"),
        before=payload("age", "integer"),
        after=payload("age", "string"),
        breaking=True,
    )
    removed = prop_removed("nickname")
    added = prop_added("handle")

    result = infer_renames([type_changed, removed, added])

    assert result == [
        type_changed,
        Change(
            kind=ChangeKind.RENAMED,
            location=added.location,
            before="nickname",
            after="handle",
            breaking=True,
            confidence="inferred",
        ),
    ]


def test_inference_is_idempotent():
    once = infer_renames([prop_removed("nickname"), prop_added("handle")])

    assert infer_renames(once) == once


PARAMS = "#/paths/~1users/get/parameters"


def param_removed(name, where="query", type_="string", fmt=None):
    return Change(
        kind=ChangeKind.PARAMETER_REMOVED,
        location=Location(pointer=PARAMS, method="get", path="/users"),
        before={"name": name, "in": where, "type": type_, "format": fmt},
        breaking=True,
    )


def param_required(name, where="query", type_="string", fmt=None, before=None):
    return Change(
        kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
        location=Location(pointer=PARAMS, method="get", path="/users"),
        before=before,
        after={"name": name, "in": where, "type": type_, "format": fmt},
        breaking=True,
    )


def test_a_parameter_rename_is_inferred():
    result = infer_renames(
        [param_removed("limit", type_="integer"), param_required("offset", type_="integer")]
    )

    assert len(result) == 1
    assert result[0].kind is ChangeKind.RENAMED
    assert (result[0].before, result[0].after) == ("limit", "offset")


def test_a_parameter_moving_to_another_location_is_not_a_rename():
    records = [param_removed("limit"), param_required("offset", where="header")]

    assert infer_renames(records) == records


def test_an_existing_parameter_becoming_required_is_not_a_candidate():
    records = [param_removed("limit"), param_required("mode", before={"name": "mode"})]

    assert infer_renames(records) == records


def document(paths):
    return {"openapi": "3.0.3", "paths": paths}


def operation(method):
    return {method: {"responses": {}}}


def test_an_endpoint_rename_with_the_same_method_is_inferred():
    old = document({"/v1/users": operation("get")})
    new = document({"/v2/users": operation("get")})

    result = diff(old, new).changes

    assert len(result) == 1
    change = result[0]
    assert change.kind is ChangeKind.RENAMED
    assert change.before == "/v1/users"
    assert change.after == "/v2/users"
    assert change.location.pointer == "#/paths"
    assert change.location.method == "get"
    assert change.location.path == "/v2/users"
    assert change.breaking is True
    assert change.confidence == "inferred"


def test_an_endpoint_with_a_different_method_is_not_a_rename():
    old = document({"/legacy": operation("get")})
    new = document({"/orders": operation("post")})

    result = diff(old, new).changes

    assert [change.kind for change in result] == [
        ChangeKind.ENDPOINT_ADDED,
        ChangeKind.ENDPOINT_REMOVED,
    ]
    assert all(change.confidence == "certain" for change in result)


def test_a_path_parameter_rename_is_inferred():
    old = document({"/users/{id}": operation("get")})
    new = document({"/users/{user_id}": operation("get")})

    result = diff(old, new).changes

    assert len(result) == 1
    assert result[0].kind is ChangeKind.RENAMED
    assert (result[0].before, result[0].after) == ("/users/{id}", "/users/{user_id}")


def test_different_parameter_counts_do_not_pair():
    old = document({"/users/{id}": operation("get")})
    new = document({"/users/{user_id}/posts": operation("get")})

    result = diff(old, new).changes

    assert [change.kind for change in result] == [
        ChangeKind.ENDPOINT_ADDED,
        ChangeKind.ENDPOINT_REMOVED,
    ]


def test_a_two_way_swap_produces_zero_renames():
    old = document({"/a": operation("get"), "/b": operation("get")})
    new = document({"/c": operation("get"), "/d": operation("get")})

    result = diff(old, new).changes

    assert len(result) == 4
    assert ChangeKind.RENAMED not in {change.kind for change in result}


def test_a_property_rename_is_inferred_through_diff():
    def body_schema(name):
        return document(
            {
                "/users": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {name: {"type": "string"}},
                                    }
                                }
                            }
                        },
                        "responses": {},
                    }
                }
            }
        )

    result = diff(body_schema("nickname"), body_schema("handle")).changes

    assert len(result) == 1
    assert result[0].kind is ChangeKind.RENAMED
    assert (result[0].before, result[0].after) == ("nickname", "handle")
    assert result[0].confidence == "inferred"


def test_json_is_byte_stable_after_inference():
    old = document({"/users/{id}": operation("get"), "/same": operation("get")})
    new = document({"/users/{user_id}": operation("get"), "/same": operation("get")})

    def reversed_keys(value):
        if isinstance(value, dict):
            return {key: reversed_keys(value[key]) for key in reversed(list(value))}
        if isinstance(value, list):
            return [reversed_keys(item) for item in value]
        return value

    assert diff(reversed_keys(old), reversed_keys(new)).to_json() == diff(old, new).to_json()

