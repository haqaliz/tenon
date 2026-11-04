"""Render a deterministic PR draft from a proposal and its proof."""

import hashlib
import json
import re
from typing import Any, Sequence

from tenon.detect import Change, Unanalyzed
from tenon.propose import Proposal, Skipped
from tenon.prove import ProofLevel, ProofResult

from .result import PrDraft

_SCALARS = (str, int, float, bool, type(None))
_NON_SLUG = re.compile(r"[^a-z0-9]+")

FOOTER = "Opened by Tenon. No merge was performed."
TESTS_PASSED_SENTENCE = (
    "The command returned 0 before and after the patch in an isolated copy."
)
TESTS_PASSED_PROOF = (
    "The check ran green before and after the patch, so the change did not break "
    "the command Tenon ran. It does not prove the change is correct."
)

_LEVEL_SENTENCES = {ProofLevel.TESTS_PASSED: TESTS_PASSED_SENTENCE}
_PROOF_PARAGRAPHS = {ProofLevel.TESTS_PASSED: TESTS_PASSED_PROOF}


def _scalar(value: Any) -> str:
    """A readable scalar; every other JSON value is canonical and compact."""
    if isinstance(value, _SCALARS):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _change_json(change: Change) -> str:
    return json.dumps(
        change.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _slug(summary: str) -> str:
    slug = _NON_SLUG.sub("-", summary.lower()).strip("-")
    return slug[:48].strip("-") or "change"


def _location(change: Change) -> str:
    location = change.location
    if location.method and location.path:
        return f"{location.method.upper()} {location.path}"
    return location.pointer


def _summary(change: Change) -> str:
    summary = f"{change.kind.value} {_location(change)}"
    if change.before is not None or change.after is not None:
        summary += f": {_scalar(change.before)} -> {_scalar(change.after)}"
    return summary


def _title(proof: ProofResult, summary: str) -> str:
    return f"[{proof.level.value}] tenon: {summary}"


def _commit_message(summary: str) -> str:
    return f"tenon: {summary}"


def _branch(change: Change, diff: str) -> str:
    digest = hashlib.sha256(
        (_change_json(change) + "\0" + diff).encode("utf-8")
    ).hexdigest()
    return f"tenon/{_slug(_summary(change))}-{digest[:8]}"


def _code(text: str) -> str:
    """One inline code span; a backtick or newline cannot break out of it."""
    cleaned = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    cleaned = cleaned.replace("`", "'")
    return f"`{cleaned}`"


def _level_sentence(proof: ProofResult) -> str:
    return _LEVEL_SENTENCES[proof.level]


def _change_section(change: Change) -> str:
    return "\n".join(
        [
            "### Change",
            "",
            f"- Kind: {_code(change.kind.value)}",
            f"- Location: {_code(_location(change))}",
            f"- Before: {_code(_scalar(change.before))}",
            f"- After: {_code(_scalar(change.after))}",
            f"- Breaking: {_code(_scalar(change.breaking))}",
            f"- Confidence: {_code(change.confidence)}",
        ]
    )


def _check_section(proof: ProofResult) -> str:
    check = proof.baseline if proof.baseline is not None else proof.after
    lines = [
        "### Check",
        "",
        f"- Command: {_code(' '.join(check.command))}",
        f"- Baseline exit: {_code(str(proof.baseline.returncode))}",
        f"- After exit: {_code(str(proof.after.returncode))}",
    ]
    return "\n".join(lines)


def _files_section(files: Sequence[str]) -> str:
    lines = ["### Files", ""]
    lines.extend(f"- {_code(path)}" for path in files)
    if not files:
        lines.append("None.")
    return "\n".join(lines)


def _skipped_section(skipped: Sequence[Skipped]) -> str:
    lines = ["### Skipped sites", ""]
    if skipped:
        lines.extend(
            f"- {_code(f'{entry.site.path}:{entry.site.line}')} "
            f"{_code(entry.site.symbol)}: {entry.reason.value}"
            for entry in skipped
        )
    else:
        lines.append("None.")
    return "\n".join(lines)


def _what_this_proves(proof: ProofResult) -> str:
    return f"### What this proves\n\n{_PROOF_PARAGRAPHS[proof.level]}"


def _body(
    proposal: Proposal,
    proof: ProofResult,
    unanalyzed: Sequence[Unanalyzed],
) -> str:
    sections = [
        f"## Tenon proof: {proof.level.value}",
        _level_sentence(proof),
        _change_section(proposal.change),
        _check_section(proof),
        _files_section(proposal.files),
        _skipped_section(proposal.skipped),
        _what_this_proves(proof),
        FOOTER,
    ]
    return "\n\n".join(sections) + "\n"


def render_pr(
    proposal: Proposal,
    proof: ProofResult,
    *,
    unanalyzed: Sequence[Unanalyzed] = (),
) -> PrDraft:
    """Render the one deterministic draft a PR write would ship."""
    summary = _summary(proposal.change)
    return PrDraft(
        title=_title(proof, summary),
        body=_body(proposal, proof, unanalyzed),
        branch=_branch(proposal.change, proposal.diff),
        commit_message=_commit_message(summary),
    )

