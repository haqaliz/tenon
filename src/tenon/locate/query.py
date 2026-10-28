"""Translate a T1 change record into the locate query: pure, no filesystem.

A change speaks HTTP; the scanner speaks Python names. ``derive`` is the single
translation point, so it names what it cannot map instead of guessing.
"""

from dataclasses import dataclass
from typing import Literal

from tenon.detect import Change, ChangeKind

from .result import LocateConfig, LocateReason

Scope = Literal["operation", "component"]
FieldPresence = Literal["must_exist", "must_be_added", "absent"]
Origin = Literal["mapping", "inferred", "none"]

_UNSUPPORTED_KINDS = frozenset(
    {ChangeKind.ENUM_NARROWED, ChangeKind.SCHEMA_REMOVED, ChangeKind.SCHEMA_ADDED}
)
_ENDPOINT_KINDS = frozenset({ChangeKind.ENDPOINT_REMOVED, ChangeKind.ENDPOINT_ADDED})
_MUST_BE_ADDED_KINDS = frozenset(
    {
        ChangeKind.PROPERTY_ADDED,
        ChangeKind.PROPERTY_REQUIRED_ADDED,
        ChangeKind.PARAMETER_REQUIRED_ADDED,
    }
)


@dataclass(frozen=True, slots=True)
class Query:
    """What a change asks the scanner to find. Candidates are ordered, never a set."""

    scope: Scope
    kind: ChangeKind
    method: str | None
    path: str | None
    operation_candidates: tuple[str, ...]
    field_name: str | None
    change_field: str | None
    field_presence: FieldPresence
    origin: Origin
    reason: LocateReason | None = None


def derive(change: Change, config: LocateConfig) -> Query:
    """Derive the locate query for one change; unsupported shapes get a named reason."""
    location = change.location
    scope: Scope = (
        "operation" if location.method and location.path else "component"
    )

    if change.kind in _UNSUPPORTED_KINDS:
        return _unsupported(change, scope)

    if change.kind in _ENDPOINT_KINDS:
        field_name = None
        change_field = None
        presence: FieldPresence = "absent"
        origin: Origin = "none"
    elif change.kind is ChangeKind.RENAMED:
        old = change.before
        if not isinstance(old, str) or not old:
            return _unsupported(change, scope)
        if location.pointer == "#/paths":
            # An endpoint rename: the old path is reporting data, not a field.
            field_name = None
            change_field = old
            presence = "absent"
            origin = "none"
        else:
            field_name = old
            change_field = old
            presence = "must_exist"
            origin = "inferred"
    else:
        spec_name = _payload_name(change)
        if spec_name is None:
            return _unsupported(change, scope)
        field_name = spec_name
        change_field = spec_name
        presence = (
            "must_be_added"
            if change.kind in _MUST_BE_ADDED_KINDS
            else "must_exist"
        )
        origin = "inferred"

    return Query(
        scope=scope,
        kind=change.kind,
        method=location.method,
        path=location.path,
        operation_candidates=(),
        field_name=field_name,
        change_field=change_field,
        field_presence=presence,
        origin=origin,
    )


def _name_of(payload: object) -> str | None:
    if isinstance(payload, dict):
        name = payload.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _payload_name(change: Change) -> str | None:
    """The spec-side name T1 rendered, or None when the payload is unusable."""
    if change.kind is ChangeKind.PROPERTY_ADDED:
        return _name_of(change.after)
    if change.kind in _MUST_BE_ADDED_KINDS:
        # A required-added item carries the name on whichever side T1 rendered.
        return _name_of(change.before) or _name_of(change.after)
    return _name_of(change.before)


def _unsupported(change: Change, scope: Scope) -> Query:
    return Query(
        scope=scope,
        kind=change.kind,
        method=change.location.method,
        path=change.location.path,
        operation_candidates=(),
        field_name=None,
        change_field=None,
        field_presence="absent",
        origin="none",
        reason=LocateReason.UNSUPPORTED_CHANGE_KIND,
    )
