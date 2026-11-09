"""The provider fan-out repo list: a UTF-8 text file of local checkout paths."""

from pathlib import Path


def load_repos(path: str | Path) -> tuple[Path, ...]:
    """Read one repos file into resolved local paths."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{path}: {error}") from error

    repos = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        repos.append((path.parent / Path(value).expanduser()).resolve())
    if not repos:
        raise ValueError(f"{path}: repos list has no paths")
    return tuple(repos)
