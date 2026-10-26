# Spec: change-record

**Slug:** `openapi-differ` · **Aspect 1 of 4** · builds first, everything depends on it.

## Problem slice

The typed unit that T2/T3/T4 consume does not exist. This aspect defines it — the record shape, its
canonical ordering, and the refusal vocabulary — with no parsing or diffing logic.

## In scope

- `Change`: `kind`, `location`, `before`, `after`, `breaking`, `confidence`. Frozen dataclass.
- `Location`: `method` (HTTP method or `None`), `path` (spec path or `None`), `pointer` (JSON pointer).
- `ChangeKind`: exactly the 13 kinds from PRD M2.
- `DiffResult`: holds `changes`, exposes `to_dict()` / `to_json()`.
- Canonical ordering: sort by `(pointer, kind, before_key, after_key)` where the keys are
  JSON-normalized strings, so ordering never depends on input dict order.
- `SpecRefusal(Exception)`: `code` (one of the 6 PRD codes), `pointer` (or line/column for
  `UNPARSEABLE`), `message`. `str()` must render code + pointer + message.
- JSON-safe serialization: only `str|int|float|bool|None|list|dict` in the output.

## Out of scope

- Any spec parsing, `$ref` resolution, walking, comparison or rename logic.
- CLI/exit codes.
- A `severity` ladder, human prose, or patch payloads.

## Acceptance criteria

1. All 13 kinds are constructible and round-trip through `to_dict()`/`from_dict()`.
2. `DiffResult` built from the same changes in two different insertion orders yields byte-identical
   `to_json()`.
3. `to_json()` is byte-identical across two runs with different `PYTHONHASHSEED`.
4. `to_json()` output parses as JSON and contains no tuples, sets, enums-as-objects or dataclass reprs.
5. `SpecRefusal` carries a code from the closed set and renders it in `str()`; an unknown code is not
   constructible (use the enum, not a bare string).
6. `Location.pointer` is validated as a syntactically valid RFC 6901 pointer.

## Dependencies & sequencing

None. First. `spec-ingest`, `diff-core` and `rename-inference` all import from this module.

## Open questions

- `pointer` semantics: it addresses the **enclosing container** that exists in the document being
  described (e.g. `#/paths/~1users/get/parameters`), not the removed item itself, since a removed
  property does not exist in the new document. PRD M5 wording is read this way. Confirm during
  implementation with one fixture asserting the pointer resolves in the right document.
