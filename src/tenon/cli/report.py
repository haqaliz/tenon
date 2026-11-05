"""Exit codes and reports over the shipped result contracts. No pipeline calls."""

import json
from dataclasses import dataclass
from typing import Any, Sequence

from tenon.detect import Change
from tenon.locate import LocateReason, LocateResult
from tenon.propose import Proposal
from tenon.prove import ProofLevel, ProofResult
from tenon.pr import PrResult, PrStatus

# Spec AC1: these reasons mean the analysis could not run, not that it found nothing.
_UNCLEAN_REASONS = frozenset(
    {LocateReason.NO_SDK_IMPORT, LocateReason.OPERATION_NOT_MAPPED}
)
_LEVEL_RANK = {ProofLevel.UNVERIFIED: 0, ProofLevel.TESTS_PASSED: 1}

CHECK_SUMMARY = "{changes} changes, {certain} certain sites, {ambiguous} ambiguity groups"
SITE_LINE = "{path}:{line}:{column}  {shape}  {symbol}"
AMBIGUOUS_LINE = "ambiguous {reason}: {symbol} at {candidates}"
NO_AFFECTED_SITES_LINE = "no affected sites ({reason})"
FIX_SUMMARY = (
    "{changes} changes, {proposals} proposals, {passed} passed, "
    "{unverified} unverified, {prs_opened} PRs opened, {prs_refused} PRs refused"
)
PROOF_LINE = "Proof: {level}"
CAUSE_LINE = "Cause: {cause}"
COMMAND_LINE = "Command: {command}"
BASELINE_EXIT_LINE = "Baseline exit: {exit}"
AFTER_EXIT_LINE = "After exit: {exit}"
SKIPPED_LINE = "Skipped: {path}:{line}:{column}  {symbol}  {reason}"
NO_SKIPPED_LINE = "Skipped: none"
PR_LINE = "PR: {url}"
PR_REFUSED_LINE = "PR refused: {refusal}"
PR_REFUSED_DETAIL_LINE = "PR refused: {refusal}: {detail}"
NOT_RUN = "not run"
TIMED_OUT = "timed out"

_SCALARS = (str, int, float, bool, type(None))



@dataclass(frozen=True, slots=True)
class FixResult:
    """One change carried through locate, propose and prove, with its optional PR."""

    change: Change
    locate: LocateResult
    proposal: Proposal
    proof: ProofResult
    pr: PrResult | None = None


def check_exit(results: Sequence[LocateResult]) -> int:
    """0 only when every change is clean and every analysis ran."""
    for result in results:
        if result.certain or result.ambiguous:
            return 1
        if result.reason in _UNCLEAN_REASONS:
            return 1
    return 0


def _meets(level: ProofLevel, require: ProofLevel) -> bool:
    return _LEVEL_RANK[level] >= _LEVEL_RANK[require]


def fix_exit(changes: int, results: Sequence[FixResult], require: ProofLevel) -> int:
    """0 only when every processed proposal reached ``require`` and every PR opened."""
    if changes == 0:
        return 0
    if not results:
        return 1
    for result in results:
        if not _meets(result.proof.level, require):
            return 1
        if result.pr is not None and result.pr.status is not PrStatus.OPENED:
            return 1
    return 0


def _scalar(value: Any) -> str:
    """A readable scalar; every other JSON value is canonical and compact."""
    if isinstance(value, _SCALARS):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _location(change: Change) -> str:
    location = change.location
    if location.method and location.path:
        return f"{location.method.upper()} {location.path}"
    return location.pointer


def _change_line(change: Change) -> str:
    line = f"{change.kind.value} {_location(change)}"
    if change.before is not None or change.after is not None:
        line += f": {_scalar(change.before)} -> {_scalar(change.after)}"
    return line


def _place(site: Any) -> str:
    return f"{site.path}:{site.line}:{site.column}"


def _check_counts(results: Sequence[LocateResult]) -> dict[str, int]:
    return {
        "changes": len(results),
        "certain": sum(len(result.certain) for result in results),
        "ambiguous": sum(len(result.ambiguous) for result in results),
    }


