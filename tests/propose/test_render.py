"""Span verification, in-memory application and unified-diff rendering."""

from dataclasses import replace
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, SiteShape, locate
from tenon.propose import Edit, RuleProposer
from tenon.propose.render import apply_edits, verify

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
STRIPE = LocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"


def a_rename():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before="amount",
        after="amount_cents",
    )


def a_real_edit():
    change = a_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    return RuleProposer().propose(change, located, SDK_BASIC)[0]


def an_edit(**overrides):
    values = {
        "path": "x.py",
        "line": 1,
        "column": 3,
        "shape": SiteShape.KEYWORD,
        "old": "amount",
        "new": "amount_cents",
    }
    values.update(overrides)
    return Edit(**values)


def test_verify_accepts_a_real_site_from_the_fixture():
    assert verify(a_real_edit(), SDK_BASIC) is True


def test_verify_rejects_a_symbol_that_moved_one_column():
    edit = a_real_edit()

    assert verify(replace(edit, column=edit.column + 1), SDK_BASIC) is False


def test_verify_rejects_a_name_extended_at_the_same_column(tmp_path):
    (tmp_path / "x.py").write_text("f(amount_cents=amount)\n", encoding="utf-8")

    assert verify(an_edit(), tmp_path) is False


@pytest.mark.parametrize("quote", ['"', "'"])
def test_verify_accepts_a_dict_key_with_its_own_quote(tmp_path, quote):
    (tmp_path / "x.py").write_text(
        f"f({{{quote}amount{quote}: 1}})\n", encoding="utf-8"
    )
    edit = an_edit(column=4, shape=SiteShape.DICT_KEY)

    assert verify(edit, tmp_path) is True


def test_verify_rejects_a_dict_key_with_a_mismatched_quote(tmp_path):
    (tmp_path / "x.py").write_text("f({\"amount': 1})\n", encoding="utf-8")
    edit = an_edit(column=4, shape=SiteShape.DICT_KEY)

    assert verify(edit, tmp_path) is False


def test_verify_rejects_an_absolute_path():
    edit = an_edit(path=str(SDK_BASIC / "acme/billing.py"))

    with pytest.raises(ValueError):
        verify(edit, SDK_BASIC)


def test_verify_rejects_a_parent_segment():
    with pytest.raises(ValueError):
        verify(an_edit(path="../sdk-basic/acme/billing.py"), SDK_BASIC)


def test_verify_rejects_a_backslash_path():
    with pytest.raises(ValueError):
        verify(an_edit(path="acme\\billing.py"), SDK_BASIC)


def test_verify_returns_false_for_a_missing_file(tmp_path):
    assert verify(an_edit(path="missing.py"), tmp_path) is False


def test_verify_returns_false_for_a_short_line(tmp_path):
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")

    assert verify(an_edit(line=2), tmp_path) is False


def test_verify_returns_false_for_undecodable_bytes(tmp_path):
    (tmp_path / "x.py").write_bytes(b"f(amount=amount)\n\xff\n")

    assert verify(an_edit(), tmp_path) is False


def test_apply_edits_applies_two_edits_on_one_line_from_the_bottom():
    text = "f(amount=amount, total=total)\n"
    edits = [
        an_edit(column=18, old="total", new="total_cents"),
        an_edit(column=3),
    ]

    assert apply_edits(text, edits) == (
        "f(amount_cents=amount, total_cents=total)\n"
    )


def test_apply_edits_preserves_the_dict_key_quote():
    edit = an_edit(column=4, shape=SiteShape.DICT_KEY)

    assert apply_edits("f({'amount': 1})\n", [edit]) == (
        "f({'amount_cents': 1})\n"
    )


def test_apply_edits_raises_on_overlapping_edits():
    edits = [
        an_edit(column=3),
        an_edit(column=5, old="ount", new="otal"),
    ]

    with pytest.raises(ValueError):
        apply_edits("f(amount=amount)\n", edits)
