"""A portable provider migration bundle: the schema and its JSON loader."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tenon.locate import LocateConfig, TsLocateConfig
from tenon.prove import ProofLevel


@dataclass(frozen=True, slots=True)
class MigrationBundle:
    """Everything one provider migration needs before a repo is touched."""

    provider: str
    migration: str
    source: Literal["openapi", "mcp"]
    language: Literal["python", "ts"]
    old: Path
    new: Path
    locate: LocateConfig | TsLocateConfig
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
    locate = data["locate"]
    locate_type = LocateConfig if data["language"] == "python" else TsLocateConfig
    return MigrationBundle(
        provider=data["provider"],
        migration=data["migration"],
        source=data["source"],
        language=data["language"],
        old=Path(data["old"]),
        new=Path(data["new"]),
        locate=locate_type(
            sdk_package=locate["sdk_package"],
            operations=locate.get("operations", {}),
            fields=locate.get("fields", {}),
        ),
        command=tuple(data.get("command", [])),
        build=tuple(data.get("build", [])),
        characterize=tuple(data.get("characterize", [])),
        replay=tuple(data.get("replay", [])),
        require=ProofLevel(data.get("require", ProofLevel.TESTS_PASSED)),
        breaking_only=data.get("breaking_only", False),
    )
