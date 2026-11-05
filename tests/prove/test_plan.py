"""The proof plan: four optional stages, frozen and validated."""

import dataclasses

import pytest

from tenon.prove.plan import ProofPlan


def a_plan(**overrides):
    values = {"tests": (), "characterize": (), "replay": (), "build": ()}
    values.update(overrides)
    return ProofPlan(**values)


# Plan phase 1: every stage defaults to an empty tuple.
def test_a_plan_defaults_to_four_empty_tuples():
    plan = ProofPlan()

    assert plan.tests == ()
    assert plan.characterize == ()
    assert plan.replay == ()
    assert plan.build == ()
    assert plan.is_empty() is True


# Plan phase 1: any sequence is accepted and stored as a tuple.
@pytest.mark.parametrize("field", ["tests", "characterize", "replay", "build"])
def test_each_stage_coerces_a_sequence_to_a_tuple(field):
    plan = a_plan(**{field: ["python", "-m", "pytest"]})

    assert getattr(plan, field) == ("python", "-m", "pytest")
    assert isinstance(getattr(plan, field), tuple)
    assert plan.is_empty() is False


# Spec AC8 / PRD M3: a bare string would need a shell, so it is rejected.
@pytest.mark.parametrize("field", ["tests", "characterize", "replay", "build"])
def test_a_bare_string_stage_raises_value_error(field):
    with pytest.raises(ValueError):
        a_plan(**{field: "python -m pytest"})


# Spec AC8: one configured stage is a plan that can run.
def test_a_plan_with_one_stage_is_not_empty():
    assert a_plan(replay=("python", "-m", "replay")).is_empty() is False


# PRD M3: the plan is frozen and slotted.
def test_a_plan_is_frozen_and_slotted():
    plan = a_plan(tests=("python", "-m", "pytest"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.tests = ()
    assert not hasattr(plan, "__dict__")
