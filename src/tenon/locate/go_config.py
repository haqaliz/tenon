"""The Go locate config: an import root, an optional package name and mappings."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

_GO_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class GoLocateConfig:
    """The in-memory API for a Go repository."""

    sdk_package: str
    package_name: str | None = None
    operations: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)
    receivers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        root = self.sdk_package
        if (
            not root
            or any(character.isspace() for character in root)
            or root.startswith("/")
            or root.endswith("/")
            or "::" in root
        ):
            raise ValueError(
                f"sdk_package must be a Go import root: {self.sdk_package!r}"
            )
        if self.package_name is not None and not _GO_IDENTIFIER.fullmatch(
            self.package_name
        ):
            raise ValueError(
                f"package_name must be a Go identifier: {self.package_name!r}"
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
