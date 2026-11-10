from .config import load_config
from .csharp_config import CSharpLocateConfig
from .csharp_locate import locate_csharp
from .go_config import GoLocateConfig
from .go_locate import locate_go
from .mcp_config import McpLocateConfig
from .mcp_locate import locate_mcp
from .query import Query, derive
from .result import (
    AmbiguityReason,
    AmbiguousGroup,
    LocateConfig,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
)
from .resolve import locate
from .rust_config import RustLocateConfig
from .rust_locate import locate_rust
from .scan import Dynamic, Hit, ScanResult, scan
from .ts_config import TsLocateConfig
from .ts_locate import locate_ts

# Spec AC5: the one language -> locate config type table.
LOCATE_TYPES = {
    "python": LocateConfig,
    "ts": TsLocateConfig,
    "rust": RustLocateConfig,
    "go": GoLocateConfig,
    "csharp": CSharpLocateConfig,
}

__all__ = [
    "LOCATE_TYPES",
    "AmbiguityReason",
    "AmbiguousGroup",
    "CSharpLocateConfig",
    "Dynamic",
    "GoLocateConfig",
    "Hit",
    "LocateConfig",
    "LocateReason",
    "LocateResult",
    "McpLocateConfig",
    "Query",
    "RustLocateConfig",
    "ScanResult",
    "Site",
    "SiteShape",
    "TsLocateConfig",
    "derive",
    "load_config",
    "locate",
    "locate_csharp",
    "locate_go",
    "locate_mcp",
    "locate_rust",
    "locate_ts",
    "scan",
]
