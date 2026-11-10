"""The Rust locate config: a crate and the two shared mappings."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

# One crate identifier; a path belongs in the import.
_CRATE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class RustLocateConfig:
    """The in-memory API for a Rust repository."""

    sdk_package: str
    operations: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _CRATE.fullmatch(self.sdk_package):
            raise ValueError(
                f"sdk_package must be one Rust crate identifier: {self.sdk_package!r}"
            )
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
