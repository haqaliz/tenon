"""The MCP locate config: the Python client package to scan."""

from dataclasses import dataclass

from .result import _PACKAGE


@dataclass(frozen=True, slots=True)
class McpLocateConfig:
    """The in-memory API for a Python MCP repository."""

    client_package: str = "mcp"

    def __post_init__(self) -> None:
        if not _PACKAGE.fullmatch(self.client_package):
            raise ValueError(
                "client_package must be a dotted Python identifier: "
                f"{self.client_package!r}"
            )
