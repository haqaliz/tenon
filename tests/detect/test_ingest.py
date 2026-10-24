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
