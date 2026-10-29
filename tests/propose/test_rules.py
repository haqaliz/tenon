import builtins
import pathlib

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import AmbiguityReason, AmbiguousGroup, LocateReason, LocateResult, Site
from tenon.propose import RuleProposer

PROPOSER = RuleProposer()


def a_site(**overrides):
    values = {
        "path": "billing.py",
        "line": 42,
        "column": 25,
        "shape": "keyword",
        "symbol": "amount",
    }
    values.update(overrides)
    return Site(**values)


def a_rename(**overrides):
    values = {
        "kind": ChangeKind.RENAMED,
        "location": Location(pointer="#/components/schemas/Charge"),
        "before": "amount",
        "after": "amount_cents",
        "confidence": "inferred",
    }
    values.update(overrides)
    return Change(**values)


def a_result(*sites, change=None, ambiguous=()):
    change = change or a_rename()
    if not sites and not ambiguous:
        return LocateResult(
            change=change,
            certain=(),
            ambiguous=(),
            reason=LocateReason.NO_SITES,
        )
    return LocateResult(change=change, certain=sites, ambiguous=ambiguous)


@pytest.mark.parametrize("kind", list(ChangeKind))
def test_only_a_renamed_change_passes_the_gate(kind):
    change = a_rename(kind=kind)
    edits = PROPOSER.propose(change, a_result(a_site(), change=change), "/nowhere")

    if kind is ChangeKind.RENAMED:
        assert edits
    else:
        assert edits == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"before": None},
        {"before": ""},
        {"after": None},
        {"after": ""},
        {"before": "amount", "after": "amount"},
        {"before": {"name": "amount"}, "after": {"name": "amount_cents"}},
        {"before": ["amount"], "after": ["amount_cents"]},
    ],
)
def test_a_malformed_rename_yields_no_edits(overrides):
    change = a_rename(**overrides)
    assert PROPOSER.propose(change, a_result(a_site(), change=change), "/nowhere") == ()


def test_an_endpoint_rename_yields_no_edits():
    change = a_rename(
        location=Location(pointer="#/paths", method="get", path="/v2/charges"),
        before="/v1/charges",
        after="/v2/charges",
    )
    site = a_site(path="client.py", line=9, column=5, shape="call", symbol="/v1/charges")

    assert PROPOSER.propose(change, a_result(site, change=change), "/nowhere") == ()


def test_a_request_body_rename_with_method_and_path_still_yields_edits():
    change = a_rename(
        location=Location(
            pointer=(
                "#/paths/~1v1~1charges/post/requestBody/content"
                "/application~1json/schema/properties"
            ),
            method="post",
            path="/v1/charges",
        ),
    )

    edits = PROPOSER.propose(change, a_result(a_site(), change=change), "/nowhere")

    assert len(edits) == 1
    assert edits[0].old == "amount"
    assert edits[0].new == "amount_cents"


def test_propose_never_touches_the_filesystem(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the rule must not read the filesystem")

    monkeypatch.setattr(pathlib.Path, "read_text", explode)
    monkeypatch.setattr(builtins, "open", explode)

    edits = PROPOSER.propose(a_rename(), a_result(a_site()), tmp_path / "missing")

    assert edits


def test_two_certain_keyword_sites_become_two_edits_in_locator_order():
    later = a_site(line=12, column=9)
    earlier = a_site(line=10, column=5)

    edits = PROPOSER.propose(a_rename(), a_result(later, earlier), "/nowhere")

    assert [(edit.path, edit.line, edit.column) for edit in edits] == [
        ("billing.py", 10, 5),
        ("billing.py", 12, 9),
    ]


def test_a_certain_call_site_yields_no_edit_but_keyword_sites_still_do():
    call_site = a_site(path="client.py", line=3, column=7, shape="call")
    keyword_site = a_site()

    edits = PROPOSER.propose(
        a_rename(), a_result(call_site, keyword_site), "/nowhere"
    )

    assert [(edit.path, edit.shape) for edit in edits] == [
        ("billing.py", "keyword")
    ]


@pytest.mark.parametrize("shape", ["dict_key", "attribute"])
def test_dict_key_and_attribute_sites_are_editable(shape):
    edits = PROPOSER.propose(
        a_rename(), a_result(a_site(shape=shape)), "/nowhere"
    )

    assert len(edits) == 1
    assert edits[0].shape == shape
    assert edits[0].old == "amount"
    assert edits[0].new == "amount_cents"


def test_a_site_for_another_symbol_yields_no_edit():
    other = a_site(symbol="amount_cents")

    assert PROPOSER.propose(a_rename(), a_result(other), "/nowhere") == ()


def test_duplicate_certain_sites_yield_one_edit():
    edits = PROPOSER.propose(a_rename(), a_result(a_site(), a_site()), "/nowhere")

    assert len(edits) == 1


def test_an_ambiguous_only_result_yields_no_edits():
    group = AmbiguousGroup(
        reason=AmbiguityReason.DYNAMIC_KWARGS,
        symbol="amount",
        candidates=(a_site(),),
    )

    assert PROPOSER.propose(a_rename(), a_result(ambiguous=(group,)), "/nowhere") == ()


def test_ambiguous_groups_do_not_change_the_edits():
    group = AmbiguousGroup(
        reason=AmbiguityReason.DYNAMIC_KWARGS,
        symbol="amount",
        candidates=(a_site(path="other.py"),),
    )

    edits = PROPOSER.propose(
        a_rename(), a_result(a_site(), ambiguous=(group,)), "/nowhere"
    )

    assert len(edits) == 1
