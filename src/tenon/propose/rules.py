"""The deterministic rename rule: certain field-rename sites become candidate edits.

Pure by construction: the rule never reads ``root`` and never touches a file;
verification (``STALE_SITE``) and the diff belong to assembly.
"""

from pathlib import Path

from tenon.detect import Change, ChangeKind
from tenon.locate import LocateResult, SiteShape

from .result import Edit

_EDITABLE_SHAPES = frozenset(
    {SiteShape.KEYWORD, SiteShape.DICT_KEY, SiteShape.ATTRIBUTE}
)


def _is_endpoint_rename(change: Change) -> bool:
    """T1's endpoint shape: a method and path, with paths on both sides.

    A request-body property rename also carries a method and path, so the
    leading ``/`` is what separates the two, mirroring T2's own discrimination.
    """
    location = change.location
    old, new = change.before, change.after
    return bool(
        location.method
        and location.path
        and isinstance(old, str)
        and isinstance(new, str)
        and old.startswith("/")
        and new.startswith("/")
    )


def has_rule(change: Change) -> bool:
    """Whether the mechanical rename rule applies to this change."""
    if change.kind is not ChangeKind.RENAMED:
        return False
    old, new = change.before, change.after
    if not isinstance(old, str) or not isinstance(new, str):
        return False
    if not old or not new or old == new:
        return False
    return not _is_endpoint_rename(change)


class RuleProposer:
    """Rename a field at the sites the locator called certain."""

    def propose(
        self, change: Change, located: LocateResult, root: str | Path
    ) -> tuple[Edit, ...]:
        if not has_rule(change):
            return ()
        old, new = change.before, change.after
        edits: list[Edit] = []
        seen: set[tuple[str, int, int, str, str]] = set()
        for site in located.certain:
            if site.shape not in _EDITABLE_SHAPES or site.symbol != old:
                continue
            edit = Edit(
                path=site.path,
                line=site.line,
                column=site.column,
                shape=site.shape,
                old=old,
                new=new,
            )
            key = (edit.path, edit.line, edit.column, edit.shape.value, edit.old)
            if key in seen:
                continue
            seen.add(key)
            edits.append(edit)
        return tuple(edits)
