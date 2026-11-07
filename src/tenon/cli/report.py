"""Exit codes and reports over the shipped result contracts. No pipeline calls."""

import json
from dataclasses import dataclass
from typing import Any, Sequence

from tenon.detect import Change
from tenon.locate import LocateReason, LocateResult, Site
from tenon.propose import Proposal
from tenon.prove import (
    PROOF_RANK,
    CheckResult,
    ProofLevel,
    ProofResult,
    ProofStage,
    proof_rank,
)
from tenon.pr import PrResult, PrStatus

# Spec AC1: these reasons mean the analysis could not run, not that it found nothing.
_UNCLEAN_REASONS = frozenset(
    {LocateReason.NO_SDK_IMPORT, LocateReason.OPERATION_NOT_MAPPED}
)
_LEVEL_RANK = PROOF_RANK

SITE_LINE = "{path}:{line}:{column}  {shape}  {symbol}"
AMBIGUOUS_LINE = "ambiguous {reason}: {symbol} at {candidates}"
NO_AFFECTED_SITES_LINE = "no affected sites ({reason})"
NO_PATCH_LINE = "No patch: {reason}"


def _count(value: int, singular: str, plural: str | None = None) -> str:
    noun = singular if value == 1 else (plural or singular + "s")
    return f"{value} {noun}"
PROOF_LINE = "Proof: {level}"
CAUSE_LINE = "Cause: {cause}"
COMMAND_LINE = "Command: {command}"
STAGE_COMMAND_LINE = "{stage}: {command}"
BASELINE_EXIT_LINE = "Baseline exit: {exit}"
AFTER_EXIT_LINE = "After exit: {exit}"
SKIPPED_LINE = "Skipped: {path}:{line}:{column}  {symbol}  {reason}"
NO_SKIPPED_LINE = "Skipped: none"
PR_LINE = "PR: {url}"
PR_REFUSED_LINE = "PR refused: {refusal}"
PR_REFUSED_DETAIL_LINE = "PR refused: {refusal}: {detail}"
NOT_RUN = "not run"
TIMED_OUT = "timed out"
ERROR_TEXT = "tenon: {kind}: {message}"
ERROR_TEXT_CODE = "tenon: {kind}: {code}: {message}"
ERROR_TEXT_POINTER = "tenon: {kind}: at {pointer}: {message}"
ERROR_TEXT_CODE_POINTER = "tenon: {kind}: {code} at {pointer}: {message}"

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
    return proof_rank(level) >= proof_rank(require)


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


def _place(site: Site) -> str:
    return f"{site.path}:{site.line}:{site.column}"


def _check_counts(results: Sequence[LocateResult]) -> dict[str, int]:
    return {
        "changes": len(results),
        "certain": sum(len(result.certain) for result in results),
        "ambiguous": sum(len(result.ambiguous) for result in results),
    }


def _check_summary(counts: dict[str, int]) -> str:
    return ", ".join(
        (
            _count(counts["changes"], "change"),
            _count(counts["certain"], "certain site"),
            _count(counts["ambiguous"], "ambiguity group"),
        )
    )


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
    summary = _check_summary(_check_counts(results))
    return "\n\n".join([*blocks, summary]) + "\n"


def _exit(check: CheckResult | None) -> str:
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


_LEVEL_COUNT = {
    ProofLevel.TESTS_PASSED: "passed",
    ProofLevel.CHARACTERIZED: "characterized",
    ProofLevel.REPLAYED: "replayed",
    ProofLevel.TYPES_BUILD_ONLY: "build_only",
    ProofLevel.UNVERIFIED: "unverified",
}
_LEVEL_KEYS = tuple(_LEVEL_COUNT.values())


def fix_summary(results: Sequence[FixResult]) -> dict[str, int]:
    """The fix counts, shared by the fix and provider envelopes."""
    counts = {"changes": len(results)}
    counts["proposals"] = sum(1 for result in results if result.proposal.edits)
    counts.update(dict.fromkeys(_LEVEL_KEYS, 0))
    for result in results:
        counts[_LEVEL_COUNT[result.proof.level]] += 1
    counts["prs_opened"] = sum(
        1
        for result in results
        if result.pr is not None and result.pr.status is PrStatus.OPENED
    )
    counts["prs_refused"] = sum(
        1
        for result in results
        if result.pr is not None and result.pr.status is PrStatus.REFUSED
    )
    return counts


def _fix_summary(counts: dict[str, int]) -> str:
    return ", ".join(
        (
            _count(counts["changes"], "change"),
            _count(counts["proposals"], "proposal"),
            f"{counts['passed']} passed",
            f"{counts['characterized']} characterized",
            f"{counts['replayed']} replayed",
            f"{counts['build_only']} build-only",
            f"{counts['unverified']} unverified",
            _count(counts["prs_opened"], "PR opened", "PRs opened"),
            _count(counts["prs_refused"], "PR refused", "PRs refused"),
        )
    )


