"""Compare two resolved OpenAPI documents and emit typed changes."""

from .record import Change, ChangeKind, DiffResult, Location

# Fixed order so records never depend on dict insertion order in the input.
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def _escape(token: object) -> str:
    """RFC 6901 escaping: ``~`` before ``/``, or ``~1`` would be escaped twice."""
    return str(token).replace("~", "~0").replace("/", "~1")


def diff(old: dict, new: dict) -> DiffResult:
    """Every change between two resolved documents, canonically ordered."""
    changes: list[Change] = []
    _diff_paths(old.get("paths") or {}, new.get("paths") or {}, changes)
    return DiffResult(changes)


def _methods(path_item: object) -> tuple[str, ...]:
    if not isinstance(path_item, dict):
        return ()
    return tuple(method for method in HTTP_METHODS if isinstance(path_item.get(method), dict))


def _endpoint(kind: ChangeKind, path: str, method: str, pointer: str) -> Change:
    removed = kind is ChangeKind.ENDPOINT_REMOVED
    return Change(
        kind=kind,
        location=Location(pointer=pointer, method=method, path=path),
        before=path if removed else None,
        after=None if removed else path,
        breaking=removed,
    )


def _diff_paths(old_paths: dict, new_paths: dict, changes: list[Change]) -> None:
    old_paths = old_paths if isinstance(old_paths, dict) else {}
    new_paths = new_paths if isinstance(new_paths, dict) else {}

    for path in sorted(old_paths):
        old_methods = _methods(old_paths[path])
        new_item = new_paths.get(path)
        if not isinstance(new_item, dict):
            for method in old_methods:
                changes.append(
                    _endpoint(ChangeKind.ENDPOINT_REMOVED, path, method, "#/paths")
                )
            continue

        pointer = f"#/paths/{_escape(path)}"
        new_methods = _methods(new_item)
        for method in old_methods:
            if method not in new_methods:
                changes.append(
                    _endpoint(ChangeKind.ENDPOINT_REMOVED, path, method, pointer)
                )
        for method in new_methods:
            if method not in old_methods:
                changes.append(_endpoint(ChangeKind.ENDPOINT_ADDED, path, method, pointer))

    for path in sorted(new_paths):
        if path in old_paths:
            continue
        for method in _methods(new_paths[path]):
            changes.append(_endpoint(ChangeKind.ENDPOINT_ADDED, path, method, "#/paths"))
