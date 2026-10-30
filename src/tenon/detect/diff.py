"""Compare two resolved OpenAPI documents and emit typed changes."""

import json

from .record import (
    Change,
    ChangeKind,
    DiffResult,
    Location,
    Unanalyzed,
    UnanalyzedReason,
)
from .rename import infer_renames

# Fixed order so records never depend on dict insertion order in the input.
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def _escape(token: object) -> str:
    """RFC 6901 escaping: ``~`` before ``/``, or ``~1`` would be escaped twice."""
    return str(token).replace("~", "~0").replace("/", "~1")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def diff(old: dict, new: dict) -> DiffResult:
    """Every change between two resolved documents, canonically ordered."""
    changes: list[Change] = []
    context = _SchemaContext(old, new)
    _diff_paths(old.get("paths") or {}, new.get("paths") or {}, context, changes)
    _diff_components(old, new, context, changes)
    return DiffResult(infer_renames(changes), context.unanalyzed)


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


def _diff_paths(
    old_paths: dict, new_paths: dict, context: "_SchemaContext", changes: list[Change]
) -> None:
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
                    context,
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
    context: "_SchemaContext",
    changes: list[Change],
) -> None:
    _diff_parameters(
        old_item, old_operation, new_item, new_operation, path, method, context, changes
    )
    _diff_bodies(old_operation, new_operation, path, method, context, changes)


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
    # 3.1 writes nullability into the type array; 3.0 uses `nullable`. Neither is
    # part of the comparison basis, so a nullability-only change is not a change.
    types.discard("null")
    if not types:
        if isinstance(schema.get("properties"), dict):
            types.add("object")
        elif "items" in schema:
            types.add("array")
    fmt = schema.get("format")
    return frozenset(types), fmt if isinstance(fmt, str) else None


def _render_type(
    name: str | None, where: str | None, basis: tuple[frozenset[str], str | None]
) -> dict:
    types, fmt = basis
    ordered = sorted(types)
    rendered: object = ordered[0] if len(ordered) == 1 else (ordered or None)
    payload: dict = {"type": rendered, "format": fmt}
    if name is not None:
        payload["name"] = name
    if where is not None:
        payload["in"] = where
    return payload


def _enum_payload(name: str | None, values: list) -> dict:
    payload: dict = {"enum": sorted(values, key=_canonical)}
    if name is not None:
        payload["name"] = name
    return payload


def _required(schema: dict) -> set[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return set()
    return {value for value in required if isinstance(value, str)}


# Keywords a plain allOf merge can carry; anything else is a composition we cannot
# merge faithfully, so it is skipped rather than guessed at.
_PLAIN_SCHEMA_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "nullable",
        "description",
        "title",
        "example",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "xml",
        "externalDocs",
    }
)


