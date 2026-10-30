import json

import pytest

from tenon.detect import Unanalyzed, UnanalyzedReason


def an_unanalyzed(reason=UnanalyzedReason.CYCLIC_REF):
    return Unanalyzed(pointer="#/components/schemas/Node", reason=reason)


def test_unanalyzed_reasons_are_the_closed_three():
    assert [reason.value for reason in UnanalyzedReason] == [
        "CYCLIC_REF",
        "UNSUPPORTED_COMPOSITION",
        "UNRESOLVED_REF",
    ]


@pytest.mark.parametrize("reason", list(UnanalyzedReason))
def test_unanalyzed_round_trips_through_dict(reason):
    entry = an_unanalyzed(reason)
    assert Unanalyzed.from_dict(entry.to_dict()) == entry


def test_unanalyzed_dict_uses_json_primitives_only():
    entry = an_unanalyzed()
    assert entry.to_dict() == {
        "pointer": "#/components/schemas/Node",
        "reason": "CYCLIC_REF",
    }
    assert json.loads(json.dumps(entry.to_dict())) == entry.to_dict()


def test_unanalyzed_coerces_a_reason_string():
    entry = Unanalyzed(pointer="#", reason="UNRESOLVED_REF")
    assert entry.reason is UnanalyzedReason.UNRESOLVED_REF


@pytest.mark.parametrize(
    "pointer", ["#", "#/components/schemas/Node", "#/paths/~1users~1{id}/get"]
)
def test_unanalyzed_accepts_an_rfc6901_fragment_pointer(pointer):
    entry = Unanalyzed(pointer=pointer, reason=UnanalyzedReason.UNRESOLVED_REF)
    assert entry.pointer == pointer


@pytest.mark.parametrize("pointer", ["", "/paths/foo", "#paths/foo", "#/paths~2bad"])
def test_unanalyzed_rejects_a_malformed_pointer(pointer):
    with pytest.raises(ValueError):
        Unanalyzed(pointer=pointer, reason=UnanalyzedReason.CYCLIC_REF)
