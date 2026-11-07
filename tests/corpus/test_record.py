import json
import re

import pytest

from tenon.corpus.record import CorpusRecord, Outcome, record_id

REPO = "https://github.com/o/r"
COMMIT = "56e69cf1c8b0d4e2f0a7c9b3d5e7f1a2c4b6d8e0"
CHANGE = {"kind": "signature", "path": "app.py", "symbol": "handler"}
PROPOSAL = {"diff": "--- a/app.py\n+++ b/app.py\n", "summary": "one edit"}
PROOF = {"level": "TESTS_PASSED", "cause": None}
PR = {"number": 1, "url": "https://github.com/o/r/pull/1"}


def an_id(**overrides):
    values = {
        "repo": REPO,
        "commit": COMMIT,
        "change": CHANGE,
        "proposal": PROPOSAL,
    }
    values.update(overrides)
    return record_id(
        values["repo"], values["commit"], values["change"], values["proposal"]
    )


def a_record(**overrides):
    values = {
        "repo": REPO,
        "commit": COMMIT,
        "change": CHANGE,
        "proposal": PROPOSAL,
        "proof": PROOF,
        "pr": None,
        "outcome": Outcome.PENDING,
        "recorded": "2026-11-07",
    }
    values.update(overrides)
    if "id" not in values:
        try:
            values["id"] = record_id(
                values["repo"], values["commit"], values["change"], values["proposal"]
            )
        except (AttributeError, TypeError):
            values["id"] = "0" * 12
    return CorpusRecord(**values)


# Spec AC1: the six outcomes are the closed vocabulary, in docs order.
def test_outcome_values_are_the_closed_six():
    assert [outcome.value for outcome in Outcome] == [
        "PENDING",
        "MERGED",
        "REJECTED",
        "CLOSED",
        "INCIDENT",
        "LOCAL_ONLY",
    ]


# Spec AC1: every outcome constructs from its string.
@pytest.mark.parametrize("outcome", list(Outcome))
def test_every_outcome_constructs(outcome):
    assert Outcome(outcome.value) is outcome


# Spec AC1: an unknown value raises rather than defaulting.
def test_unknown_outcome_raises():
    with pytest.raises(ValueError):
        Outcome("DONE")


# Spec AC2: a valid record keeps every field, and optional text defaults to empty.
def test_a_valid_record_holds_its_fields():
    record = a_record()
    assert record.id == an_id()
    assert record.repo == REPO
    assert record.commit == COMMIT
    assert record.change == CHANGE
    assert record.proposal == PROPOSAL
    assert record.proof == PROOF
    assert record.pr is None
    assert record.outcome is Outcome.PENDING
    assert record.recorded == "2026-11-07"
    assert record.outcome_url is None
    assert record.notes == ""
    assert record.evidence == ""


# Spec AC2: an outcome string coerces to the enum and a PR mapping is kept.
def test_record_coerces_a_string_outcome_and_keeps_a_pr():
    record = a_record(outcome="MERGED", pr=PR)
    assert record.outcome is Outcome.MERGED
    assert record.pr == PR


# Spec AC2 / AC3: a record round-trips through its dictionary without drift.
def test_record_round_trips_through_dict():
    record = a_record(
        outcome=Outcome.MERGED,
        outcome_url="https://github.com/o/r/pull/1",
        notes="merged by hand",
        evidence="docs/evidence.md",
        pr=PR,
    )
    parsed = record.to_dict()
    assert parsed["outcome"] == "MERGED"
    assert CorpusRecord.from_dict(parsed) == record


def test_record_round_trips_through_json():
    record = a_record(outcome=Outcome.LOCAL_ONLY)
    assert CorpusRecord.from_dict(json.loads(record.to_json())) == record


# Spec AC2: the dictionary carries exactly the contract keys.
def test_to_dict_has_the_contract_keys():
    parsed = a_record(pr=PR).to_dict()
    assert set(parsed) == {
        "id",
        "repo",
        "commit",
        "change",
        "proposal",
        "proof",
        "pr",
        "outcome",
        "recorded",
        "outcome_url",
        "notes",
        "evidence",
    }
    assert parsed["outcome"] == "PENDING"
    assert parsed["pr"] == PR


