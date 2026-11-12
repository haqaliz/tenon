"""The C# locate wrapper: shared query, C# scanner, shared resolver."""

from pathlib import Path

from tenon.detect import Change

from .csharp_config import CSharpLocateConfig
from .csharp_scan import scan_csharp
from .query import derive
from .resolve import resolve
from .result import LocateResult


def locate_csharp(
    change: Change, root: str | Path, config: CSharpLocateConfig
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
        scan_csharp(root, config.sdk_package, config.receivers),
        config,
    )
