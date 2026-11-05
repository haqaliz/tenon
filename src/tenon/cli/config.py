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
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise ValueError(f"{path}: {error}") from error

    section = data.get("locate")
    if not isinstance(section, dict):
        raise ValueError(f"{path}: missing the [locate] table")
    if "sdk_package" not in section:
        raise ValueError(f"{path}: [locate] is missing sdk_package")
    operations = section.get("operations", {})
    if not isinstance(operations, dict):
        raise ValueError(f"{path}: [locate] operations must be a table")
    fields = section.get("fields", {})
    if not isinstance(fields, dict):
        raise ValueError(f"{path}: [locate] fields must be a table")

    tenon = data.get("tenon", {})
    if not isinstance(tenon, dict):
        raise ValueError(f"{path}: [tenon] must be a table")
    command = tenon.get("command", [])
    if not isinstance(command, list) or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ValueError(f"{path}: [tenon] command must be an array of non-empty strings")
    require = tenon.get("require", ProofLevel.TESTS_PASSED)
    if require not in (ProofLevel.TESTS_PASSED, ProofLevel.UNVERIFIED):
        raise ValueError(
            f"{path}: [tenon] require {require!r} is not supported until T7; "
            "use TESTS_PASSED or UNVERIFIED"
        )
    breaking_only = tenon.get("breaking_only", False)
    if not isinstance(breaking_only, bool):
        raise ValueError(f"{path}: [tenon] breaking_only must be a bool")

    return CliConfig(
        locate=LocateConfig(
            sdk_package=section["sdk_package"],
            operations=operations,
            fields=fields,
        ),
        command=tuple(command),
        require=ProofLevel(require),
        breaking_only=breaking_only,
    )
