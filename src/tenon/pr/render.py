"""Render a deterministic PR draft from a proposal and its proof."""

import json
from typing import Any

from tenon.detect import Change
from tenon.prove import ProofResult

_SCALARS = (str, int, float, bool, type(None))


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


def _summary(change: Change) -> str:
    summary = f"{change.kind.value} {_location(change)}"
    if change.before is not None or change.after is not None:
        summary += f": {_scalar(change.before)} -> {_scalar(change.after)}"
    return summary


def _title(proof: ProofResult, summary: str) -> str:
    return f"[{proof.level.value}] tenon: {summary}"


def _commit_message(summary: str) -> str:
    return f"tenon: {summary}"
