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
    receivers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _CRATE.fullmatch(self.sdk_package):
            raise ValueError(
                f"sdk_package must be one Rust crate identifier: {self.sdk_package!r}"
            )
        # Spec AC1: every receiver key and value is one non-empty token.
        for key, value in self.receivers.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or key.split() != [key]
                or value.split() != [value]
            ):
                raise ValueError(
                    f"receivers must map a KEY to a VALUE, both non-empty "
                    f"tokens: {key!r}: {value!r}"
                )
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "receivers", MappingProxyType(dict(self.receivers)))
