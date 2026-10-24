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
            else:
                _diff_operation(
                    old_paths[path],
                    old_paths[path][method],
                    new_item,
                    new_item[method],
                    path,
                    method,
                    changes,
                )

    for path in sorted(new_paths):
        if path in old_paths:
            continue
        for method in _methods(new_paths[path]):
            changes.append(_endpoint(ChangeKind.ENDPOINT_ADDED, path, method, "#/paths"))


def _diff_operation(
    old_item: dict,
    old_operation: dict,
    new_item: dict,
    new_operation: dict,
    path: str,
    method: str,
    changes: list[Change],
) -> None:
    _diff_parameters(old_item, old_operation, new_item, new_operation, path, method, changes)


def _effective_parameters(
    path_item: dict, operation: dict, path: str, method: str
) -> dict[tuple[str, str], tuple[dict, str, int]]:
    """Path-level parameters inherited by the operation; operation level wins."""
    base = f"#/paths/{_escape(path)}"
    merged: dict[tuple[str, str], tuple[dict, str, int]] = {}
    for params, pointer in (
        (path_item.get("parameters"), f"{base}/parameters"),
        (operation.get("parameters"), f"{base}/{method}/parameters"),
    ):
        if not isinstance(params, list):
            continue
        for index, param in enumerate(params):
            if not isinstance(param, dict):
                continue
            name, where = param.get("name"), param.get("in")
            if not isinstance(name, str) or not isinstance(where, str):
                continue
            merged[(name, where)] = (param, pointer, index)
    return merged


def _type_basis(schema: object) -> tuple[frozenset[str], str | None]:
    """The comparable type expression: explicit type plus inferred object/array."""
    if not isinstance(schema, dict):
        return frozenset(), None
    raw = schema.get("type")
    if isinstance(raw, str):
        types = {raw}
    elif isinstance(raw, list):
        types = {item for item in raw if isinstance(item, str)}
    else:
        types = set()
    if not types:
        if isinstance(schema.get("properties"), dict):
            types.add("object")
        elif "items" in schema:
            types.add("array")
    fmt = schema.get("format")
    return frozenset(types), fmt if isinstance(fmt, str) else None


def _render_type(name: str, where: str | None, basis: tuple[frozenset[str], str | None]):
    types, fmt = basis
    ordered = sorted(types)
    rendered: object = ordered[0] if len(ordered) == 1 else (ordered or None)
    payload = {"name": name, "type": rendered, "format": fmt}
    if where is not None:
        payload["in"] = where
    return payload


def _diff_parameters(
    old_item: dict,
    old_operation: dict,
    new_item: dict,
    new_operation: dict,
    path: str,
    method: str,
    changes: list[Change],
) -> None:
    old_params = _effective_parameters(old_item, old_operation, path, method)
    new_params = _effective_parameters(new_item, new_operation, path, method)
    for key in sorted(set(old_params) | set(new_params)):
        name, where = key
        if key not in new_params:
            _, pointer, _ = old_params[key]
            changes.append(
                Change(
                    kind=ChangeKind.PARAMETER_REMOVED,
                    location=Location(pointer=pointer, method=method, path=path),
                    before=name,
                    breaking=True,
                )
            )
            continue

        param, pointer, _ = new_params[key]
        location = Location(pointer=pointer, method=method, path=path)
        if key not in old_params:
            if param.get("required") is True:
                changes.append(
                    Change(
                        kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
                        location=location,
                        after=name,
                        breaking=True,
                    )
                )
            continue

        old_param = old_params[key][0]
        if param.get("required") is True and old_param.get("required") is not True:
            changes.append(
                Change(
                    kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
                    location=location,
                    before=name,
                    after=name,
                    breaking=True,
                )
            )

        old_basis = _type_basis(old_param.get("schema"))
        new_basis = _type_basis(param.get("schema"))
        if old_basis != new_basis:
            changes.append(
                Change(
                    kind=ChangeKind.PARAMETER_TYPE_CHANGED,
                    location=location,
                    before=_render_type(name, where, old_basis),
                    after=_render_type(name, where, new_basis),
                    breaking=True,
                )
            )
