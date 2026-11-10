"""The C# locate config: a namespace root and the shared mappings."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

_NAMESPACE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")


@dataclass(frozen=True, slots=True)
class CSharpLocateConfig:
    """The in-memory API for a C# repository."""

    sdk_package: str
    operations: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NAMESPACE.fullmatch(self.sdk_package):
            raise ValueError(
                f"sdk_package must be a dotted C# namespace: {self.sdk_package!r}"
            )
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
