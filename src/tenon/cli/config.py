"""Resolve ``tenon.toml`` and CLI flags into one CLI config. No pipeline calls."""

import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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


def a_level(value: object, source: str) -> ProofLevel:
    """One of the two proof levels shipped today; anything else is a T7 error."""
    if value not in (ProofLevel.TESTS_PASSED, ProofLevel.UNVERIFIED):
        raise ValueError(
            f"{source} must be TESTS_PASSED or UNVERIFIED until T7: {value!r}"
        )
    return ProofLevel(value)


def a_pairs(values: Sequence[str], flag: str) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` flags, splitting on the first '='."""
    pairs: dict[str, str] = {}
    for value in values:
        key, separator, mapped = value.partition("=")
        if not separator or not key or not mapped:
            raise ValueError(
                f"{flag} must be KEY=VALUE with a non-empty key and value: {value!r}"
            )
        pairs[key] = mapped
    return pairs


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
        require=a_level(tenon.get("require", ProofLevel.TESTS_PASSED), f"{path}: [tenon] require"),
        breaking_only=breaking_only,
    )


def overrides(
    config: CliConfig,
    *,
    sdk_package: str | None = None,
    operations: Sequence[str] = (),
    fields: Sequence[str] = (),
    command: str | None = None,
    require: str | None = None,
    breaking_only: bool | None = None,
) -> CliConfig:
    """Apply flags over the config; only supplied flags change anything."""
    locate = config.locate
    operations_over = a_pairs(operations, "--operation")
    fields_over = a_pairs(fields, "--field")
    if sdk_package is not None or operations_over or fields_over:
        locate = LocateConfig(
            sdk_package=locate.sdk_package if sdk_package is None else sdk_package,
            operations={**locate.operations, **operations_over},
            fields={**locate.fields, **fields_over},
        )

    if command is not None:
        parts = shlex.split(command)
        if not parts:
            raise ValueError(f"--check must not be blank: {command!r}")
    else:
        parts = config.command

    return CliConfig(
        locate=locate,
        command=tuple(parts),
        require=config.require if require is None else a_level(require, "--require"),
        breaking_only=config.breaking_only if breaking_only is None else breaking_only,
    )
