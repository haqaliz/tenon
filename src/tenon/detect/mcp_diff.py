"""Compare two normalized MCP ``tools/list`` documents and emit typed changes."""

from .diff import (
    _canonical,
    _enum_payload,
    _escape,
    _render_type,
    _required,
    _type_basis,
)
from .record import (
    Change,
    ChangeKind,
    DiffResult,
    Location,
    Unanalyzed,
    UnanalyzedReason,
)
from .rename import infer_renames


def diff_mcp(old: dict, new: dict) -> DiffResult:
    """Every change between two normalized MCP documents, canonically ordered."""
    old_tools = _tools_of(old)
    new_tools = _tools_of(new)
    changes: list[Change] = []
    context = _McpContext()
    for name in sorted(old_tools):
        if name not in new_tools:
            changes.append(_tool_change(ChangeKind.ENDPOINT_REMOVED, name))
    for name in sorted(new_tools):
        if name not in old_tools:
            changes.append(_tool_change(ChangeKind.ENDPOINT_ADDED, name))
            continue
        _diff_tool(old_tools[name], new_tools[name], name, changes)
    return DiffResult(infer_renames(changes), context.unanalyzed)


def _tools_of(document: dict) -> dict:
    tools = document.get("tools") if isinstance(document, dict) else None
    return tools if isinstance(tools, dict) else {}


def _tool_change(kind: ChangeKind, name: str) -> Change:
    removed = kind is ChangeKind.ENDPOINT_REMOVED
    return Change(
        kind=kind,
        location=Location(
            pointer=f"#/tools/{_escape(name)}", method="tool", path=name
        ),
        before=name if removed else None,
        after=None if removed else name,
        breaking=removed,
    )


def _diff_tool(
    old_tool: dict,
    new_tool: dict,
    name: str,
    changes: list[Change],
) -> None:
    base = f"#/tools/{_escape(name)}"
    location = Location(pointer=base, method="tool", path=name)
    for key, required_added in (("inputSchema", True), ("outputSchema", False)):
        old_schema = old_tool.get(key) if isinstance(old_tool, dict) else None
        new_schema = new_tool.get(key) if isinstance(new_tool, dict) else None
        if isinstance(old_schema, dict) and isinstance(new_schema, dict):
            _diff_schema(
                old_schema,
                new_schema,
                f"{base}/{key}",
                location,
                changes,
                required_added=required_added,
            )


def _diff_schema(
    old: object,
    new: object,
    pointer: str,
    location: Location,
    changes: list[Change],
    *,
    name: str | None = None,
    required_added: bool = True,
) -> None:
    old_schema = old if isinstance(old, dict) else {}
    new_schema = new if isinstance(new, dict) else {}
    _diff_schema_header(old_schema, new_schema, name, pointer, location, changes)
    _diff_additional_properties(old_schema, new_schema, pointer, location, changes)
    _diff_properties(
        old_schema,
        new_schema,
        f"{pointer}/properties",
        location,
        changes,
        required_added=required_added,
    )


def _diff_schema_header(
    old_schema: dict,
    new_schema: dict,
    name: str | None,
    pointer: str,
    location: Location,
    changes: list[Change],
) -> None:
    old_basis = _type_basis(old_schema)
    new_basis = _type_basis(new_schema)
    if old_basis != new_basis:
        changes.append(
            Change(
                kind=ChangeKind.PROPERTY_TYPE_CHANGED,
                location=_record_location(location, pointer),
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
                    location=_record_location(location, pointer),
                    before=_enum_payload(name, old_enum),
                    after=_enum_payload(name, new_enum),
                    breaking=True,
                )
            )


def _diff_additional_properties(
    old_schema: dict,
    new_schema: dict,
    pointer: str,
    location: Location,
    changes: list[Change],
) -> None:
    old_value = old_schema.get("additionalProperties")
    new_value = new_schema.get("additionalProperties")
    if _canonical(old_value) == _canonical(new_value):
        return
    changes.append(
        Change(
            kind=ChangeKind.ADDITIONAL_PROPERTIES_CHANGED,
            location=_record_location(location, pointer),
            before=old_value,
            after=new_value,
            breaking=new_value is False and old_value is not False,
        )
    )


def _diff_properties(
    old_schema: dict,
    new_schema: dict,
    pointer: str,
    location: Location,
    changes: list[Change],
    *,
    required_added: bool,
) -> None:
    old_properties = _properties_of(old_schema)
    new_properties = _properties_of(new_schema)
    old_required = _required(old_schema)
    new_required = _required(new_schema)

    for prop in sorted(old_properties):
        if prop not in new_properties:
            changes.append(
                Change(
                    kind=ChangeKind.PROPERTY_REMOVED,
                    location=_record_location(location, pointer),
                    before=_render_type(prop, None, _type_basis(old_properties[prop])),
                    breaking=True,
                )
            )

    for prop in sorted(new_properties):
        if prop not in old_properties:
            required = required_added and prop in new_required
            changes.append(
                Change(
                    kind=(
                        ChangeKind.PROPERTY_REQUIRED_ADDED
                        if required
                        else ChangeKind.PROPERTY_ADDED
                    ),
                    location=_record_location(location, pointer),
                    after=_render_type(prop, None, _type_basis(new_properties[prop])),
                    breaking=required,
                )
            )
            continue

        old_property = old_properties[prop]
        new_property = new_properties[prop]
        if required_added and prop in new_required and prop not in old_required:
            changes.append(
                Change(
                    kind=ChangeKind.PROPERTY_REQUIRED_ADDED,
                    location=_record_location(location, pointer),
                    before=_render_type(prop, None, _type_basis(old_property)),
                    after=_render_type(prop, None, _type_basis(new_property)),
                    breaking=True,
                )
            )
        _diff_property(old_property, new_property, prop, pointer, location, changes)


def _diff_property(
    old: object,
    new: object,
    name: str,
    pointer: str,
    location: Location,
    changes: list[Change],
) -> None:
    _diff_schema_header(
        old if isinstance(old, dict) else {},
        new if isinstance(new, dict) else {},
        name,
        pointer,
        location,
        changes,
    )


def _properties_of(schema: object) -> dict:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return properties if isinstance(properties, dict) else {}


def _record_location(location: Location, pointer: str) -> Location:
    return Location(pointer=pointer, method=location.method, path=location.path)


class _McpContext:
    """Per-diff state: the recursion guard and skipped subtrees."""

    def __init__(self) -> None:
        self.active: set[tuple[int, int]] = set()
        self.unanalyzed: list[Unanalyzed] = []

    def record(self, pointer: str, reason: UnanalyzedReason) -> None:
        entry = Unanalyzed(pointer, reason)
        if entry not in self.unanalyzed:
            self.unanalyzed.append(entry)
