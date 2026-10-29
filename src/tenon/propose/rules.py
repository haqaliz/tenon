"""The deterministic rename rule: certain field-rename sites become candidate edits.

Pure by construction: the rule never reads ``root`` and never touches a file;
verification (``STALE_SITE``) and the diff belong to assembly.
"""

from pathlib import Path

from tenon.detect import Change, ChangeKind
from tenon.locate import LocateResult

from .result import Edit


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


class RuleProposer:
    """Rename a field at the sites the locator called certain."""

    def propose(
        self, change: Change, located: LocateResult, root: str | Path
    ) -> tuple[Edit, ...]:
        if change.kind is not ChangeKind.RENAMED:
            return ()
        old, new = change.before, change.after
        if not isinstance(old, str) or not isinstance(new, str):
            return ()
        if not old or not new or old == new:
            return ()
        if _is_endpoint_rename(change):
            return ()
        return tuple(
            Edit(
                path=site.path,
                line=site.line,
                column=site.column,
                shape=site.shape,
                old=old,
                new=new,
            )
            for site in located.certain
            if site.symbol == old
        )