def _check_block(result: LocateResult) -> str:
    lines = [_change_line(result.change)]
    lines.extend(
        SITE_LINE.format(
            path=site.path,
            line=site.line,
            column=site.column,
            shape=site.shape.value,
            symbol=site.symbol,
        )
        for site in result.certain
    )
    lines.extend(
        AMBIGUOUS_LINE.format(
            reason=group.reason.value,
            symbol=group.symbol,
            candidates=", ".join(_place(site) for site in group.candidates),
        )
        for group in result.ambiguous
    )
    if result.reason is not None:
        lines.append(NO_AFFECTED_SITES_LINE.format(reason=result.reason.value))
    return "\n".join(lines)


def render_check_text(results: Sequence[LocateResult]) -> str:
    """One deterministic block per change, then the counts, one trailing newline."""
    blocks = [_check_block(result) for result in results]
    summary = CHECK_SUMMARY.format(**_check_counts(results))
    return "\n\n".join([*blocks, summary]) + "\n"


def _exit(check: Any) -> str:
    if check is None:
        return NOT_RUN
    if check.timed_out:
        return TIMED_OUT
    if check.returncode is None:
        return NOT_RUN
    return str(check.returncode)


def _command(proof: ProofResult) -> str:
    check = proof.baseline if proof.baseline is not None else proof.after
    return " ".join(check.command) if check is not None else NOT_RUN


def _fix_counts(results: Sequence[FixResult]) -> dict[str, int]:
    return {
        "changes": len(results),
        "proposals": sum(1 for result in results if result.proposal.edits),
        "passed": sum(
            1 for result in results if result.proof.level is ProofLevel.TESTS_PASSED
        ),
        "unverified": sum(
            1 for result in results if result.proof.level is ProofLevel.UNVERIFIED
        ),
        "prs_opened": sum(
            1
            for result in results
            if result.pr is not None and result.pr.status is PrStatus.OPENED
        ),
        "prs_refused": sum(
            1
            for result in results
            if result.pr is not None and result.pr.status is PrStatus.REFUSED
        ),
    }


def _fix_block(result: FixResult) -> str:
    lines = [_change_line(result.change)]
    diff = result.proposal.diff.rstrip("\n")
    if diff:
        lines.append(diff)
    proof = result.proof
    lines.append(PROOF_LINE.format(level=proof.level.value))
    if proof.level is ProofLevel.UNVERIFIED:
        lines.append(CAUSE_LINE.format(cause=proof.cause.value))
    lines.extend(
        [
            COMMAND_LINE.format(command=_command(proof)),
            BASELINE_EXIT_LINE.format(exit=_exit(proof.baseline)),
            AFTER_EXIT_LINE.format(exit=_exit(proof.after)),
        ]
    )
    if result.proposal.skipped:
        lines.extend(
            SKIPPED_LINE.format(
                path=entry.site.path,
                line=entry.site.line,
                column=entry.site.column,
                symbol=entry.site.symbol,
                reason=entry.reason.value,
            )
            for entry in result.proposal.skipped
        )
    else:
        lines.append(NO_SKIPPED_LINE)

    pr = result.pr
    if pr is not None:
        if pr.status is PrStatus.OPENED:
            lines.append(PR_LINE.format(url=pr.url))
        elif pr.detail:
            lines.append(
                PR_REFUSED_DETAIL_LINE.format(
                    refusal=pr.refusal.value, detail=pr.detail
                )
            )
        else:
            lines.append(PR_REFUSED_LINE.format(refusal=pr.refusal.value))
    return "\n".join(lines)


def render_fix_text(results: Sequence[FixResult]) -> str:
    """One block with diff and proof per change, then the counts."""
    blocks = [_fix_block(result) for result in results]
    summary = FIX_SUMMARY.format(**_fix_counts(results))
    return "\n\n".join([*blocks, summary]) + "\n"


