import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest

from tenon.pr import PrRefusal, PrStatus
from tenon.pr.result import PrDraft


# Spec AC1: the status vocabulary is exactly two values, in order.
def test_pr_status_values_are_the_closed_two():
    assert [status.value for status in PrStatus] == ["OPENED", "REFUSED"]


# Spec AC1: the refusal vocabulary is exactly thirteen values, in order.
def test_pr_refusal_values_are_the_closed_thirteen():
    assert [refusal.value for refusal in PrRefusal] == [
        "NOT_A_GIT_REPO",
        "DIRTY_CHECKOUT",
        "NO_REMOTE",
        "UNKNOWN_DEFAULT_BRANCH",
        "NO_PATCH",
        "DEFAULT_BRANCH",
        "BRANCH_EXISTS",
        "UNVERIFIED_NOT_ALLOWED",
        "PATCH_DID_NOT_APPLY",
        "COPY_FAILED",
        "COMMIT_FAILED",
        "PUSH_FAILED",
        "PR_FAILED",
    ]


# Spec AC1: every value constructs from its string.
@pytest.mark.parametrize("status", list(PrStatus))
def test_every_pr_status_constructs(status):
    assert PrStatus(status.value) is status


@pytest.mark.parametrize("refusal", list(PrRefusal))
def test_every_pr_refusal_constructs(refusal):
    assert PrRefusal(refusal.value) is refusal


# Spec AC1: every value is a plain string, never an opaque object.
def test_every_vocabulary_value_is_a_plain_string():
    assert all(isinstance(value, str) for value in [*PrStatus, *PrRefusal])


def a_draft(**overrides):
    values = {
        "title": "[TESTS_PASSED] tenon: rename payment method types",
        "body": "## Proof\n\n`python -m pytest -q` passed after the patch.",
        "branch": "tenon/renamed-payment-method-types-a1b2c3d4",
        "commit_message": "tenon: rename payment method types",
    }
    values.update(overrides)
    return PrDraft(**values)


# Spec AC2: a valid draft keeps every field unchanged on access.
def test_pr_draft_keeps_its_four_fields():
    draft = a_draft()
    assert draft.title == "[TESTS_PASSED] tenon: rename payment method types"
    assert draft.body == "## Proof\n\n`python -m pytest -q` passed after the patch."
    assert draft.branch == "tenon/renamed-payment-method-types-a1b2c3d4"
    assert draft.commit_message == "tenon: rename payment method types"


# Spec AC2: every field must be non-empty.
@pytest.mark.parametrize("field", ["title", "body", "branch", "commit_message"])
def test_pr_draft_rejects_an_empty_field(field):
    with pytest.raises(ValueError):
        a_draft(**{field: ""})


# Plan edge case: non-string values are rejected at construction, not at render time.
@pytest.mark.parametrize("field", ["title", "body", "branch", "commit_message"])
def test_pr_draft_rejects_a_non_string_field(field):
    with pytest.raises(ValueError):
        a_draft(**{field: None})


# Spec AC2: a draft cannot be mutated after construction.
def test_pr_draft_is_frozen():
    with pytest.raises(FrozenInstanceError):
        a_draft().title = "other"


# Spec AC5: the draft payload has exactly four keys, in a fixed order.
def test_pr_draft_to_dict_has_the_contract_keys():
    parsed = a_draft().to_dict()
    assert list(parsed) == ["title", "body", "branch", "commit_message"]
    assert parsed == {
        "title": "[TESTS_PASSED] tenon: rename payment method types",
        "body": "## Proof\n\n`python -m pytest -q` passed after the patch.",
        "branch": "tenon/renamed-payment-method-types-a1b2c3d4",
        "commit_message": "tenon: rename payment method types",
    }


# Spec AC5: no dataclass repr or non-JSON value reaches the payload.
def test_pr_draft_to_json_holds_only_json_primitives():
    text = a_draft().to_json()
    assert json.loads(text) == a_draft().to_dict()
    assert "PrDraft(" not in text


DRAFT_SUBPROCESS_SCRIPT = """
from tenon.pr.result import PrDraft

draft = PrDraft(
    title="[TESTS_PASSED] tenon: rename payment method types",
    body="## Proof\\n\\n`python -m pytest -q` passed after the patch.",
    branch="tenon/renamed-payment-method-types-a1b2c3d4",
    commit_message="tenon: rename payment method types",
)
print(draft.to_json(), end="")
"""


def draft_to_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", DRAFT_SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC5: byte-identical output across hash seeds.
def test_pr_draft_to_json_is_byte_stable_across_hash_seeds():
    assert draft_to_json_with_hash_seed("0") == draft_to_json_with_hash_seed("1")