def _flatten(
    schema: object,
    pointer: str,
    context: "_SchemaContext",
    active: set[int] | None = None,
) -> dict | None:
    """Return the schema with any plain ``allOf`` merged into one object schema.

    ``oneOf``, ``anyOf``, ``discriminator`` and any non-plain ``allOf`` record
    ``UNSUPPORTED_COMPOSITION`` at ``pointer`` and return ``None``; the caller skips the
    pair. A ``$ref`` marker records ``CYCLIC_REF`` and returns ``None``.
    """
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        context.record(pointer, UnanalyzedReason.CYCLIC_REF)
        return None
    for keyword in ("oneOf", "anyOf", "discriminator"):
        if keyword in schema:
            context.record(pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
            return None
    if "allOf" not in schema:
        return schema

    if active is None:
        active = set()
    if id(schema) in active:
        context.record(pointer, UnanalyzedReason.CYCLIC_REF)
        return None
    active.add(id(schema))
    try:
        members = schema["allOf"]
        if (
            not isinstance(members, list)
            or not members
            or not all(isinstance(member, dict) for member in members)
        ):
            context.record(pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
            return None

        container = {key: value for key, value in schema.items() if key != "allOf"}
        extra = set(container) - _PLAIN_SCHEMA_KEYS
        if extra:
            context.record(pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
            return None
        if container.get("type") not in (None, "object"):
            context.record(pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
            return None
        properties = container.get("properties") or {}
        if not isinstance(properties, dict):
            context.record(pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
            return None
        properties = dict(properties)
        required = _required(container)
        nullable = container.get("nullable") is True

        for index, member in enumerate(members):
            member_pointer = f"{pointer}/allOf/{index}"
            flattened = _flatten(member, member_pointer, context, active)
            if flattened is None:
                return None
            extra = set(flattened) - _PLAIN_SCHEMA_KEYS
            if extra:
                context.record(member_pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
                return None
            if flattened.get("type") not in (None, "object"):
                context.record(member_pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
                return None
            member_properties = flattened.get("properties") or {}
            if not isinstance(member_properties, dict):
                context.record(member_pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION)
                return None
            for prop, prop_schema in member_properties.items():
                if prop in properties and properties[prop] != prop_schema:
                    context.record(
                        member_pointer, UnanalyzedReason.UNSUPPORTED_COMPOSITION
                    )
                    return None
                properties[prop] = prop_schema
            required |= _required(flattened)
            nullable = nullable or flattened.get("nullable") is True

        merged = {
            key: value
            for key, value in container.items()
            if key not in ("properties", "required", "nullable", "type")
        }
        merged["type"] = "object"
        merged["properties"] = properties
        if required:
            merged["required"] = sorted(required)
        if nullable:
            merged["nullable"] = True
        return merged
    finally:
        active.discard(id(schema))


def _diff_parameters(
    old_item: dict,
    old_operation: dict,
    new_item: dict,
    new_operation: dict,
    path: str,
    method: str,
    context: "_SchemaContext",
    changes: list[Change],
) -> None:
    old_params = _effective_parameters(old_item, old_operation, path, method)
    new_params = _effective_parameters(new_item, new_operation, path, method)
    for key in sorted(set(old_params) | set(new_params)):
        name, where = key
        if key not in new_params:
            old_param, pointer, _ = old_params[key]
            changes.append(
                Change(
                    kind=ChangeKind.PARAMETER_REMOVED,
                    location=Location(pointer=pointer, method=method, path=path),
                    before=_render_type(
                        name, where, _type_basis(old_param.get("schema"))
                    ),
                    breaking=True,
                )
            )
            continue

        param, pointer, new_index = new_params[key]
        location = Location(pointer=pointer, method=method, path=path)
        if key not in old_params:
            if param.get("required") is True:
                changes.append(
                    Change(
                        kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
                        location=location,
                        after=_render_type(
                            name, where, _type_basis(param.get("schema"))
                        ),
                        breaking=True,
                    )
                )
            continue

        old_param, old_pointer, old_index = old_params[key]
        if param.get("required") is True and old_param.get("required") is not True:
            changes.append(
                Change(
                    kind=ChangeKind.PARAMETER_REQUIRED_ADDED,
                    location=location,
                    before=_render_type(
                        name, where, _type_basis(old_param.get("schema"))
                    ),
                    after=_render_type(
                        name, where, _type_basis(param.get("schema"))
                    ),
                    breaking=True,
                )
            )

        if context.is_component_copy(old_param.get("schema"), param.get("schema")):
            continue

        old_schema = _flatten(
            old_param.get("schema"), f"{old_pointer}/{old_index}/schema", context
        )
        new_schema = _flatten(
            param.get("schema"), f"{pointer}/{new_index}/schema", context
        )
        if old_schema is None or new_schema is None:
            continue
        old_basis = _type_basis(old_schema)
        new_basis = _type_basis(new_schema)
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


def _record_location(location: Location, pointer: str) -> Location:
    return Location(pointer=pointer, method=location.method, path=location.path)


def _diff_bodies(
    old_operation: dict,
    new_operation: dict,
    path: str,
    method: str,
    context: "_SchemaContext",
    changes: list[Change],
) -> None:
    base = f"#/paths/{_escape(path)}/{method}"
    location = Location(pointer=base, method=method, path=path)
    _diff_content(
        old_operation.get("requestBody"),
        new_operation.get("requestBody"),
        f"{base}/requestBody/content",
        location,
        context,
        changes,
    )

    old_responses = old_operation.get("responses")
    new_responses = new_operation.get("responses")
    if not isinstance(old_responses, dict) or not isinstance(new_responses, dict):
        return
    for status in sorted(
        set(old_responses) & set(new_responses),
        key=lambda key: (str(key), type(key).__name__),
    ):
        if not isinstance(old_responses[status], dict) or not isinstance(
            new_responses[status], dict
        ):
            continue
        _diff_content(
            old_responses[status],
            new_responses[status],
            f"{base}/responses/{_escape(status)}/content",
            location,
            context,
            changes,
        )


def _diff_content(
    old_holder: object,
    new_holder: object,
    pointer: str,
    location: Location,
    context: "_SchemaContext",
    changes: list[Change],
) -> None:
    if not isinstance(old_holder, dict) or not isinstance(new_holder, dict):
        return
    old_content = old_holder.get("content")
    new_content = new_holder.get("content")
    if not isinstance(old_content, dict) or not isinstance(new_content, dict):
        return
    for media in sorted(set(old_content) & set(new_content)):
        old_media = old_content[media]
        new_media = new_content[media]
        if not isinstance(old_media, dict) or not isinstance(new_media, dict):
            continue
        old_schema = old_media.get("schema")
        new_schema = new_media.get("schema")
        if isinstance(old_schema, dict) and isinstance(new_schema, dict):
            _diff_schema(
                old_schema,
                new_schema,
                f"{pointer}/{_escape(media)}/schema",
                location,
                context,
                changes,
            )


def _diff_schema(
    old: object,
    new: object,
    pointer: str,
    location: Location,
    context: "_SchemaContext",
    changes: list[Change],
    *,
    name: str | None = None,
    enclosing: str | None = None,
    root: bool = False,
) -> None:
    pair = (id(old), id(new))
    if pair in context.active:
        context.record(pointer, UnanalyzedReason.CYCLIC_REF)
        return
    context.active.add(pair)
    try:
        _diff_schema_node(
            old,
            new,
            pointer,
            location,
            context,
            changes,
            name=name,
            enclosing=enclosing,
            root=root,
        )
    finally:
        context.active.discard(pair)


def _diff_schema_node(
    old: object,
    new: object,
    pointer: str,
    location: Location,
    context: "_SchemaContext",
    changes: list[Change],
    *,
    name: str | None,
    enclosing: str | None,
    root: bool,
) -> None:
    old_schema = old if isinstance(old, dict) else {}
    new_schema = new if isinstance(new, dict) else {}

    if not root and context.is_component_copy(old_schema, new_schema):
        return

    old_schema = _flatten(old_schema, pointer, context)
    new_schema = _flatten(new_schema, pointer, context)
    if old_schema is None or new_schema is None:
        return

    record_pointer = enclosing or pointer
    old_basis = _type_basis(old_schema)
    new_basis = _type_basis(new_schema)
    if old_basis != new_basis:
        changes.append(
            Change(
                kind=ChangeKind.PROPERTY_TYPE_CHANGED,
                location=_record_location(location, record_pointer),
                before=_render_type(name, None, old_basis),
                after=_render_type(name, None, new_basis),
                breaking=True,
            )
        )

    old_enum = old_schema.get("enum")
    new_enum = new_schema.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        old_values = {_canonical(value) for value in old_enum}
        new_values = {_canonical(value) for value in new_enum}
        if new_values < old_values:
            changes.append(
                Change(
                    kind=ChangeKind.ENUM_NARROWED,
                    location=_record_location(location, record_pointer),
                    before=_enum_payload(name, old_enum),
                    after=_enum_payload(name, new_enum),
                    breaking=True,
                )
            )

    old_properties = old_schema.get("properties")
    new_properties = new_schema.get("properties")
    old_properties = old_properties if isinstance(old_properties, dict) else {}
    new_properties = new_properties if isinstance(new_properties, dict) else {}
    properties_pointer = f"{pointer}/properties"
    old_required = _required(old_schema)
    new_required = _required(new_schema)

    for prop in sorted(old_properties):
        if prop not in new_properties:
            changes.append(
                Change(
                    kind=ChangeKind.PROPERTY_REMOVED,
                    location=_record_location(location, properties_pointer),
                    before=_render_type(
                        prop, None, _type_basis(old_properties[prop])
                    ),
                    breaking=True,
                )
            )

    for prop in sorted(new_properties):
        if prop not in old_properties:
            if prop in new_required:
                changes.append(
                    Change(
                        kind=ChangeKind.PROPERTY_REQUIRED_ADDED,
                        location=_record_location(location, properties_pointer),
                        after=_render_type(
                            prop, None, _type_basis(new_properties[prop])
                        ),
                        breaking=True,
                    )
                )
            else:
                changes.append(
                    Change(
                        kind=ChangeKind.PROPERTY_ADDED,
                        location=_record_location(location, properties_pointer),
                        after=_render_type(
                            prop, None, _type_basis(new_properties[prop])
                        ),
                    )
                )
            continue

        if prop in new_required and prop not in old_required:
            changes.append(
                Change(
                    kind=ChangeKind.PROPERTY_REQUIRED_ADDED,
                    location=_record_location(location, properties_pointer),
                    before=_render_type(
                        prop, None, _type_basis(old_properties[prop])
                    ),
                    after=_render_type(
                        prop, None, _type_basis(new_properties[prop])
                    ),
                    breaking=True,
                )
            )
        _diff_schema(
            old_properties[prop],
            new_properties[prop],
            f"{properties_pointer}/{_escape(prop)}",
            location,
            context,
            changes,
            name=prop,
            enclosing=properties_pointer,
        )

    old_items = old_schema.get("items")
    new_items = new_schema.get("items")
    if isinstance(old_items, dict) and isinstance(new_items, dict):
        _diff_schema(
            old_items,
            new_items,
            f"{pointer}/items",
            location,
            context,
            changes,
            enclosing=pointer,
        )


def _schemas_of(document: dict) -> dict:
    components = document.get("components")
    if not isinstance(components, dict):
        return {}
    schemas = components.get("schemas")
    return schemas if isinstance(schemas, dict) else {}


class _SchemaContext:
    """Per-diff state: component identities and the recursion guard."""

    def __init__(self, old_document: dict, new_document: dict) -> None:
        self.old_ids = {id(schema) for schema in _schemas_of(old_document).values()}
        self.new_ids = {id(schema) for schema in _schemas_of(new_document).values()}
        self.active: set[tuple[int, int]] = set()
        self.unanalyzed: list[Unanalyzed] = []

    def record(self, pointer: str, reason: UnanalyzedReason) -> None:
        """Remember a skipped subtree once per ``(pointer, reason)``."""
        entry = Unanalyzed(pointer, reason)
        if entry not in self.unanalyzed:
            self.unanalyzed.append(entry)

    def is_component_copy(self, old: object, new: object) -> bool:
        """True when both sides are the same resolved component objects.

        Such a subtree is reported once, at ``components``, not once per use.
        """
        return id(old) in self.old_ids and id(new) in self.new_ids


def _diff_components(
    old_document: dict,
    new_document: dict,
    context: "_SchemaContext",
    changes: list[Change],
) -> None:
    old_schemas = _schemas_of(old_document)
    new_schemas = _schemas_of(new_document)
    pointer = "#/components/schemas"
    for name in sorted(old_schemas):
        if name not in new_schemas:
            changes.append(
                Change(
                    kind=ChangeKind.SCHEMA_REMOVED,
                    location=Location(pointer=pointer),
                    before=name,
                    breaking=True,
                )
            )
    for name in sorted(new_schemas):
        if name not in old_schemas:
            changes.append(
                Change(
                    kind=ChangeKind.SCHEMA_ADDED,
                    location=Location(pointer=pointer),
                    after=name,
                )
            )
        else:
            _diff_schema(
                old_schemas[name],
                new_schemas[name],
                f"{pointer}/{_escape(name)}",
                Location(pointer=pointer),
                context,
                changes,
                root=True,
            )
