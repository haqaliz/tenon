"""A portable provider migration bundle: the schema and its JSON loader."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tenon.locate import LocateConfig, McpLocateConfig, TsLocateConfig
from tenon.prove import ProofLevel

SOURCES = ("openapi", "mcp")
LANGUAGES = ("python", "ts")


@dataclass(frozen=True, slots=True)
class MigrationBundle:
    """Everything one provider migration needs before a repo is touched."""

    provider: str
    migration: str
    source: Literal["openapi", "mcp"]
    language: Literal["python", "ts"]
    old: Path
    new: Path
    locate: LocateConfig | TsLocateConfig | McpLocateConfig
    command: tuple[str, ...] = ()
    build: tuple[str, ...] = ()
    characterize: tuple[str, ...] = ()
    replay: tuple[str, ...] = ()
    require: ProofLevel = ProofLevel.TESTS_PASSED
    breaking_only: bool = False


def a_text(data: dict, key: str, path: Path) -> str:
    """One required non-blank string, named with the bundle path."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {key} must be a non-empty string")
    return value


def a_spec(data: dict, key: str, path: Path) -> Path:
    """One spec path, resolved against the bundle and checked readable."""
    spec = (path.parent / a_text(data, key, path)).resolve()
    if not spec.is_file():
        raise ValueError(f"{path}: {key} is not a readable file: {spec}")
    return spec


def a_mapping(locate: dict, key: str, path: Path) -> dict[str, str]:
    """One optional locate mapping of strings to strings."""
    value = locate.get(key, {})
    if not isinstance(value, dict) or not all(
        isinstance(mapped, str) for mapped in value.values()
    ):
        raise ValueError(
            f"{path}: locate {key} must be a mapping of strings to strings"
        )
    return value


def a_locate(
    data: dict, source: str, language: str, path: Path
) -> LocateConfig | TsLocateConfig | McpLocateConfig:
    """The locate config type follows source and language."""
    locate = data.get("locate")
    if not isinstance(locate, dict):
        raise ValueError(f"{path}: locate must be an object")
    sdk_package = a_text(locate, "sdk_package", path)
    operations = a_mapping(locate, "operations", path)
    fields = a_mapping(locate, "fields", path)
    try:
        if source == "mcp":
            return McpLocateConfig(client_package=sdk_package)
        locate_type = TsLocateConfig if language == "ts" else LocateConfig
        return locate_type(
            sdk_package=sdk_package, operations=operations, fields=fields
        )
    except ValueError as error:
        raise ValueError(f"{path}: locate sdk_package: {error}") from None


def a_command(data: dict, key: str, path: Path) -> tuple[str, ...]:
    """One optional stage command: an array of non-empty strings."""
    value = data.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{path}: {key} must be an array of non-empty strings")
    return tuple(value)


def a_require(data: dict, path: Path) -> ProofLevel:
    """One of the five proof levels, defaulting to the shipped one."""
    value = data.get("require", ProofLevel.TESTS_PASSED)
    try:
        return ProofLevel(value)
    except (TypeError, ValueError):
        names = ", ".join(level.value for level in ProofLevel)
        raise ValueError(
            f"{path}: require must be one of {names}: {value!r}"
        ) from None


def load_bundle(path: str | Path) -> MigrationBundle:
    """Read one JSON bundle into its dataclass."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path}: bundle must be a JSON object")

    provider = a_text(data, "provider", path)
    migration = a_text(data, "migration", path)
    source = a_text(data, "source", path)
    if source not in SOURCES:
        raise ValueError(f"{path}: source must be openapi or mcp: {source!r}")
    language = a_text(data, "language", path)
    if language not in LANGUAGES:
        raise ValueError(f"{path}: language must be python or ts: {language!r}")
    if source == "mcp" and language != "python":
        raise ValueError(
            f"{path}: source mcp requires language python: {language!r}"
        )

    old = a_spec(data, "old", path)
    new = a_spec(data, "new", path)
    locate = a_locate(data, source, language, path)

    breaking_only = data.get("breaking_only", False)
    if not isinstance(breaking_only, bool):
        raise ValueError(f"{path}: breaking_only must be a bool")

    return MigrationBundle(
        provider=provider,
        migration=migration,
        source=source,
        language=language,
        old=old,
        new=new,
        locate=locate,
        command=a_command(data, "command", path),
        build=a_command(data, "build", path),
        characterize=a_command(data, "characterize", path),
        replay=a_command(data, "replay", path),
        require=a_require(data, path),
        breaking_only=breaking_only,
    )
