import re
from pathlib import Path

import pytest

from tenon.detect import RefusalCode, SpecRefusal
from tenon.detect.ingest import load, parse

FIXTURES = Path(__file__).parent.parent / "fixtures" / "specs"


def test_load_reads_a_3_0_yaml_spec():
    document = load(FIXTURES / "minimal-3.0.yaml")

    assert document["openapi"] == "3.0.3"
    assert document["paths"]["/users"]["get"]["operationId"] == "listUsers"


def test_load_reads_a_3_1_json_spec():
    document = load(FIXTURES / "minimal-3.1.json")

    assert document["openapi"] == "3.1.0"
    assert document["paths"]["/users"]["get"]["responses"]["200"]["description"] == "OK"


@pytest.mark.parametrize(
    ("fixture", "code", "pointer"),
    [
        ("swagger-2.0.yaml", RefusalCode.UNSUPPORTED_VERSION, "#/swagger"),
        ("not-a-spec.yaml", RefusalCode.NOT_A_SPEC, "#"),
        ("unparseable.yaml", RefusalCode.UNPARSEABLE, None),
        ("empty.yaml", RefusalCode.UNPARSEABLE, None),
        ("bad-version.yaml", RefusalCode.UNSUPPORTED_VERSION, "#/openapi"),
    ],
)
def test_load_refuses_bad_input_by_name(fixture, code, pointer):
    with pytest.raises(SpecRefusal) as caught:
        load(FIXTURES / fixture)

    assert caught.value.code is code
    assert caught.value.pointer == pointer
    assert fixture in caught.value.message


def test_unparseable_names_the_line_and_column():
    with pytest.raises(SpecRefusal) as caught:
        load(FIXTURES / "unparseable.yaml")

    assert re.search(r"line \d+, column \d+", caught.value.message)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", RefusalCode.UNPARSEABLE),
        ("   \n", RefusalCode.UNPARSEABLE),
        ("null", RefusalCode.NOT_A_SPEC),
        ("- one\n- two\n", RefusalCode.NOT_A_SPEC),
        ("openapi: 3.0\n", RefusalCode.UNSUPPORTED_VERSION),
        ("openapi: [3, 0, 3]\n", RefusalCode.UNSUPPORTED_VERSION),
        ("swagger: '1.2'\n", RefusalCode.UNSUPPORTED_VERSION),
    ],
)
def test_parse_refuses_bad_documents(text, code):
    with pytest.raises(SpecRefusal) as caught:
        parse(text, "<inline>")

    assert caught.value.code is code
    assert "<inline>" in caught.value.message


def test_missing_file_is_a_refusal_naming_the_path():
    missing = FIXTURES / "does-not-exist.yaml"

    with pytest.raises(SpecRefusal) as caught:
        load(missing)

    assert caught.value.code is RefusalCode.UNPARSEABLE
    assert str(missing) in caught.value.message


def test_ref_chain_resolves_to_the_final_node():
    document = load(FIXTURES / "ref-chain.yaml")

    schema = document["paths"]["/users"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema == {"type": "object", "properties": {"id": {"type": "integer"}}}
    assert document["components"]["schemas"]["A"] == schema


def test_unresolved_ref_names_the_missing_pointer():
    with pytest.raises(SpecRefusal) as caught:
        load(FIXTURES / "ref-missing.yaml")

    assert caught.value.code is RefusalCode.UNRESOLVED_REF
    assert caught.value.pointer == "#/components/schemas/Missing"
    assert "ref-missing.yaml" in caught.value.message


def test_external_ref_names_the_pointer_where_it_was_found():
    with pytest.raises(SpecRefusal) as caught:
        load(FIXTURES / "ref-external.yaml")

    assert caught.value.code is RefusalCode.EXTERNAL_REF
    assert caught.value.pointer == (
        "#/paths/~1users/get/responses/200/content/application~1json/schema/$ref"
    )
    assert "example.com" in caught.value.message


@pytest.mark.parametrize(
    "ref",
    [
        "http://example.com/x.yaml",
        "https://example.com/x.yaml#/User",
        "file:///tmp/x.yaml",
        "./other.yaml#/User",
        "other.yaml",
    ],
)
def test_every_external_ref_shape_is_refused(ref):
    with pytest.raises(SpecRefusal) as caught:
        parse(f"openapi: 3.1.0\npaths: {{}}\nx-schema:\n  $ref: '{ref}'\n", "<inline>")

    assert caught.value.code is RefusalCode.EXTERNAL_REF
    assert caught.value.pointer == "#/x-schema/$ref"
    assert ref in caught.value.message


def test_cyclic_ref_chain_leaves_a_marker_at_the_back_edge():
    document = load(FIXTURES / "ref-cycle.yaml")

    schemas = document["components"]["schemas"]
    assert schemas["A"] == {"$ref": "#/components/schemas/B"}
    assert schemas["B"] == {"$ref": "#/components/schemas/A"}


def test_self_referential_node_resolves_everything_but_the_back_edge():
    document = load(FIXTURES / "cycle-old.yaml")

    assert document["components"]["schemas"]["Node"] == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "child": {"$ref": "#/components/schemas/Node"},
        },
    }


def test_pointer_tokens_are_unescaped():
    document = parse(
        "openapi: 3.1.0\n"
        "paths: {}\n"
        "x-target:\n"
        "  'a/b': {type: string}\n"
        "  'c~d': {type: integer}\n"
        "x-refs:\n"
        "  slash: {$ref: '#/x-target/a~1b'}\n"
        "  tilde: {$ref: '#/x-target/c~0d'}\n",
        "<inline>",
    )

    assert document["x-refs"]["slash"] == {"type": "string"}
    assert document["x-refs"]["tilde"] == {"type": "integer"}


def test_ref_can_address_an_array_item():
    document = parse(
        "openapi: 3.1.0\n"
        "paths: {}\n"
        "x-list:\n"
        "  - {type: string}\n"
        "  - {type: integer}\n"
        "x-alias:\n"
        "  $ref: '#/x-list/1'\n",
        "<inline>",
    )

    assert document["x-alias"] == {"type": "integer"}


def test_ref_past_the_end_of_an_array_is_unresolved():
    with pytest.raises(SpecRefusal) as caught:
        parse(
            "openapi: 3.1.0\npaths: {}\nx-list: [a]\nx-alias:\n  $ref: '#/x-list/9'\n",
            "<inline>",
        )

    assert caught.value.code is RefusalCode.UNRESOLVED_REF
    assert caught.value.pointer == "#/x-list/9"


@pytest.mark.parametrize("ref", ["'#x'", "42", "null", "['#/x-list/0']"])
def test_malformed_ref_is_a_refusal_not_a_crash(ref):
    with pytest.raises(SpecRefusal) as caught:
        parse(f"openapi: 3.1.0\npaths: {{}}\nx-schema:\n  $ref: {ref}\n", "<inline>")

    assert caught.value.code is RefusalCode.UNRESOLVED_REF
    assert caught.value.pointer == "#/x-schema/$ref"


def test_non_utf8_file_is_unparseable_naming_the_path(tmp_path):
    path = tmp_path / "latin-1.yaml"
    path.write_bytes(b"openapi: 3.0.3\ninfo: \xff\n")

    with pytest.raises(SpecRefusal) as caught:
        load(path)

    assert caught.value.code is RefusalCode.UNPARSEABLE
    assert str(path) in caught.value.message
