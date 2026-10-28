"""Optional ``tenon.toml`` loader. The in-memory LocateConfig is the real API."""

import tomllib
from pathlib import Path

from .result import LocateConfig


def load_config(path: str | Path) -> LocateConfig:
    """Read ``[locate]`` from a TOML file, naming the key a bad file lacks."""
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    if "locate" not in data:
        raise ValueError(f"{path}: missing the [locate] table")
    section = data["locate"]
    if "sdk_package" not in section:
        raise ValueError(f"{path}: [locate] is missing sdk_package")
    return LocateConfig(
        sdk_package=section["sdk_package"],
        operations=section.get("operations", {}),
        fields=section.get("fields", {}),
    )
