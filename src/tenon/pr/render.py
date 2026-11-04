"""Render a deterministic PR draft from a proposal and its proof."""

import hashlib
import json
import re
from typing import Any

from tenon.detect import Change
from tenon.prove import ProofResult

_SCALARS = (str, int, float, bool, type(None))
_NON_SLUG = re.compile(r"[^a-z0-9]+")


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