# Spec AC2 / AC7: the JSON is canonical, compact and sorted.
def test_to_json_is_canonical():
    record = a_record()
    text = record.to_json()
    assert text == json.dumps(
        record.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert '", "' not in text
    assert '": "' not in text


# Spec AC2: an empty or non-string repository is not a record.
@pytest.mark.parametrize("repo", ["", None, 3, ["https://github.com/o/r"]])
def test_a_bad_repo_raises(repo):
    with pytest.raises(ValueError):
        a_record(repo=repo)


# Spec AC2: an empty or non-string commit is not a record.
@pytest.mark.parametrize("commit", ["", None, 3])
def test_a_bad_commit_raises(commit):
    with pytest.raises(ValueError):
        a_record(commit=commit)


# Spec AC2: change, proposal and proof must be mappings.
@pytest.mark.parametrize("field", ["change", "proposal", "proof"])
@pytest.mark.parametrize("value", [None, ["not", "a", "dict"], "text", 7])
def test_a_non_mapping_snapshot_raises(field, value):
    with pytest.raises(ValueError):
        a_record(**{field: value})


# Spec AC2: the PR is a mapping or None, never anything else.
@pytest.mark.parametrize("pr", [[], "https://github.com/o/r/pull/1", 7])
def test_a_non_mapping_pr_raises(pr):
    with pytest.raises(ValueError):
        a_record(pr=pr)


# Spec AC2: the date is exactly YYYY-MM-DD and a real day.
@pytest.mark.parametrize(
    "recorded",
    [
        "",
        "2026-11-7",
        "20261107",
        "2026-13-01",
        "2026-02-30",
        "2026-11-07T00:00:00",
        "not-a-date",
    ],
)
def test_a_bad_date_raises(recorded):
    with pytest.raises(ValueError):
        a_record(recorded=recorded)


# Spec AC2: a non-string date raises even when it looks date-like.
@pytest.mark.parametrize("recorded", [20261107, None, ["2026-11-07"]])
def test_a_non_string_date_raises(recorded):
    with pytest.raises(ValueError):
        a_record(recorded=recorded)


# Spec AC2: a non-Outcome value raises.
@pytest.mark.parametrize("outcome", ["DONE", "merged", None, 3])
def test_a_non_outcome_raises(outcome):
    with pytest.raises(ValueError):
        a_record(outcome=outcome)


# Spec AC2: the id must equal the deterministic identity.
def test_an_id_mismatch_raises():
    with pytest.raises(ValueError, match="does not match"):
        a_record(id="0123456789ab")


def test_a_non_string_id_raises():
    with pytest.raises(ValueError):
        a_record(id=123456789012)


# Spec AC2: outcome_url is a string or None; notes and evidence are strings.
@pytest.mark.parametrize(
    "field,value",
    [
        ("outcome_url", 7),
        ("outcome_url", []),
        ("notes", None),
        ("notes", 7),
        ("evidence", None),
        ("evidence", 7),
    ],
)
def test_text_fields_must_be_strings(field, value):
    with pytest.raises(ValueError):
        a_record(**{field: value})


# Spec AC3: the id is 12 hex characters and stable for the same inputs.
def test_record_id_is_twelve_hex_and_stable():
    first = an_id()
    assert re.fullmatch(r"[0-9a-f]{12}", first)
    assert first == an_id()
    assert first == record_id(REPO, COMMIT, dict(CHANGE), dict(PROPOSAL))


# Spec AC3: canonical key order and compact separators are pinned.
def test_record_id_matches_a_pinned_hash():
    assert (
        record_id("r", "c", {"b": 2, "a": 1}, {"diff": "d"}) == "0e59faea46e0"
    )


# Spec AC3: each identity part changes the id.
@pytest.mark.parametrize(
    "overrides",
    [
        {"repo": "https://github.com/o/other"},
        {"commit": "0" * 40},
        {"change": {"kind": "signature", "path": "other.py"}},
        {"proposal": {"diff": "--- a/app.py\n+++ b/app.py\n+one line\n"}},
    ],
)
def test_record_id_changes_with_each_identity_part(overrides):
    assert an_id(**overrides) != an_id()


# Spec AC3: the outcome and its URL are not part of the id, so an update keeps it.
def test_record_id_ignores_the_outcome():
    pending = a_record(outcome=Outcome.PENDING)
    merged = a_record(
        outcome=Outcome.MERGED, outcome_url="https://github.com/o/r/pull/1"
    )
    assert pending.id == merged.id


# Spec AC3: a missing diff hashes as the empty string.
def test_record_id_uses_an_empty_diff_when_missing():
    assert an_id(proposal={}) == record_id(REPO, COMMIT, CHANGE, {"diff": ""})


# Spec AC3: other proposal keys do not change the id, only the diff does.
def test_record_id_ignores_other_proposal_keys():
    assert an_id(proposal={"diff": "d", "summary": "x"}) == an_id(
        proposal={"diff": "d"}
    )
