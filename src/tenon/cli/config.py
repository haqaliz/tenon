"""Resolve ``tenon.toml`` and CLI flags into one CLI config. No pipeline calls."""

import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from tenon.locate import LocateConfig, McpLocateConfig, TsLocateConfig
from tenon.prove import ProofLevel

LANGUAGES = ("python", "ts")
SOURCES = ("openapi", "mcp")


@dataclass(frozen=True, slots=True)
class CliConfig:
    """Everything one CLI run needs before it starts."""

    locate: LocateConfig | TsLocateConfig | McpLocateConfig
    command: tuple[str, ...] = ()
    build: tuple[str, ...] = ()
    characterize: tuple[str, ...] = ()
    replay: tuple[str, ...] = ()
    require: ProofLevel = ProofLevel.TESTS_PASSED
    breaking_only: bool = False
    language: Literal["python", "ts"] = "python"
    source: Literal["openapi", "mcp"] = "openapi"

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError(
                f"language must be python or ts: {self.language!r}"
            )
        if self.source not in SOURCES:
            raise ValueError(
                f"source must be openapi or mcp: {self.source!r}"
            )
        if self.source == "mcp" and self.language != "python":
            raise ValueError(
                f"source mcp requires language python: {self.language!r}"
            )
        for name in ("command", "build", "characterize", "replay"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not isinstance(self.require, ProofLevel):
            object.__setattr__(self, "require", ProofLevel(self.require))


def a_level(value: object, source: str) -> ProofLevel:
    """One of the five ladder levels; anything else names the whole ladder."""
    try:
        return ProofLevel(value)
    except ValueError:
        names = ", ".join(level.value for level in ProofLevel)
        raise ValueError(
            f"{source} must be one of {names}: {value!r}"
        ) from None


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


def a_command(tenon: dict, path: str | Path, key: str) -> tuple[str, ...]:
    """One stage's command array, validated exactly like ``command``."""
    value = tenon.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(
            f"{path}: [tenon] {key} must be an array of non-empty strings"
        )
    return tuple(value)


def load_cli_config(
    path: str | Path, language: str | None = None, source: str | None = None
) -> CliConfig:
    """Read ``[locate]`` and ``[tenon]`` from one TOML file."""
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise ValueError(f"{path}: {error}") from error

    section = data.get("locate")
    if not isinstance(section, dict):
        raise ValueError(f"{path}: missing the [locate] table")
    chosen_source = section.get("source", "openapi") if source is None else source
    if not isinstance(chosen_source, str) or chosen_source not in SOURCES:
        raise ValueError(
            f"{path}: [locate] source must be openapi or mcp: {chosen_source!r}"
        )
    chosen = section.get("language", "python") if language is None else language
    if not isinstance(chosen, str) or chosen not in LANGUAGES:
        raise ValueError(
            f"{path}: [locate] language must be python or ts: {chosen!r}"
        )
    if chosen_source == "mcp" and chosen != "python":
        raise ValueError(
            f"{path}: [locate] source mcp requires language python: {chosen!r}"
        )
    operations = section.get("operations", {})
    if not isinstance(operations, dict):
        raise ValueError(f"{path}: [locate] operations must be a table")
    fields = section.get("fields", {})
    if not isinstance(fields, dict):
        raise ValueError(f"{path}: [locate] fields must be a table")

    tenon = data.get("tenon", {})
    if not isinstance(tenon, dict):
        raise ValueError(f"{path}: [tenon] must be a table")
    commands = {
        key: a_command(tenon, path, key)
        for key in ("command", "build", "characterize", "replay")
    }
    breaking_only = tenon.get("breaking_only", False)
    if not isinstance(breaking_only, bool):
        raise ValueError(f"{path}: [tenon] breaking_only must be a bool")

    if chosen_source == "mcp":
        # Spec AC2: the MCP client package is optional and defaults to mcp.
        locate: LocateConfig | TsLocateConfig | McpLocateConfig = McpLocateConfig(
            client_package=section.get("sdk_package", "mcp")
        )
    else:
        if "sdk_package" not in section:
            raise ValueError(f"{path}: [locate] is missing sdk_package")
        locate_type = TsLocateConfig if chosen == "ts" else LocateConfig
        locate = locate_type(
            sdk_package=section["sdk_package"],
            operations=operations,
            fields=fields,
        )

    return CliConfig(
        locate=locate,
        command=commands["command"],
        build=commands["build"],
        characterize=commands["characterize"],
        replay=commands["replay"],
        require=a_level(
            tenon.get("require", ProofLevel.TESTS_PASSED), f"{path}: [tenon] require"
        ),
        breaking_only=breaking_only,
        language=chosen,
        source=chosen_source,
    )


def _split(value: str, flag: str) -> tuple[str, ...]:
    parts = shlex.split(value)
    if not parts:
        raise ValueError(f"{flag} must not be blank: {value!r}")
    return tuple(parts)


def _package(locate: LocateConfig | TsLocateConfig | McpLocateConfig) -> str:
    """The package a locate config scans, under either source."""
    return (
        locate.client_package
        if isinstance(locate, McpLocateConfig)
        else locate.sdk_package
    )


def overrides(
    config: CliConfig,
    *,
    sdk_package: str | None = None,
    operations: Sequence[str] = (),
    fields: Sequence[str] = (),
    command: str | None = None,
    build: str | None = None,
    characterize: str | None = None,
    replay: str | None = None,
    require: str | None = None,
    breaking_only: bool | None = None,
    language: str | None = None,
    source: str | None = None,
) -> CliConfig:
    """Apply flags over the config; only supplied flags change anything."""
    chosen = config.language if language is None else language
    if chosen not in LANGUAGES:
        raise ValueError(f"--language must be python or ts: {language!r}")
    chosen_source = config.source if source is None else source
    if chosen_source not in SOURCES:
        raise ValueError(f"--source must be openapi or mcp: {source!r}")
    if chosen_source == "mcp" and chosen != "python":
        raise ValueError(f"--source mcp requires --language python: {chosen!r}")

    locate = config.locate
    source_changed = chosen_source != config.source
    if chosen_source == "mcp":
        # Spec AC2: an MCP config carries a client package, not API tables.
        if source_changed or sdk_package is not None:
            locate = McpLocateConfig(
                client_package=(
                    _package(config.locate)
                    if sdk_package is None
                    else sdk_package
                )
            )
    else:
        operations_over = a_pairs(operations, "--operation")
        fields_over = a_pairs(fields, "--field")
        if (
            source_changed
            or sdk_package is not None
            or operations_over
            or fields_over
            or chosen != config.language
        ):
            locate_type = TsLocateConfig if chosen == "ts" else LocateConfig
            openapi = not isinstance(config.locate, McpLocateConfig)
            locate = locate_type(
                sdk_package=(
                    _package(config.locate)
                    if sdk_package is None
                    else sdk_package
                ),
                operations={
                    **(config.locate.operations if openapi else {}),
                    **operations_over,
                },
                fields={**(config.locate.fields if openapi else {}), **fields_over},
            )

    if command is not None:
        command_parts = _split(command, "--check")
    else:
        command_parts = config.command

    return CliConfig(
        locate=locate,
        command=tuple(command_parts),
        build=config.build if build is None else _split(build, "--build"),
        characterize=(
            config.characterize
            if characterize is None
            else _split(characterize, "--characterize")
        ),
        replay=config.replay if replay is None else _split(replay, "--replay"),
        require=config.require if require is None else a_level(require, "--require"),
        breaking_only=config.breaking_only if breaking_only is None else breaking_only,
        language=chosen,
        source=chosen_source,
    )


def resolve_config_path(repo: str | Path, explicit: str | None) -> Path | None:
    """The explicit file, else ``<repo>/tenon.toml``, else None."""
    if explicit is not None:
        return Path(explicit)
    candidate = Path(repo) / "tenon.toml"
    return candidate if candidate.is_file() else None
