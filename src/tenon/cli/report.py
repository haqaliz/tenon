"""Exit codes and reports over the shipped result contracts. No pipeline calls."""

from dataclasses import dataclass
from typing import Sequence

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
