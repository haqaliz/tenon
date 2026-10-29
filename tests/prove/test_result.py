import pytest

from tenon.prove import CheckResult, ProofCause, ProofLevel, tail


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
