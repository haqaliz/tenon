"""Translate a T1 change record into the locate query: pure, no filesystem.

A change speaks HTTP; the scanner speaks Python names. ``derive`` is the single
translation point, so it names what it cannot map instead of guessing.
"""

import re
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

_VERSION_SEGMENT = re.compile(r"v\d+")
_PATH_PARAMETER = re.compile(r"\{[^/{}]+\}")

# The verb leaves the PRD settles on; order is part of the contract.
_VERB_LEAVES: dict[str, tuple[str, ...]] = {
    "get": ("get", "list", "retrieve"),
    "post": ("create",),
    "put": ("update",),
    "patch": ("update",),
    "delete": ("delete",),
}


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

    spec_name: str | None = None
    if change.kind in _ENDPOINT_KINDS:
        field_name = None
        change_field = None
        presence: FieldPresence = "absent"
    elif change.kind is ChangeKind.RENAMED:
        old = change.before
        if not isinstance(old, str) or not old:
            return _unsupported(change, scope)
        if scope == "operation" and _path_like(old) and _path_like(change.after):
            # An endpoint rename carries paths on both sides; a property rename
            # under an operation carries names even though method/path are set.
            field_name = None
            change_field = old
            presence = "absent"
        else:
            spec_name = old
            field_name = old
            change_field = old
            presence = "must_exist"
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

    mapped_operation = _mapped_operation(config, location.method, location.path)
    if mapped_operation is not None:
        operation_candidates = (mapped_operation,)
    else:
        operation_candidates = _infer_operations(location.method, location.path)
    mapped_field = _mapped_field(config, location.pointer, spec_name)
    if mapped_field is not None:
        field_name = mapped_field

    if mapped_operation is not None or mapped_field is not None:
        origin: Origin = "mapping"
    elif scope == "operation":
        origin = "inferred" if operation_candidates else "none"
    else:
        origin = "inferred" if field_name is not None else "none"

    return Query(
        scope=scope,
        kind=change.kind,
        method=location.method,
        path=location.path,
        operation_candidates=operation_candidates,
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


def _path_like(value: object) -> bool:
    return isinstance(value, str) and value.startswith("/")


def _mapped_operation(
    config: LocateConfig, method: str | None, path: str | None
) -> str | None:
    """An exact ``METHOD /path`` key, with the method compared case-insensitively."""
    if not method or not path:
        return None
    for key, target in config.operations.items():
        key_method, separator, key_path = key.partition(" ")
        if not separator or key_path != path:
            continue
        if key_method.upper() == method.upper() and target:
            return target
    return None


def _segments(path: str) -> tuple[str, ...]:
    """Resource segments: no leading ``v<N>`` and no ``{param}`` placeholders."""
    parts = [part for part in path.split("/") if part]
    if parts and _VERSION_SEGMENT.fullmatch(parts[0]):
        parts = parts[1:]
    return tuple(part for part in parts if not _PATH_PARAMETER.fullmatch(part))


def _infer_operations(method: str | None, path: str | None) -> tuple[str, ...]:
    """Ordered dotted candidates from the path and the verb; empty when unnamed."""
    if not method or not path:
        return ()
    leaves = _VERB_LEAVES.get(method.lower())
    if leaves is None:
        return ()
    base = _segments(path)
    if not base:
        return ()
    return tuple(".".join((*base, leaf)) for leaf in leaves)


def _schema_name(pointer: str) -> str | None:
    """The schema segment of a ``#/components/schemas/<name>`` pointer, else None."""
    segments = [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer.split("/")
    ]
    if segments[:3] != ["#", "components", "schemas"] or len(segments) < 4:
        return None
    return segments[3] or None


def _mapped_field(
    config: LocateConfig, pointer: str, spec_name: str | None
) -> str | None:
    """``Schema.field`` lookup; a mapping for another schema never applies."""
    if spec_name is None:
        return None
    schema = _schema_name(pointer)
    if schema is None:
        return None
    return config.fields.get(f"{schema}.{spec_name}") or None


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
