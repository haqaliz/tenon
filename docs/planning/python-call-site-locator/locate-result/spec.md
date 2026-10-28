# Spec: locate-result

**Slug:** `python-call-site-locator` · **Aspect 1 of 4** · builds first, everything depends on it.

## Problem slice

T3 and T4 need a stable, honest answer shape before any scanning exists: what a site is, what an
ambiguity group is, when a result carries a reason, and how it serializes. This aspect defines the
contract and nothing else — no query derivation, no filesystem, no `ast`.

## In scope

- `LocateConfig`: `sdk_package: str` (dotted roots allowed, e.g. `google.cloud.storage`),
  `operations: Mapping[str, str]`, `fields: Mapping[str, str]`. Frozen; empty string package is a
  `ValueError`.
- `Site`: `path` (repo-relative, `/` separators), `line` (1-based), `column` (1-based character
  column, not byte offset), `shape` (`call|keyword|dict_key|attribute`), `symbol`, optional
  `line_text`.
- `AmbiguousGroup`: `reason`, `symbol`, `candidates: tuple[Site, ...]` (at least one candidate).
- `LocateResult`: `change`, `certain`, `ambiguous`, `reason`. Invariant: `reason is not None` iff
  both lists are empty; a non-empty result with a reason is a construction error.
- Reason enums: `LocateReason` (`UNSUPPORTED_CHANGE_KIND`, `NO_SDK_IMPORT`,
  `OPERATION_NOT_MAPPED`, `NO_SITES`) and `AmbiguityReason` (`DYNAMIC_KWARGS`, `DYNAMIC_GETATTR`,
  `ALIAS_CHAIN`, `UNROOTED_RECEIVER`, `MULTIPLE_CANDIDATES`, `UNMAPPED_SYMBOL`).
- Canonical order: `certain` and each group's `candidates` sorted by `(path, line, column, symbol)`;
  groups sorted by `(reason, symbol)`.
- `to_dict()` / `to_json()`: JSON-safe primitives only, `sort_keys=True`, byte-stable.
- Optional `load_config(path)` for `tenon.toml` `[locate]` (PRD S1) — stdlib `tomllib`, refused with
  a plain `ValueError` naming the missing key. Ships only if it stays under ~40 lines with tests.

## Out of scope

- Reading source files, `ast`, import graphs.
- Extracting names from a `Change` (aspect 2).
- Deciding certain vs ambiguous (aspect 4).
- CLI, exit codes, human rendering.

## Acceptance criteria

1. All four shapes, both reason enums, and every reason value are constructible and round-trip
   through `to_dict()` → valid JSON.
2. `LocateResult` built from the same sites in different insertion orders yields byte-identical
   `to_json()`.
3. `to_json()` is byte-identical across two runs with different `PYTHONHASHSEED`; no tuples, sets,
   enums-as-objects or dataclass reprs appear.
4. Constructing a result with a reason **and** a non-empty `certain`/`ambiguous` list raises
   `ValueError`; an empty result with `reason=None` also raises.
5. A group with zero candidates raises `ValueError`.
6. `LocateConfig(sdk_package="")` raises `ValueError`.
7. `load_config` (if shipped) parses all three tables from a fixture `tenon.toml` and names the
   missing key on a bad file.

## Dependencies & sequencing

None. First. Aspects 2-4 import from this module.

## Open questions

- Does a `Site` need the enclosing symbol (function/class name) for T3/T4? Not needed to rewrite a
  line, but useful in a report. Deferred; adding a field later is additive.
