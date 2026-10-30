"""Turn a file on disk into an OpenAPI 3.x document, or refuse it by name."""

import re
from pathlib import Path

import yaml

from .record import RefusalCode, SpecRefusal

# A JSON pointer in URI-fragment form, before unescaping.
_LOCAL_REF = re.compile(r"#(?:/(?:[^~]|~[01])*)*")


def parse(text: str, source: str) -> dict:
    """Return the resolved document for ``text``, or refuse it by name.

    The document may share subtrees (it is a DAG); do not ``json.dumps`` it,
    because that expands the shared nodes exponentially.
    """
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
    """Return the document with every local ``$ref`` replaced by its target.

    Every raw dict/list resolves once and is shared, so the result is a DAG:
    two refs to the same node return the same object. Do not serialise it;
    ``json.dumps`` expands the shared subtrees exponentially.

    A back-edge is left as ``{"$ref": ref}``: inlining it again would add no
    depth, and the marker is what the differ reports as unanalyzed.
    """
    cache: dict[int, object] = {}
    active: set[int] = set()  # raw node ids on the current resolution path

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

    def target_of(ref, where: str):
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
        return lookup(ref)

    def walk(node, pointer: str):
        if not isinstance(node, (dict, list)):
            return node
        key = id(node)
        if key in cache:
            return cache[key]
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            target = target_of(ref, f"{pointer}/$ref")
            if not isinstance(target, (dict, list)):
                return target
            target_key = id(target)
            if target_key in cache:
                return cache[target_key]
            if target_key in active:
                return {"$ref": ref}
            active.add(target_key)
            try:
                resolved = walk(target, ref)
            finally:
                active.discard(target_key)
            # A marker belongs to the back-edge that produced it; sharing it
            # would give another back-edge the wrong ref string.
            if isinstance(resolved, dict) and "$ref" in resolved:
                return resolved
            cache[key] = resolved
            return resolved
        active.add(key)
        try:
            if isinstance(node, dict):
                resolved = {
                    child: walk(value, f"{pointer}/{_escape(str(child))}")
                    for child, value in node.items()
                }
            else:
                resolved = [
                    walk(item, f"{pointer}/{index}")
                    for index, item in enumerate(node)
                ]
        finally:
            active.discard(key)
        cache[key] = resolved
        return resolved

    return walk(document, "#")


def load(path: str | Path) -> dict:
    """Read ``path`` and return the resolved document from :func:`parse`.

    The document may share subtrees; do not ``json.dumps`` it.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecRefusal(
            RefusalCode.UNPARSEABLE, message=f"{path}: cannot read: {exc}"
        ) from None
    return parse(text, str(path))
