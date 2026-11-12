"""The TypeScript locate wrapper: shared query, TS scanner, shared resolver."""

from pathlib import Path

from tenon.detect import Change

from .query import derive
from .resolve import resolve
from .result import LocateResult
from .ts_config import TsLocateConfig
from .ts_scan import scan_ts


def locate_ts(
    change: Change, root: str | Path, config: TsLocateConfig
) -> LocateResult:
    """Derive the query, scan the repository, and apply the certainty policy."""
    query = derive(change, config)
    if query.reason is not None:
        return LocateResult(
            change=change, certain=(), ambiguous=(), reason=query.reason
        )
    return resolve(
        change, query, scan_ts(root, config.sdk_package, config.receivers), config
    )
