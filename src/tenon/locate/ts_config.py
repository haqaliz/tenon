"""The TypeScript locate config: an npm package and the two shared mappings."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

# A bare package or an ``@scope/package``; a subpath belongs in the import.
_NPM_NAME = re.compile(r"(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class TsLocateConfig:
    """The in-memory API for a TypeScript repository."""

    sdk_package: str
    operations: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NPM_NAME.fullmatch(self.sdk_package):
            raise ValueError(
                f"sdk_package must be an npm package name: {self.sdk_package!r}"
            )
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
