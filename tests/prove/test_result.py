import json
import os
import subprocess
import sys

import pytest

from tenon.prove import CheckResult, ProofCause, ProofLevel, ProofResult, tail


def a_check(**overrides):
    values = {
        "kind": "baseline",
        "command": ("python", "-m", "pytest", "-q"),
        "returncode": 0,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": "",
    }
    values.update(overrides)
    return CheckResult(**values)


# Spec AC1: CheckResult constructs for the two kinds the runner records.
@pytest.mark.parametrize("kind", ["baseline", "after"])
def test_check_result_accepts_both_kinds(kind):
    check = a_check(kind=kind)
    assert check.kind == kind
    assert check.command == ("python", "-m", "pytest", "-q")
    assert check.returncode == 0
    assert check.timed_out is False
    assert check.stdout_tail == ""
    assert check.stderr_tail == ""


def test_check_result_keeps_a_sequence_command_as_a_tuple():
    assert a_check(command=["python", "check.py"]).command == ("python", "check.py")


def test_check_result_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        a_check(kind="during")


# Spec AC7: a timeout has no return code, and a killed process may still have one.
def test_check_result_accepts_a_timeout_without_a_return_code():
    check = a_check(returncode=None, timed_out=True)
    assert check.returncode is None
    assert check.timed_out is True


# Spec AC7: a return code alongside a timeout is kept, not normalised away.
def test_check_result_does_not_normalise_a_return_code_on_a_timeout():
    check = a_check(returncode=-9, timed_out=True)
    assert check.returncode == -9
    assert check.timed_out is True


# Spec AC1 / PRD M8: the two levels and seven causes are the closed vocabulary.
def test_proof_level_values_are_the_closed_two():
    assert [level.value for level in ProofLevel] == ["TESTS_PASSED", "UNVERIFIED"]


def test_proof_cause_values_are_the_closed_seven():
    assert [cause.value for cause in ProofCause] == [
        "NO_PATCH_PROPOSED",
        "PATCH_DID_NOT_APPLY",
        "NO_TESTS_FOUND",
        "TESTS_FAILED_BEFORE",
        "TESTS_FAILED_AFTER",
        "CHECK_TIMED_OUT",
        "COPY_FAILED",
    ]


@pytest.mark.parametrize("level", list(ProofLevel))
def test_every_proof_level_constructs(level):
    assert ProofLevel(level.value) is level


@pytest.mark.parametrize("cause", list(ProofCause))
def test_every_proof_cause_constructs(cause):
    assert ProofCause(cause.value) is cause


# Spec AC6: tail keeps the last 20 lines.
def test_tail_keeps_only_the_last_twenty_lines():
    text = "\n".join(f"line {number}" for number in range(1, 26))
    assert tail(text).splitlines() == [f"line {number}" for number in range(6, 26)]
    assert len(tail(text).splitlines()) == 20


# Spec AC6 / PRD S1: each kept line is cut to 2,000 characters.
def test_tail_truncates_each_line_to_two_thousand_characters():
    assert tail("x" * 5000) == "x" * 2000


def test_tail_truncates_every_kept_line_not_only_the_last():
    text = "\n".join(["y" * 5000, "short", "z" * 5000])
    assert tail(text) == "\n".join(["y" * 2000, "short", "z" * 2000])


# Spec AC6: empty input is an empty tail.
def test_tail_of_empty_text_is_empty():
    assert tail("") == ""


# Spec AC6: joined with a newline, no trailing newline.
def test_tail_has_no_trailing_newline():
    assert tail("one\ntwo\n") == "one\ntwo"
    assert not tail("one\ntwo").endswith("\n")


def a_passed(**overrides):
    values = {
        "level": ProofLevel.TESTS_PASSED,
        "cause": None,
        "baseline": a_check(kind="baseline", returncode=0),
        "after": a_check(kind="after", returncode=0),
        "patch_applied": True,
    }
    values.update(overrides)
    return ProofResult(**values)


def an_unverified(cause=ProofCause.NO_TESTS_FOUND, **overrides):
    values = {
        "level": ProofLevel.UNVERIFIED,
        "cause": cause,
        "baseline": None,
        "after": None,
        "patch_applied": False,
    }
    values.update(overrides)
    return ProofResult(**values)


# Spec AC2 + M8: the only passing shape is a green after check on an applied patch.
def test_tests_passed_with_a_green_after_and_an_applied_patch_is_valid():
    result = a_passed()
    assert result.level is ProofLevel.TESTS_PASSED
    assert result.cause is None
    assert result.baseline.returncode == 0
    assert result.after.returncode == 0
    assert result.patch_applied is True


