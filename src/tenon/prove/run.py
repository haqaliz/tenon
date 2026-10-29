"""Run one check in the copy and record what happened."""

import os
import subprocess
from pathlib import Path
from typing import Sequence

from tenon.propose import Proposal, ProposalReason

from .copy import CopyError, apply_diff, isolated_copy
from .result import CheckResult, ProofCause, ProofLevel, ProofResult, tail


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
) -> ProofResult:
    return ProofResult(
        level=ProofLevel.UNVERIFIED,
        cause=cause,
        baseline=baseline,
        after=after,
        patch_applied=patch_applied,
    )


def _run(
    proposal: Proposal,
    copy: str | Path,
    command: Sequence[str],
    timeout: float,
) -> ProofResult:
    """Baseline, apply, after. The only place ``TESTS_PASSED`` is constructed."""
    baseline = run_check(command, copy, "baseline", timeout)
    if baseline.timed_out:
        return _unverified(ProofCause.CHECK_TIMED_OUT, baseline=baseline)
    if baseline.returncode != 0:
        return _unverified(ProofCause.TESTS_FAILED_BEFORE, baseline=baseline)
    try:
        applied = apply_diff(copy, proposal.diff)
    except subprocess.TimeoutExpired:
        applied = False
    if not applied:
        return _unverified(ProofCause.PATCH_DID_NOT_APPLY, baseline=baseline)
    after = run_check(command, copy, "after", timeout)
    if after.timed_out:
        return _unverified(
            ProofCause.CHECK_TIMED_OUT,
            baseline=baseline,
            after=after,
            patch_applied=True,
        )
    if after.returncode != 0:
        return _unverified(
            ProofCause.TESTS_FAILED_AFTER,
            baseline=baseline,
            after=after,
            patch_applied=True,
        )
    return ProofResult(
        level=ProofLevel.TESTS_PASSED,
        baseline=baseline,
        after=after,
        patch_applied=True,
    )


def prove(
    proposal: Proposal,
    root: str | Path,
    command: Sequence[str],
    timeout: float = 300.0,
) -> ProofResult:
    """Prove ``proposal`` in a fresh copy of ``root`` under ``command``.

    First match wins: preconditions, copy, baseline, apply, after. A red
    baseline is never blamed on the patch and never applies it.
    """
    if isinstance(command, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    if timeout is None or timeout <= 0:
        raise ValueError(f"timeout must be positive: {timeout!r}")
    if not command:
        return _unverified(ProofCause.NO_TESTS_FOUND)
    if not proposal.edits:
        if proposal.reason is ProposalReason.STALE_SITE:
            return _unverified(ProofCause.PATCH_DID_NOT_APPLY)
        return _unverified(ProofCause.NO_PATCH_PROPOSED)
    try:
        with isolated_copy(root) as copy:
            return _run(proposal, copy, command, timeout)
    except (CopyError, OSError):
        return _unverified(ProofCause.COPY_FAILED)
