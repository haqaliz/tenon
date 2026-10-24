"""Turn a file on disk into an OpenAPI 3.x document, or refuse it by name."""

from pathlib import Path

import yaml

from .record import RefusalCode, SpecRefusal


def parse(text: str, source: str) -> dict:
    if not text.strip():
        raise SpecRefusal(RefusalCode.UNPARSEABLE, message=f"{source}: empty document")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        position = (
            f"line {mark.line + 1}, column {mark.column + 1}" if mark else "unknown position"
        )
        problem = getattr(exc, "problem", None) or "invalid YAML"
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{source}: {problem} at {position}"
        ) from None
    if not isinstance(document, dict):
        raise SpecRefusal(RefusalCode.NOT_A_SPEC, "#", message=f"{source}: not a mapping")
    if "openapi" in document:
        version = document["openapi"]
        if isinstance(version, str) and version.startswith(("3.0.", "3.1.")):
            return document
        raise SpecRefusal(
            RefusalCode.UNSUPPORTED_VERSION,
            "#/openapi",
            message=f"{source}: unsupported OpenAPI version {version!r}",
        )
    if "swagger" in document:
        raise SpecRefusal(
            RefusalCode.UNSUPPORTED_VERSION,
            "#/swagger",
            message=f"{source}: Swagger {document['swagger']!r} is not OpenAPI 3.x",
        )
    raise SpecRefusal(
        RefusalCode.NOT_A_SPEC, "#", message=f"{source}: no 'openapi' version"
    )


def load(path: str | Path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{path}: cannot read: {exc}"
        ) from None
    return parse(text, str(path))
