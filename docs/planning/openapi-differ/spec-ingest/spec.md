# Spec: spec-ingest

**Slug:** `openapi-differ` · **Aspect 2 of 4** · depends on `change-record`.

## Problem slice

Turn a file on disk into a resolved OpenAPI 3.x document, or refuse it by name. This is the only
place that touches the filesystem, YAML, and `$ref` — everything downstream works on plain dicts.

## In scope

- `load(path) -> dict` and `parse(text, source) -> dict` (the latter for inline fixtures).
- YAML and JSON via one `yaml.safe_load` path (JSON is valid YAML); parse errors become
  `UNPARSEABLE` with line/column when the loader provides them.
- Version gate: accept `openapi` matching `3.0.*` or `3.1.*`. Missing/`swagger` key → `NOT_A_SPEC`;
  any other version (2.0, 4.x, malformed) → `UNSUPPORTED_VERSION`.
- Local `$ref` resolution: `#/a/b/~1c` → the referenced node, with cycle detection.
- Refusals: `EXTERNAL_REF` for `file:`/`http(s):`/relative refs, `UNRESOLVED_REF` for a pointer that
  does not exist.

## Out of scope

- Multi-file bundles, `$ref` fetching over the network, Swagger 2.0 normalization.
- Semantic validation of the OpenAPI document (we are not a linter).
- Composition policy — that belongs to `diff-core`, which is where the pointer to the offender is
  known.

## Acceptance criteria

1. A valid 3.0.x YAML spec and a valid 3.1.x JSON spec both load to a dict.
2. Swagger 2.0, a random YAML file, an empty file, and a YAML syntax error each raise
   `SpecRefusal` with the expected code — and never `KeyError`/`TypeError`.
3. A local `$ref` chain (`A → B → C`) resolves; a self-referential chain raises
   `UNRESOLVED_REF` or a dedicated cycle refusal (decide once, assert it) rather than recursing.
4. An `https://` ref raises `EXTERNAL_REF` naming the pointer where it was found.
5. A pointer into a missing key raises `UNRESOLVED_REF` naming that pointer.
6. Refusals from `load` include the file path in the message.

## Dependencies & sequencing

After `change-record` (imports the refusal type). Before `diff-core`, which assumes `$ref`s are
already resolvable.

## Open questions

- Cycle policy: refuse the whole document, or resolve cycles by identity? Default: refuse, because a
  partial resolution would violate "no partial results".
