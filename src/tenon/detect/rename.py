"""Pair removed and added records into inferred renames, or leave them alone."""

import json
import re

from .record import Change, ChangeKind

_PATH_PARAM = re.compile(r"\{[^/{}]+\}")


def _shape(*parts: object) -> str:
    return json.dumps(parts, sort_keys=True)


def _normalise_template(path: str) -> tuple[bool, ...]:
    """Param/no-param segment shape: ``{id}`` and ``{user_id}`` compare alike."""
    return tuple(_PATH_PARAM.search(segment) is not None for segment in path.split("/"))


def _payload_basis(payload: dict, *, with_in: bool) -> tuple[object, str]:
    head = [payload.get("in")] if with_in else []
    return payload.get("name"), _shape(*head, payload.get("type"), payload.get("format"))


def _removed_candidate(change: Change) -> tuple[str, object, str] | None:
    if change.kind is ChangeKind.PROPERTY_REMOVED:
        return ("property", *_payload_basis(change.before, with_in=False))
    if change.kind is ChangeKind.PARAMETER_REMOVED:
        return ("parameter", *_payload_basis(change.before, with_in=True))
    if change.kind is ChangeKind.ENDPOINT_REMOVED:
        return ("endpoint", change.before, _endpoint_shape(change, change.before))
    return None


def _added_candidate(change: Change) -> tuple[str, object, str] | None:
    # A before is present when an existing item merely became required: not a rename.
    if change.kind in (ChangeKind.PROPERTY_ADDED, ChangeKind.PROPERTY_REQUIRED_ADDED):
        if change.before is not None:
            return None
        return ("property", *_payload_basis(change.after, with_in=False))
    if change.kind is ChangeKind.PARAMETER_REQUIRED_ADDED:
        if change.before is not None:
            return None
        return ("parameter", *_payload_basis(change.after, with_in=True))
    if change.kind is ChangeKind.ENDPOINT_ADDED:
        return ("endpoint", change.after, _endpoint_shape(change, change.after))
    return None


def _endpoint_shape(change: Change, path: str) -> str:
    return _shape(change.location.method, _normalise_template(path))


def infer_renames(changes: list[Change]) -> list[Change]:
    """Replace removed/added pairs that are unambiguous in both directions.

    A pair is accepted only when exactly one removed and exactly one added record
    share the same parent pointer, family and shape. Everything else is left as a
    removal plus an addition, because a wrong rename is a product-level lie.
    """
    removed: dict[tuple, list[tuple[int, object]]] = {}
    added: dict[tuple, list[tuple[int, object]]] = {}
    for index, change in enumerate(changes):
        candidate = _removed_candidate(change)
        if candidate is not None:
            family, name, shape = candidate
            key = (change.location.pointer, change.location.method, family, shape)
            removed.setdefault(key, []).append((index, name))
        candidate = _added_candidate(change)
        if candidate is not None:
            family, name, shape = candidate
            key = (change.location.pointer, change.location.method, family, shape)
            added.setdefault(key, []).append((index, name))

    # sorted(..., key=repr) is deterministic even where method is None.
    paired: dict[int, tuple[object, int, object]] = {}
    for key in sorted(removed, key=repr):
        removeds = removed[key]
        addeds = added.get(key, [])
        if len(removeds) == 1 and len(addeds) == 1:
            removed_index, before = removeds[0]
            added_index, after = addeds[0]
            paired[removed_index] = (before, added_index, after)
    consumed = {added_index for _, added_index, _ in paired.values()}

    result: list[Change] = []
    for index, change in enumerate(changes):
        if index in paired:
            before, added_index, after = paired[index]
            # Location points at the new document: the item exists under the new name.
            result.append(
                Change(
                    kind=ChangeKind.RENAMED,
                    location=changes[added_index].location,
                    before=before,
                    after=after,
                    breaking=True,
                    confidence="inferred",
                )
            )
        elif index not in consumed:
            result.append(change)
    return result
