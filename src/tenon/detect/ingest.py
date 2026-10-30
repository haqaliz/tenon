"""Turn a file on disk into an OpenAPI 3.x document, or refuse it by name."""

import re
from pathlib import Path

import yaml

from .record import RefusalCode, SpecRefusal

# A JSON pointer in URI-fragment form, before unescaping.
_LOCAL_REF = re.compile(r"#(?:/(?:[^~]|~[01])*)*")


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
            try:
                return resolve_refs(document)
            except SpecRefusal as refusal:
                raise SpecRefusal(
                    refusal.code, refusal.pointer, message=f"{source}: {refusal.message}"
                ) from None
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


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def resolve_refs(document: dict) -> dict:
    """Return a fresh document with every local ``$ref`` replaced by its target.

    A back-edge is left as ``{"$ref": ref}``: inlining it again would add no
    depth, and the marker is what the differ reports as unanalyzed.
    """

    def lookup(ref: str):
        node = document
        for raw in ref[2:].split("/") if ref != "#" else ():
            token = raw.replace("~1", "/").replace("~0", "~")
            try:
                node = node[int(token)] if isinstance(node, list) else node[token]
            except (KeyError, IndexError, TypeError, ValueError):
                raise SpecRefusal(
                    RefusalCode.UNRESOLVED_REF, ref, message=f"no node at {ref}"
                ) from None
        return node

    def walk(node, pointer: str, chain: tuple[str, ...]):
        if isinstance(node, dict):
            if "$ref" in node:
                return deref(node["$ref"], f"{pointer}/$ref", chain)
            # The current node is part of the document being expanded, so a ref
            # back to it closes a cycle here, at its first nested occurrence.
            nested = (*chain, pointer)
            return {
                key: walk(value, f"{pointer}/{_escape(str(key))}", nested)
                for key, value in node.items()
            }
        if isinstance(node, list):
            nested = (*chain, pointer)
            return [
                walk(item, f"{pointer}/{index}", nested)
                for index, item in enumerate(node)
            ]
        return node

    def deref(ref, where: str, chain: tuple[str, ...]):
        if not isinstance(ref, str):
            raise SpecRefusal(
                RefusalCode.UNRESOLVED_REF,
                where,
                message=f"not a JSON pointer: {ref!r}",
            )
        if not ref.startswith("#"):
            raise SpecRefusal(
                RefusalCode.EXTERNAL_REF,
                where,
                message=f"cannot fetch external $ref {ref!r}",
            )
        if not _LOCAL_REF.fullmatch(ref):
            raise SpecRefusal(
                RefusalCode.UNRESOLVED_REF,
                where,
                message=f"not a JSON pointer: {ref!r}",
            )
        if ref in chain:
            return {"$ref": ref}
        return walk(lookup(ref), ref, (*chain, ref))

    return walk(document, "#", ())


def load(path: str | Path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{path}: cannot read: {exc}"
        ) from None
    return parse(text, str(path))
