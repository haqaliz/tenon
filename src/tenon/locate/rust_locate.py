"""The Rust locate wrapper: shared query, Rust scanner, shared resolver."""

from pathlib import Path

from tenon.detect import Change

from .query import derive
from .resolve import resolve
from .result import LocateResult
from .rust_config import RustLocateConfig
from .rust_scan import scan_rust


def locate_rust(
    change: Change, root: str | Path, config: RustLocateConfig
) -> LocateResult:
    """Derive the query, scan the repository, and apply the certainty policy."""
    query = derive(change, config)
    if query.reason is not None:
        return LocateResult(
            change=change, certain=(), ambiguous=(), reason=query.reason
        )
    return resolve(change, query, scan_rust(root, config.sdk_package), config)
