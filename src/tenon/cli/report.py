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

