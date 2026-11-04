import pytest

from tenon.pr import PrRefusal, PrStatus


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
