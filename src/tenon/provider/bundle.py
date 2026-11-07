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


def load_bundle(path: str | Path) -> MigrationBundle:
    """Read one JSON bundle into its dataclass."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    source = data["source"]
    language = data["language"]
    if source not in SOURCES:
        raise ValueError(f"{path}: source must be openapi or mcp: {source!r}")
    if language not in LANGUAGES:
        raise ValueError(f"{path}: language must be python or ts: {language!r}")
    if source == "mcp" and language != "python":
        raise ValueError(
            f"{path}: source mcp requires language python: {language!r}"
        )
    old = (path.parent / data["old"]).resolve()
    new = (path.parent / data["new"]).resolve()
    for key, spec in (("old", old), ("new", new)):
        if not spec.is_file():
            raise ValueError(f"{path}: {key} is not a readable file: {spec}")

    locate = data["locate"]
    if source == "mcp":
        config: LocateConfig | TsLocateConfig | McpLocateConfig = McpLocateConfig(
            client_package=locate["sdk_package"]
        )
    else:
        locate_type = TsLocateConfig if language == "ts" else LocateConfig
        config = locate_type(
            sdk_package=locate["sdk_package"],
            operations=locate.get("operations", {}),
            fields=locate.get("fields", {}),
        )
    return MigrationBundle(
        provider=data["provider"],
        migration=data["migration"],
        source=source,
        language=language,
        old=old,
        new=new,
        locate=config,
        command=tuple(data.get("command", [])),
        build=tuple(data.get("build", [])),
        characterize=tuple(data.get("characterize", [])),
        replay=tuple(data.get("replay", [])),
        require=ProofLevel(data.get("require", ProofLevel.TESTS_PASSED)),
        breaking_only=data.get("breaking_only", False),
    )