def _stage_checks(
    proof: ProofResult,
) -> list[tuple[ProofStage, dict[str, CheckResult]]]:
    """The proof's checks grouped by stage, in the runner's order."""
    grouped: dict[ProofStage, dict[str, CheckResult]] = {}
    for check in proof.checks:
        grouped.setdefault(check.stage, {})[check.kind] = check
    return [(stage, grouped[stage]) for stage in ProofStage if stage in grouped]


def _proof_lines(proof: ProofResult) -> list[str]:
    lines = [PROOF_LINE.format(level=proof.level.value)]
    if proof.level is ProofLevel.UNVERIFIED:
        lines.append(CAUSE_LINE.format(cause=proof.cause.value))
    stages = _stage_checks(proof)
    if not stages:
        return lines + [
            COMMAND_LINE.format(command=_command(proof)),
            BASELINE_EXIT_LINE.format(exit=_exit(proof.baseline)),
            AFTER_EXIT_LINE.format(exit=_exit(proof.after)),
        ]
    for stage, checks in stages:
        check = checks["baseline"] if "baseline" in checks else checks["after"]
        lines.extend(
            (
                STAGE_COMMAND_LINE.format(
                    stage=stage.value, command=" ".join(check.command)
                ),
                BASELINE_EXIT_LINE.format(exit=_exit(checks.get("baseline"))),
                AFTER_EXIT_LINE.format(exit=_exit(checks.get("after"))),
            )
        )
    return lines


def _fix_block(result: FixResult) -> str:
    lines = [_change_line(result.change)]
    diff = result.proposal.diff.rstrip("\n")
    if diff:
        lines.append(diff)
    if result.proposal.reason is not None:
        lines.append(NO_PATCH_LINE.format(reason=result.proposal.reason.value))
    lines.extend(_proof_lines(result.proof))
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
    summary = _fix_summary(fix_summary(results))
    return "\n\n".join([*blocks, summary]) + "\n"


def _canonical_json(payload: Any) -> str:
    return (
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        + "\n"
    )


def render_check_json(results: Sequence[LocateResult]) -> str:
    """One byte-stable check envelope composing the shipped dictionaries."""
    return _canonical_json(
        {
            "command": "check",
            "results": [result.to_dict() for result in results],
            "summary": _check_counts(results),
        }
    )


def fix_result_dict(result: FixResult) -> dict[str, object]:
    """One fix result item, shared by the fix and provider envelopes."""
    return {
        "change": result.change.to_dict(),
        "locate": result.locate.to_dict(),
        "proposal": result.proposal.to_dict(),
        "proof": result.proof.to_dict(),
        "pr": None if result.pr is None else result.pr.to_dict(),
    }


def render_fix_json(results: Sequence[FixResult]) -> str:
    """One byte-stable fix envelope composing the shipped dictionaries."""
    return _canonical_json(
        {
            "command": "fix",
            "results": [fix_result_dict(result) for result in results],
            "summary": fix_summary(results),
        }
    )


def render_provider_text(
    provider: str, migration: str, results: Sequence[FixResult]
) -> str:
    """The provider header, then the unchanged fix report."""
    return (
        f"provider: {provider}\nmigration: {migration}\n\n"
        + render_fix_text(results)
    )


def render_provider_json(
    provider: str,
    migration: str,
    repo: str,
    results: Sequence[FixResult],
) -> str:
    """One byte-stable provider envelope wrapping the shipped fix items."""
    return _canonical_json(
        {
            "command": "provider",
            "provider": provider,
            "migration": migration,
            "repo": repo,
            "results": [fix_result_dict(result) for result in results],
            "summary": fix_summary(results),
        }
    )


def render_error(
    kind: str,
    message: str,
    *,
    code: str | None = None,
    pointer: str | None = None,
    json_mode: bool = False,
) -> str:
    """One error object in JSON mode, or one stderr-ready line. Never a traceback."""
    if json_mode:
        return _canonical_json(
            {
                "error": {
                    "kind": kind,
                    "code": code,
                    "pointer": pointer,
                    "message": message,
                }
            }
        )
    if code is not None and pointer is not None:
        line = ERROR_TEXT_CODE_POINTER.format(
            kind=kind, code=code, pointer=pointer, message=message
        )
    elif code is not None:
        line = ERROR_TEXT_CODE.format(kind=kind, code=code, message=message)
    elif pointer is not None:
        line = ERROR_TEXT_POINTER.format(kind=kind, pointer=pointer, message=message)
    else:
        line = ERROR_TEXT.format(kind=kind, message=message)
    return line + "\n"

