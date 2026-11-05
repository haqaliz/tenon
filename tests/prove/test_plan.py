"""The proof plan: four optional stages, frozen and validated."""

import dataclasses
import hashlib
import sys
import tempfile
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location, diff, parse
from tenon.locate import LocateConfig, locate
from tenon.propose import Edit, Proposal, ProposalReason, propose
from tenon.propose.render import render
from tenon.prove import (
    ProofCause,
    ProofLevel,
    ProofStage,
    apply_diff,
    run_check,
)
from tenon.prove.plan import ProofPlan
from tenon.prove.run import prove_plan

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
PROOF_BASIC = FIXTURES / "proof-basic"
ACME = LocateConfig(sdk_package="acme.client")
COMMAND = (sys.executable, "-c", "import acme.billing")
FAILING = (sys.executable, "-c", "raise SystemExit(1)")

OLD_SPEC = """
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
"""

NEW_SPEC = OLD_SPEC.replace("amount:", "amount_cents:")

STAGES = [
    ("build", ProofStage.BUILD, ProofLevel.TYPES_BUILD_ONLY),
    ("characterize", ProofStage.CHARACTERIZE, ProofLevel.CHARACTERIZED),
    ("replay", ProofStage.REPLAY, ProofLevel.REPLAYED),
    ("tests", ProofStage.TESTS, ProofLevel.TESTS_PASSED),
]
FAILED_BEFORE = {
    ProofStage.BUILD: ProofCause.BUILD_FAILED_BEFORE,
    ProofStage.CHARACTERIZE: ProofCause.CHARACTERIZE_FAILED_BEFORE,
    ProofStage.REPLAY: ProofCause.REPLAY_FAILED_BEFORE,
    ProofStage.TESTS: ProofCause.TESTS_FAILED_BEFORE,
}
FAILED_AFTER = {
    ProofStage.BUILD: ProofCause.BUILD_FAILED_AFTER,
    ProofStage.CHARACTERIZE: ProofCause.CHARACTERIZE_FAILED_AFTER,
    ProofStage.REPLAY: ProofCause.REPLAY_FAILED_AFTER,
    ProofStage.TESTS: ProofCause.TESTS_FAILED_AFTER,
}


def tree_hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(root).rglob("*"))
        if path.is_file()
    }


# Spec AC9: every case leaves the source tree and the temp dir untouched.
@pytest.fixture(autouse=True)
def source_unchanged_and_copies_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    before = tree_hashes(PROOF_BASIC)

    yield

    assert tree_hashes(PROOF_BASIC) == before
    assert list(tmp_path.glob("tenon-prove-*")) == []


def a_rename_proposal(root=PROOF_BASIC, proposer=None):
    """T1 diff -> T2 locate -> T3 propose over the fixture."""
    change = diff(parse(OLD_SPEC, "old"), parse(NEW_SPEC, "new")).changes[0]
    located = locate(change, root, ACME)
    if proposer is None:
        return propose(change, located, root)
    return propose(change, located, root, proposer)


class BrokenProposer:
    """Renames the keyword to something that makes the import a SyntaxError."""

    def propose(self, change, located, root):
        return tuple(
            Edit(
                path=site.path,
                line=site.line,
                column=site.column,
                shape=site.shape,
                old=site.symbol,
                new="1bad",
            )
            for site in located.certain
            if site.symbol == change.before
        )


def an_empty_proposal(reason):
    return Proposal(
        change=Change(
            kind=ChangeKind.RENAMED,
            location=Location(pointer="#/components/schemas/Charge/properties"),
            before="amount",
            after="amount_cents",
        ),
        edits=(),
        skipped=(),
        diff="",
        reason=reason,
    )


def a_plan(**stages):
    return ProofPlan(**stages)


def an_all_stage_plan():
    return a_plan(
        build=COMMAND,
        characterize=COMMAND,
        replay=COMMAND,
        tests=COMMAND,
    )


def a_garbage_proposal():
    proposal = a_rename_proposal()
    return Proposal(
        change=proposal.change,
        edits=proposal.edits,
        skipped=proposal.skipped,
        diff="this is not a diff\n",
    )


def a_hanging_proposal():
    proposal = a_rename_proposal()
    old = (PROOF_BASIC / "acme/billing.py").read_text(encoding="utf-8")
    new = old.replace(
        "def create_charge", "while True:\n    pass\n\n\ndef create_charge"
    )
    return Proposal(
        change=proposal.change,
        edits=proposal.edits,
        skipped=proposal.skipped,
        diff=render({"acme/billing.py": (old, new)}),
    )


def check_order(result):
    return [(check.kind, check.stage) for check in result.checks]


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


# Spec AC1/AC2: one green stage proves its own rung and records both checks.
@pytest.mark.parametrize("field, stage, level", STAGES)
def test_one_green_stage_yields_its_level(field, stage, level):
    result = prove_plan(
        a_rename_proposal(), PROOF_BASIC, a_plan(**{field: COMMAND})
    )

    assert result.level is level
    assert result.cause is None
    assert result.patch_applied is True
    assert [check.kind for check in result.checks] == ["baseline", "after"]
    assert [check.stage for check in result.checks] == [stage, stage]
    assert result.baseline.kind == "baseline"
    assert result.after.kind == "after"
    assert result.baseline.returncode == 0
    assert result.after.returncode == 0


