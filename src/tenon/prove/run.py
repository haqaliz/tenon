"""Run one check in the copy and record what happened."""

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from tenon.propose import Proposal, ProposalReason

from .copy import CopyError, apply_diff, isolated_copy
from .plan import ProofPlan
from .result import CheckResult, ProofCause, ProofLevel, ProofResult, ProofStage, tail

_STAGES = (
    (ProofStage.BUILD, "build"),
    (ProofStage.CHARACTERIZE, "characterize"),
    (ProofStage.REPLAY, "replay"),
    (ProofStage.TESTS, "tests"),
)

_LEVEL_FOR_STAGE = {
    ProofStage.BUILD: ProofLevel.TYPES_BUILD_ONLY,
    ProofStage.CHARACTERIZE: ProofLevel.CHARACTERIZED,
    ProofStage.REPLAY: ProofLevel.REPLAYED,
    ProofStage.TESTS: ProofLevel.TESTS_PASSED,
}

_FAILED_BEFORE = {
    ProofStage.BUILD: ProofCause.BUILD_FAILED_BEFORE,
    ProofStage.CHARACTERIZE: ProofCause.CHARACTERIZE_FAILED_BEFORE,
    ProofStage.REPLAY: ProofCause.REPLAY_FAILED_BEFORE,
    ProofStage.TESTS: ProofCause.TESTS_FAILED_BEFORE,
}

_FAILED_AFTER = {
    ProofStage.BUILD: ProofCause.BUILD_FAILED_AFTER,
    ProofStage.CHARACTERIZE: ProofCause.CHARACTERIZE_FAILED_AFTER,
    ProofStage.REPLAY: ProofCause.REPLAY_FAILED_AFTER,
    ProofStage.TESTS: ProofCause.TESTS_FAILED_AFTER,
}


def _text(value: str | bytes | None) -> str:
    """TimeoutExpired may carry bytes even in text mode; normalise to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_check(
    command: Sequence[str],
    cwd: str | Path,
    kind: str,
    timeout: float,
) -> CheckResult:
    """Run ``command`` in ``cwd`` with a timeout, capping both output tails.

    A missing executable is a check that exited 127, not an exception: the
    command the user gave never ran.
    """
    if isinstance(command, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    command = tuple(command)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            kind=kind,
            command=command,
            returncode=None,
            timed_out=True,
            stdout_tail=tail(_text(exc.stdout)),
            stderr_tail=tail(_text(exc.stderr)),
        )
    except OSError as exc:
        return CheckResult(
            kind=kind,
            command=command,
            returncode=127,
            timed_out=False,
            stderr_tail=f"could not run {command[0]!r}: {exc}",
        )
    return CheckResult(
        kind=kind,
        command=command,
        returncode=completed.returncode,
        timed_out=False,
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )


def _unverified(
    cause: ProofCause,
    *,
    baseline: CheckResult | None = None,
    after: CheckResult | None = None,
    patch_applied: bool = False,
    checks: tuple[CheckResult, ...] = (),
) -> ProofResult:
    return ProofResult(
        level=ProofLevel.UNVERIFIED,
        cause=cause,
        baseline=baseline,
        after=after,
        patch_applied=patch_applied,
        checks=checks,
    )


def _run(
    proposal: Proposal,
    copy: str | Path,
    plan: ProofPlan,
    timeout: float,
) -> ProofResult:
    """All baselines, one apply, all afters; fail closed on any red check."""
    configured = [
        (stage, getattr(plan, field))
        for stage, field in _STAGES
        if getattr(plan, field)
    ]
    baselines: list[CheckResult] = []
    for stage, command in configured:
        baseline = replace(run_check(command, copy, "baseline", timeout), stage=stage)
        baselines.append(baseline)
        if baseline.timed_out:
            return _unverified(
                ProofCause.CHECK_TIMED_OUT,
                baseline=baseline,
                checks=tuple(baselines),
            )
        if baseline.returncode != 0:
            return _unverified(
                _FAILED_BEFORE[stage],
                baseline=baseline,
                checks=tuple(baselines),
            )
    try:
        applied = apply_diff(copy, proposal.diff)
    except subprocess.TimeoutExpired:
        applied = False
    if not applied:
        return _unverified(
            ProofCause.PATCH_DID_NOT_APPLY,
            baseline=baselines[-1],
            checks=tuple(baselines),
        )
    afters: list[CheckResult] = []
    for stage, command in configured:
        after = replace(run_check(command, copy, "after", timeout), stage=stage)
        afters.append(after)
        checks = tuple(baselines + afters)
        if after.timed_out:
            return _unverified(
                ProofCause.CHECK_TIMED_OUT,
                baseline=baselines[-1],
                after=after,
                patch_applied=True,
                checks=checks,
            )
        if after.returncode != 0:
            return _unverified(
                _FAILED_AFTER[stage],
                baseline=baselines[-1],
                after=after,
                patch_applied=True,
                checks=checks,
            )
    return ProofResult(
        level=_LEVEL_FOR_STAGE[configured[-1][0]],
        baseline=baselines[-1],
        after=afters[-1],
        patch_applied=True,
        checks=tuple(baselines + afters),
    )


def prove_plan(
    proposal: Proposal,
    root: str | Path,
    plan: ProofPlan,
    timeout: float = 300.0,
) -> ProofResult:
    """Prove ``proposal`` under every configured stage of ``plan``.

    First match wins: plan validation, preconditions, empty plan, copy. A red
    baseline is never blamed on the patch and never applies it.
    """
    if not isinstance(plan, ProofPlan):
        raise ValueError(f"plan must be a ProofPlan: {plan!r}")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    if not proposal.edits:
        if proposal.reason is ProposalReason.STALE_SITE:
            return _unverified(ProofCause.PATCH_DID_NOT_APPLY)
        return _unverified(ProofCause.NO_PATCH_PROPOSED)
    if plan.is_empty():
        return _unverified(ProofCause.NO_PROOF_COMMAND)
    try:
        with isolated_copy(root) as copy:
            return _run(proposal, copy, plan, timeout)
    except CopyError:
        return _unverified(ProofCause.COPY_FAILED)


def prove(
    proposal: Proposal,
    root: str | Path,
    command: Sequence[str],
    timeout: float = 300.0,
) -> ProofResult:
    """The T4 shortcut: prove ``proposal`` under a tests-only plan.

    An empty command is named before copying. Every other case is the ladder
    with one stage, so the results and causes stay exactly as they were.
    """
    if isinstance(command, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    if not command:
        return _unverified(ProofCause.NO_TESTS_FOUND)
    return prove_plan(proposal, root, ProofPlan(tests=tuple(command)), timeout)
