"""The Go locate wrapper: shared query, Go scanner, shared resolver."""

from pathlib import Path

from tenon.detect import Change

from .go_config import GoLocateConfig
from .go_scan import scan_go
from .query import derive
from .resolve import resolve
from .result import LocateResult


def locate_go(
    change: Change, root: str | Path, config: GoLocateConfig
) -> LocateResult:
    """Derive the query, scan the repository, and apply the certainty policy."""
    query = derive(change, config)
    if query.reason is not None:
        return LocateResult(
            change=change, certain=(), ambiguous=(), reason=query.reason
        )
    return resolve(
        change,
        query,
        scan_go(root, config.sdk_package, config.package_name, config.receivers),
        config,
    )