# Spec AC4: an empty plan is named before any copy or command.
def test_an_empty_plan_is_no_proof_command_before_copying(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("an empty plan must not copy")

    monkeypatch.setattr("tenon.prove.copy.copy_tree", unexpected)

    result = prove_plan(a_rename_proposal(), PROOF_BASIC, a_plan())

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.NO_PROOF_COMMAND
    assert result.baseline is None
    assert result.after is None
    assert result.checks == ()
    assert result.patch_applied is False


# Spec AC5: a red baseline stops the run, names its stage and never applies.
@pytest.mark.parametrize("field, stage, level", STAGES)
def test_a_red_baseline_stops_before_applying(field, stage, level, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("a red baseline must not apply the patch")

    monkeypatch.setattr("tenon.prove.run.apply_diff", unexpected)

    result = prove_plan(
        a_rename_proposal(), PROOF_BASIC, a_plan(**{field: FAILING})
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is FAILED_BEFORE[stage]
    assert result.patch_applied is False
    assert result.after is None
    assert result.checks == (result.baseline,)
    assert result.baseline.stage is stage
    assert result.baseline.kind == "baseline"
    assert result.baseline.returncode == 1


# Spec AC4: a green baseline and a red after is the patch's fault, per stage.
@pytest.mark.parametrize("field, stage, level", STAGES)
def test_a_red_after_is_the_stages_failed_after(field, stage, level):
    result = prove_plan(
        a_rename_proposal(proposer=BrokenProposer()),
        PROOF_BASIC,
        a_plan(**{field: COMMAND}),
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is FAILED_AFTER[stage]
    assert result.patch_applied is True
    assert [check.kind for check in result.checks] == ["baseline", "after"]
    assert [check.stage for check in result.checks] == [stage, stage]
    assert result.checks[0].returncode == 0
    assert result.checks[1].returncode != 0
    assert result.baseline is result.checks[0]
    assert result.after is result.checks[1]


# Spec AC5: preconditions win over the empty plan, as in T4.
def test_a_stale_proposal_with_an_empty_plan_is_patch_did_not_apply():
    result = prove_plan(
        an_empty_proposal(ProposalReason.STALE_SITE), PROOF_BASIC, a_plan()
    )

    assert result.cause is ProofCause.PATCH_DID_NOT_APPLY
    assert result.checks == ()


# Spec / PRD M4: the plan argument is a ProofPlan, unlike the T4 command sequence.
def test_a_non_plan_argument_raises_value_error():
    with pytest.raises(ValueError):
        prove_plan(a_rename_proposal(), PROOF_BASIC, COMMAND)


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_raises_value_error(timeout):
    with pytest.raises(ValueError):
        prove_plan(
            a_rename_proposal(), PROOF_BASIC, a_plan(tests=COMMAND), timeout
        )


# Spec AC3: every configured stage green records all eight checks in stage order.
def test_all_four_green_stages_pass_the_tests_level():
    result = prove_plan(a_rename_proposal(), PROOF_BASIC, an_all_stage_plan())

    assert result.level is ProofLevel.TESTS_PASSED
    assert result.cause is None
    assert result.patch_applied is True
    assert check_order(result) == [
        ("baseline", ProofStage.BUILD),
        ("baseline", ProofStage.CHARACTERIZE),
        ("baseline", ProofStage.REPLAY),
        ("baseline", ProofStage.TESTS),
        ("after", ProofStage.BUILD),
        ("after", ProofStage.CHARACTERIZE),
        ("after", ProofStage.REPLAY),
        ("after", ProofStage.TESTS),
    ]
    assert all(check.returncode == 0 for check in result.checks)
    assert result.baseline is result.checks[3]
    assert result.after is result.checks[7]


# Spec AC4: a green weaker stage does not mask a red stronger one.
def test_a_green_build_with_red_tests_is_unverified_not_build_only():
    plan = a_plan(
        build=(sys.executable, "-c", "import acme.client"),
        tests=COMMAND,
    )

    result = prove_plan(
        a_rename_proposal(proposer=BrokenProposer()), PROOF_BASIC, plan
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.TESTS_FAILED_AFTER
    assert result.patch_applied is True
    assert check_order(result) == [
        ("baseline", ProofStage.BUILD),
        ("baseline", ProofStage.TESTS),
        ("after", ProofStage.BUILD),
        ("after", ProofStage.TESTS),
    ]
    assert result.checks[2].returncode == 0
    assert result.checks[3].returncode != 0
    assert result.baseline is result.checks[1]
    assert result.after is result.checks[3]


# Spec AC5: a red build baseline never applies and never runs a later baseline.
def test_a_red_build_baseline_stops_before_apply_and_later_baselines(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("a red build baseline must not apply the patch")

    monkeypatch.setattr("tenon.prove.run.apply_diff", unexpected)

    result = prove_plan(
        a_rename_proposal(),
        PROOF_BASIC,
        a_plan(build=FAILING, tests=COMMAND),
    )

    assert result.cause is ProofCause.BUILD_FAILED_BEFORE
    assert result.baseline.stage is ProofStage.BUILD
    assert result.checks == (result.baseline,)
    assert result.after is None
    assert result.patch_applied is False


# Spec AC5: a red replay baseline keeps the earlier green baselines and stops.
def test_a_red_replay_baseline_stops_before_apply(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("a red replay baseline must not apply the patch")

    monkeypatch.setattr("tenon.prove.run.apply_diff", unexpected)

    result = prove_plan(
        a_rename_proposal(),
        PROOF_BASIC,
        a_plan(build=COMMAND, replay=FAILING, tests=COMMAND),
    )

    assert result.cause is ProofCause.REPLAY_FAILED_BEFORE
    assert check_order(result) == [
        ("baseline", ProofStage.BUILD),
        ("baseline", ProofStage.REPLAY),
    ]
    assert result.checks[0].returncode == 0
    assert result.baseline is result.checks[1]
    assert result.after is None
    assert result.patch_applied is False


# Spec AC6: a rejected diff keeps every baseline and runs no after check.
def test_a_garbage_diff_is_patch_did_not_apply_with_the_baselines():
    result = prove_plan(
        a_garbage_proposal(),
        PROOF_BASIC,
        a_plan(build=COMMAND, tests=COMMAND),
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.PATCH_DID_NOT_APPLY
    assert check_order(result) == [
        ("baseline", ProofStage.BUILD),
        ("baseline", ProofStage.TESTS),
    ]
    assert all(check.returncode == 0 for check in result.checks)
    assert result.baseline is result.checks[1]
    assert result.after is None
    assert result.patch_applied is False


# Spec AC6: the patch is applied once, not once per stage.
def test_the_diff_is_applied_once(monkeypatch):
    calls = []

    def counting(copy, diff):
        calls.append(diff)
        return apply_diff(copy, diff)

    monkeypatch.setattr("tenon.prove.run.apply_diff", counting)

    result = prove_plan(
        a_rename_proposal(),
        PROOF_BASIC,
        a_plan(build=COMMAND, tests=COMMAND),
    )

    assert result.level is ProofLevel.TESTS_PASSED
    assert len(calls) == 1
    assert "amount_cents" in calls[0]


# Spec AC7: a baseline timeout names the timeout and the stage, before apply.
def test_a_baseline_timeout_is_check_timed_out_with_its_stage():
    result = prove_plan(
        a_rename_proposal(),
        PROOF_BASIC,
        a_plan(
            build=(sys.executable, "-c", "import time; time.sleep(30)"),
            tests=COMMAND,
        ),
        timeout=0.2,
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.CHECK_TIMED_OUT
    assert result.baseline.stage is ProofStage.BUILD
    assert result.baseline.timed_out is True
    assert result.baseline.returncode is None
    assert result.after is None
    assert result.checks == (result.baseline,)
    assert result.patch_applied is False


# Spec AC7: an after timeout keeps the applied patch and the stage on the record.
def test_a_tests_after_timeout_keeps_the_applied_patch():
    result = prove_plan(
        a_hanging_proposal(),
        PROOF_BASIC,
        a_plan(
            build=(sys.executable, "-c", "import acme.client"),
            tests=COMMAND,
        ),
        timeout=0.5,
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.CHECK_TIMED_OUT
    assert result.after.stage is ProofStage.TESTS
    assert result.after.timed_out is True
    assert result.after.returncode is None
    assert result.patch_applied is True
    assert check_order(result) == [
        ("baseline", ProofStage.BUILD),
        ("baseline", ProofStage.TESTS),
        ("after", ProofStage.BUILD),
        ("after", ProofStage.TESTS),
    ]


# Spec AC10: the same inputs produce the same checks in the same order.
def test_the_same_plan_serialises_identically_twice():
    first = prove_plan(a_rename_proposal(), PROOF_BASIC, an_all_stage_plan())
    second = prove_plan(a_rename_proposal(), PROOF_BASIC, an_all_stage_plan())

    assert check_order(first) == check_order(second)
    assert first.to_json() == second.to_json()


# Spec AC9: checks run in a temp copy, and that copy is gone afterwards.
def test_checks_run_in_a_copy_that_is_removed(monkeypatch):
    seen = []

    def spy(command, cwd, kind, timeout):
        seen.append(Path(cwd))
        return run_check(command, cwd, kind, timeout)

    monkeypatch.setattr("tenon.prove.run.run_check", spy)

    result = prove_plan(a_rename_proposal(), PROOF_BASIC, an_all_stage_plan())

    assert result.level is ProofLevel.TESTS_PASSED
    assert len(seen) == 8
    assert all(PROOF_BASIC not in path.parents for path in seen)
    assert all(not path.exists() for path in seen)
