from tenon.detect import Change, ChangeKind, Location
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
