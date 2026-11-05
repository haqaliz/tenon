"""Resolve ``tenon.toml`` and CLI flags into one CLI config. No pipeline calls."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from tenon.locate import LocateConfig
from tenon.prove import ProofLevel


@dataclass(frozen=True, slots=True)
class CliConfig:
    """Everything one CLI run needs before it starts."""

    locate: LocateConfig
    command: tuple[str, ...] = ()
    require: ProofLevel = ProofLevel.TESTS_PASSED
    breaking_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        if not isinstance(self.require, ProofLevel):
            object.__setattr__(self, "require", ProofLevel(self.require))


def load_cli_config(path: str | Path) -> CliConfig:
    """Read ``[locate]`` and ``[tenon]`` from one TOML file."""
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    section = data["locate"]
    tenon = data.get("tenon", {})
    return CliConfig(
        locate=LocateConfig(
            sdk_package=section["sdk_package"],
            operations=section.get("operations", {}),
            fields=section.get("fields", {}),
        ),
        command=tuple(tenon.get("command", ())),
        require=ProofLevel(tenon.get("require", ProofLevel.TESTS_PASSED)),
        breaking_only=tenon.get("breaking_only", False),
    )
