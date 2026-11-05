import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest

from tenon.pr import PrRefusal, PrStatus
from tenon.pr.result import PrDraft, PrResult
from tenon.prove import ProofLevel


# Spec AC1: the status vocabulary is exactly two values, in order.
def test_pr_status_values_are_the_closed_two():
    assert [status.value for status in PrStatus] == ["OPENED", "REFUSED"]


# Spec M10/AC3: a weak but not unverified proof gets its own named refusal.
def test_below_required_level_is_named():
    assert PrRefusal.BELOW_REQUIRED_LEVEL.value == "BELOW_REQUIRED_LEVEL"


# Spec AC1: the refusal vocabulary is exactly fifteen values, in order.
def test_pr_refusal_values_are_the_closed_fifteen():
    assert [refusal.value for refusal in PrRefusal] == [
        "NOT_A_GIT_REPO",
        "DIRTY_CHECKOUT",
        "NO_REMOTE",
        "UNKNOWN_DEFAULT_BRANCH",
        "NO_PATCH",
        "DEFAULT_BRANCH",
        "BRANCH_EXISTS",
        "REMOTE_CHECK_FAILED",
        "UNVERIFIED_NOT_ALLOWED",
        "BELOW_REQUIRED_LEVEL",
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


def an_opened(**overrides):
    values = {
        "status": PrStatus.OPENED,
        "level": ProofLevel.TESTS_PASSED,
        "draft": a_draft(),
        "url": "https://github.com/example/repo/pull/42",
        "refusal": None,
        "detail": "",
    }
    values.update(overrides)
    return PrResult(**values)


def a_refused(refusal=PrRefusal.DIRTY_CHECKOUT, **overrides):
    values = {
        "status": PrStatus.REFUSED,
        "level": ProofLevel.TESTS_PASSED,
        "draft": a_draft(),
        "url": None,
        "refusal": refusal,
        "detail": "",
    }
    values.update(overrides)
    return PrResult(**values)


# Spec AC3: an opened PR carries a URL and no refusal.
def test_opened_with_a_url_and_no_refusal_is_valid():
    result = an_opened()
    assert result.status is PrStatus.OPENED
    assert result.url == "https://github.com/example/repo/pull/42"
    assert result.refusal is None


# Spec AC3: an opened PR without a URL says nothing about where it went.
@pytest.mark.parametrize("url", [None, ""])
def test_opened_without_a_url_raises(url):
    with pytest.raises(ValueError):
        an_opened(url=url)


# Spec AC3: an opened PR cannot also claim it was refused.
def test_opened_with_a_refusal_raises():
    with pytest.raises(ValueError):
        an_opened(refusal=PrRefusal.DIRTY_CHECKOUT)


# Spec: detail is only for a refusal's command output.
def test_opened_with_detail_raises():
    with pytest.raises(ValueError):
        an_opened(detail="fatal: something")


# Spec AC3: a refusal names its reason and has no URL.
def test_refused_with_a_refusal_and_no_url_is_valid():
    result = a_refused()
    assert result.status is PrStatus.REFUSED
    assert result.refusal is PrRefusal.DIRTY_CHECKOUT
    assert result.url is None


# Spec AC3: a refusal without a refusal would hide why nothing was opened.
def test_refused_without_a_refusal_raises():
    with pytest.raises(ValueError):
        a_refused(refusal=None)


# Spec AC3: a refusal cannot also claim a URL.
def test_refused_with_a_url_raises():
    with pytest.raises(ValueError):
        a_refused(url="https://github.com/example/repo/pull/42")


# Spec AC4: strings coerce to enums, so a JSON round-trip is easy.
def test_pr_result_coerces_string_status_level_and_refusal():
    result = PrResult(
        status="REFUSED",
        level="UNVERIFIED",
        draft=a_draft(),
        url=None,
        refusal="DIRTY_CHECKOUT",
        detail="",
    )
    assert result.status is PrStatus.REFUSED
    assert result.level is ProofLevel.UNVERIFIED
    assert result.refusal is PrRefusal.DIRTY_CHECKOUT


# Plan edge case: an unknown string fails loudly in the enum constructor.
def test_pr_result_rejects_an_unknown_refusal_string():
    with pytest.raises(ValueError):
        a_refused(refusal="SOMETHING_ELSE")


# Spec AC6: detail defaults to the empty string.
def test_pr_result_detail_defaults_to_empty():
    result = PrResult(
        status=PrStatus.REFUSED,
        level=ProofLevel.TESTS_PASSED,
        draft=a_draft(),
        refusal=PrRefusal.PUSH_FAILED,
    )
    assert result.detail == ""


# Spec AC6: a refusal keeps the command tail it was given.
def test_refused_keeps_a_command_tail():
    tail_text = "fatal: unable to access the remote\nTo github.com:example/repo.git"
    result = a_refused(refusal=PrRefusal.PUSH_FAILED, detail=tail_text)
    assert result.detail == tail_text


# Spec: a result cannot be mutated after construction.
def test_pr_result_is_frozen():
    with pytest.raises(FrozenInstanceError):
        an_opened().status = PrStatus.REFUSED


# Spec AC5: the result payload has exactly six keys, in a fixed order.
def test_pr_result_to_dict_has_the_contract_keys():
    parsed = a_refused(refusal=PrRefusal.PUSH_FAILED, detail="fatal: rejected").to_dict()
    assert list(parsed) == ["status", "level", "draft", "url", "refusal", "detail"]
    assert parsed == {
        "status": "REFUSED",
        "level": "TESTS_PASSED",
        "draft": a_draft().to_dict(),
        "url": None,
        "refusal": "PUSH_FAILED",
        "detail": "fatal: rejected",
    }
    assert list(parsed["draft"]) == ["title", "body", "branch", "commit_message"]


# Spec AC5: enums become plain strings, never enum or dataclass reprs.
def test_pr_result_to_json_holds_only_json_primitives():
    text = an_opened(level=ProofLevel.UNVERIFIED).to_json()
    assert json.loads(text) == an_opened(level=ProofLevel.UNVERIFIED).to_dict()
    for leak in ("PrStatus.", "PrRefusal.", "ProofLevel.", "PrDraft(", "PrResult("):
        assert leak not in text


RESULT_SUBPROCESS_SCRIPT = """
from tenon.pr.result import PrDraft, PrResult

draft = PrDraft(
    title="[UNVERIFIED] tenon: rename payment method types",
    body="## Proof\\n\\nThe check did not pass.",
    branch="tenon/renamed-payment-method-types-a1b2c3d4",
    commit_message="tenon: rename payment method types",
)
result = PrResult(
    status="REFUSED",
    level="UNVERIFIED",
    draft=draft,
    url=None,
    refusal="PUSH_FAILED",
    detail="fatal: rejected",
)
print(result.to_json(), end="")
"""


def result_to_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", RESULT_SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC5: byte-identical output across hash seeds.
def test_pr_result_to_json_is_byte_stable_across_hash_seeds():
    assert result_to_json_with_hash_seed("0") == result_to_json_with_hash_seed("1")


# Plan phase 4: `tenon.pr` is the public surface for the contract and the renderer.
def test_package_exports_the_public_contract():
    from tenon.pr import (
        PrDraft,
        PrRefusal,
        PrResult,
        PrStatus,
        __all__,
        render_pr,
    )

    assert __all__ == [
        "GitGhRemote",
        "PrDraft",
        "PrRefusal",
        "PrResult",
        "PrStatus",
        "Remote",
        "RemoteError",
        "render_pr",
        "write_pr",
    ]
    assert PrStatus.OPENED.value == "OPENED"
    assert PrRefusal.PR_FAILED.value == "PR_FAILED"
    assert PrDraft.__name__ == "PrDraft"
    assert PrResult.__name__ == "PrResult"
    assert callable(render_pr)