# Spec AC2: a passed level must not also name a cause.
def test_tests_passed_with_a_cause_raises():
    with pytest.raises(ValueError):
        a_passed(cause=ProofCause.TESTS_FAILED_AFTER)


# Spec AC2: no after check means nothing ran after the patch.
def test_tests_passed_without_an_after_check_raises():
    with pytest.raises(ValueError):
        a_passed(after=None)


# Spec AC2: an unapplied patch cannot be proven by a check that predates it.
def test_tests_passed_without_an_applied_patch_raises():
    with pytest.raises(ValueError):
        a_passed(patch_applied=False)


# Spec AC2: a red after check is not proof.
def test_tests_passed_with_a_non_zero_after_raises():
    with pytest.raises(ValueError):
        a_passed(after=a_check(kind="after", returncode=1))


# Plan edge case: exit code 0 while being killed is still a timeout, not proof.
def test_tests_passed_with_a_timed_out_after_raises():
    with pytest.raises(ValueError):
        a_passed(after=a_check(kind="after", returncode=0, timed_out=True))


# Spec AC3: UNVERIFIED without a cause would hide why nothing proved the patch.
def test_unverified_without_a_cause_raises():
    with pytest.raises(ValueError):
        an_unverified(cause=None)


# Spec AC4: a precondition failure has no checks at all and is still a valid result.
def test_unverified_with_neither_check_is_valid():
    result = an_unverified(cause=ProofCause.NO_TESTS_FOUND)
    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.NO_TESTS_FOUND
    assert result.baseline is None
    assert result.after is None
    assert result.patch_applied is False


# Spec: UNVERIFIED keeps the checks that did run, so a red after is still recorded.
def test_unverified_keeps_the_checks_that_ran():
    result = an_unverified(
        cause=ProofCause.TESTS_FAILED_AFTER,
        baseline=a_check(kind="baseline", returncode=0),
        after=a_check(kind="after", returncode=1),
        patch_applied=True,
    )
    assert result.baseline.returncode == 0
    assert result.after.returncode == 1


# Plan edge case: string values are coerced, matching the house style.
def test_proof_result_coerces_a_string_level_and_cause():
    result = ProofResult(
        level="UNVERIFIED",
        cause="NO_PATCH_PROPOSED",
        baseline=None,
        after=None,
        patch_applied=False,
    )
    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.NO_PATCH_PROPOSED


# Spec AC1: every cause constructs and round-trips through to_dict().
@pytest.mark.parametrize("cause", list(ProofCause))
def test_unverified_round_trips_every_cause(cause):
    result = an_unverified(cause=cause)
    parsed = json.loads(result.to_json())
    assert parsed == result.to_dict()
    assert parsed["level"] == "UNVERIFIED"
    assert parsed["cause"] == cause.value
    assert parsed["baseline"] is None
    assert parsed["after"] is None


# Spec AC1: every level is constructible and appears as a plain string.
def test_every_level_round_trips_through_to_dict():
    results = [a_passed(), an_unverified()]
    assert [result.to_dict()["level"] for result in results] == [
        proof_level.value for proof_level in ProofLevel
    ]


def test_to_dict_has_the_contract_keys_and_a_nested_check_record():
    parsed = a_passed().to_dict()
    assert set(parsed) == {"level", "cause", "baseline", "after", "patch_applied"}
    assert parsed["cause"] is None
    assert parsed["after"] == {
        "kind": "after",
        "command": ["python", "-m", "pytest", "-q"],
        "returncode": 0,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": "",
    }


# Spec AC5: no tuple, enum object or dataclass repr reaches the payload.
def test_to_json_holds_only_json_primitives():
    text = a_passed().to_json()
    assert json.loads(text) == a_passed().to_dict()
    for leak in (
        "ProofLevel.",
        "ProofCause.",
        "CheckResult(",
        "ProofResult(",
        "('",
    ):
        assert leak not in text


SUBPROCESS_SCRIPT = """
from tenon.prove import CheckResult, ProofCause, ProofResult

baseline = CheckResult(
    kind="baseline",
    command=("python", "-m", "pytest", "-q"),
    returncode=0,
    timed_out=False,
    stdout_tail="3 passed",
    stderr_tail="",
)
after = CheckResult(
    kind="after",
    command=("python", "-m", "pytest", "-q"),
    returncode=1,
    timed_out=False,
    stdout_tail="1 failed",
    stderr_tail="warning",
)
result = ProofResult(
    level="UNVERIFIED",
    cause=ProofCause.TESTS_FAILED_AFTER,
    baseline=baseline,
    after=after,
    patch_applied=True,
)
print(result.to_json(), end="")
"""


def to_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC5: byte-identical output across hash seeds.
def test_to_json_is_byte_stable_across_hash_seeds():
    assert to_json_with_hash_seed("0") == to_json_with_hash_seed("1")
