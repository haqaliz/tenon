# PRD: OpenAPI differ (T1 — change detection)

- **Slug:** `openapi-differ`
- **Capability:** T1 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M0.1 in `docs/ROADMAP.md` (Phase 0)
- **Status:** draft, awaiting review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

Tenon's entire pipeline starts from a machine-readable description of what changed. Nothing else
exists yet: `docs/technical/ARCHITECTURE.md` defines the Change record as "the unit" every
downstream stage consumes, and `CLAUDE.md` constraint 3 restricts trusted change sources to
machine-readable ones (OpenAPI diffs, SDK metadata, MCP schemas — a changelog paragraph is a hint).

Today, given two versions of an OpenAPI document, there is no way in this codebase to say *what*
changed in a form a program can act on. A human reading the vendor's changelog is exactly the
failure mode the product exists to replace (87.3% of breaking API versions published no deprecation
notice in the prior version — `VISION.md`).

**For whom:** the rest of Tenon. This card has no end user; its consumer is T2 (locate), T3
(propose), T4 (prove). Its indirect user is the developer running `tenon check` in M1.4.

## Goals & Success Metrics

1. **Typed, complete enumeration.** Two OpenAPI 3.x documents diff into a deterministic list of
   `Change` records covering: endpoint removed/added, parameter removed / required-added /
   type-changed, schema property removed/added / required-added / type-changed, enum narrowed,
   schema added/removed, and renamed (endpoint parameter or schema property).
2. **Honest failure.** Every input the differ cannot faithfully analyze produces a *named refusal*
   carrying a code and a JSON pointer — never an exception, never a partial result. This is the
   `detect` half of "ambiguity is reported, never guessed".
3. **Determinism.** The same two inputs produce identical records in identical order, and
   `json.dumps` of the result is byte-identical across runs and across `PYTHONHASHSEED` values.
4. **Real-spec readiness.** When the first vendor/SDK pair is chosen (open question in
   `CAPABILITY_ROADMAP.md`), it either diffs without refusal or refuses naming the exact pointer
   that blocked it. That refusal is the input to a follow-up card, not a silent gap.

Measured by fixtures in `tests/`, not by opinion. No network, no model calls.

## User Personas & Scenarios

- **T2 locate (primary consumer).** "Give me the changes, and for each one tell me what to look for
  in the user's repository" — needs `location` (method + path + JSON pointer), old and new symbol
  names, and whether the change is breaking.
- **T3 propose.** Needs the same record plus `confidence`, so an inferred rename can be proposed
  with a visible caveat while a `certain` removal is mechanical.
- **Developer reading the output (M1.4).** Needs stable ordering so diffs and JSON are reviewable.

## Requirements

### Must have

- **M1 — Input formats.** Accept OpenAPI **3.0.x and 3.1.x** in YAML or JSON. Any other version
  (including Swagger 2.0) is refused with `UNSUPPORTED_VERSION`.
- **M2 — Change kinds.** Emit these `kind` values, each with `breaking: bool`:
  `endpoint_removed`, `endpoint_added`, `parameter_removed`, `parameter_required_added`,
  `parameter_type_changed`, `property_removed`, `property_added`, `property_required_added`,
  `property_type_changed`, `enum_narrowed`, `schema_removed`, `schema_added`, `renamed`.
- **M3 — Scope walked.** Paths → operations (by HTTP method) → parameters (path/query/header/cookie,
  including path-level parameters inherited by operations) → request body and response schemas,
  recursing into object properties and array items.
- **M4 — `$ref` resolution.** Resolve local `#/components/...` references, with cycle detection.
  External/remote references are refused with `EXTERNAL_REF`.
- **M5 — Composition policy.** Traverse `allOf` when it is a plain property merge. `oneOf`,
  `anyOf`, `discriminator`, and any `allOf` that is not a plain merge are refused with
  `UNSUPPORTED_COMPOSITION` naming the pointer. Never silently skip a subtree.
- **M6 — Rename inference.** Pair a removed name with an added name **only when exactly one
  candidate** matches on location, type and schema shape. Emit `renamed` with
  `confidence: "inferred"`. Ambiguous or zero-match cases emit `removed` + `added` with
  `confidence: "certain"`.
- **M7 — Named refusals.** `SpecRefusal` with codes: `NOT_A_SPEC`, `UNSUPPORTED_VERSION`,
  `UNPARSEABLE`, `UNRESOLVED_REF`, `EXTERNAL_REF`, `UNSUPPORTED_COMPOSITION`, plus a JSON pointer
  (or line/column for `UNPARSEABLE`) and a human-readable message.
- **M8 — Canonical order.** Records sorted by `(pointer, kind, before_key, after_key)` so output is
  stable regardless of dict insertion order in the input.
- **M9 — Serializable record.** `Change.to_dict()` producing JSON-safe primitives; a result object
  with `to_json()` that is byte-stable.

### Should have

- **S1 — 3.1 normalization.** `type: ["string","null"]` and 3.0's `nullable: true` normalize to the
  same comparison basis, so a nullability-only change is *not* reported as a type change, and a real
  type change is. Numeric `exclusiveMinimum` (3.1) vs boolean (3.0) likewise normalized.
- **S2 — Enum handling.** `enum_narrowed` fires when the new enum is a strict subset; widened or
  equal is not a change.

### Nice to have

- **N1 — `description` / `deprecated` flags carried on the record.** Useful for T3 prose, not
  needed for correctness. Skipped unless free.

## Data Model

```
Change
  kind:       enum (M2)
  location:   Location { method: str|None, path: str|None, pointer: str }   # JSON pointer into the new doc
  before:     JSON value | None
  after:      JSON value | None
  breaking:   bool
  confidence: "certain" | "inferred"
```

`renamed` carries `before` = old name and `after` = new name, with `location` pointing at the
enclosing object (the parent path item, parameter list, or schema).

Deliberately absent: a patch, a severity ladder, a human message. T3 owns patches; `CLAUDE.md`
forbids a model's output standing in for a check, and this card produces no patch at all.

## API Contract

```python
from tenon.detect import diff, load, SpecRefusal, Change, DiffResult

old = load("spec-v1.yaml")          # dict; raises SpecRefusal
new = load("spec-v2.yaml")
result: DiffResult = diff(old, new)  # raises SpecRefusal; never returns partial on refusal
result.changes                       # list[Change], canonically ordered
result.to_json()                     # str, byte-stable
```

No CLI, no exit codes, no file writing. Those are M1.4.

## Technical Considerations

- **Greenfield.** No `pyproject.toml`, no `src/`, no `tests/` exist. This card scaffolds the package
  (`uv`, `src/tenon/detect/`, `tests/`) per `ARCHITECTURE.md`'s planned layout.
- **Dependencies:** `pyyaml` for YAML specs; `pytest` for tests. Nothing else. No network access at
  test time; fixtures are committed spec pairs.
- **Python:** `requires-python >= 3.11` (system Python is 3.9; `uv` provisions).
- **Determinism** is a testable property, not a hope: sort keys, no set iteration in output, no
  timestamps in records.
- **Refusal is a result path, not an exception leak.** `SpecRefusal` is an exception type in the
  API but must be the only one escaping `diff`/`load` for bad input; tests assert no `KeyError`,
  `TypeError` or traceback for each malformed fixture.

## Risks & Open Questions

- **R3 (from `docs/ROADMAP.md`):** machine-readable changes are rare for many vendors. T1 assumes
  the source exists; this card does not help a vendor that only ships a changelog. Accepted — T1
  makes the machine-readable case work, and the changelog case is explicitly out of scope.
- **Taxonomy drift (new):** a complete change taxonomy can outrun what T3 can mechanically repair.
  Mitigation: `breaking` and `confidence` on every record, so T3 filters rather than guesses; the
  two consumers are named above so the shape is not designed in a vacuum.
- **Real-spec surprise (new, highest):** the first real vendor spec may refuse at a composition or
  `$ref` pattern these fixtures don't cover. Mitigation: refusals name the pointer, so the follow-up
  is a scoped card rather than a mystery. This is the M0.3 prerequisite risk.
- **Open question — first real case.** `CAPABILITY_ROADMAP.md` asks which vendor/SDK is first.
  Still unanswered; T1 is buildable without it, and the answer should become a committed fixture
  pair as soon as it is picked.
- **Open question — 3.1-only constructs** (`webhooks`, `jsonSchemaDialect`): currently unanalyzed
  and silently ignored because they are outside paths/schemas. Flag if that is considered a partial
  result.

## Out of Scope

- CLI, exit codes, JSON output surface (`tenon check` — M1.4).
- Any patching, proposing or proof (T3, T4).
- Call-site location (T2).
- MCP schema diffs and SDK release metadata (T8, and the other change sources).
- Changelog/text parsing.
- Swagger 2.0, OpenAPI 2.0 normalization.
- Multi-file bundles and external `$ref` fetching.
- Semver or version-string comparison: T1 compares *documents*, not versions.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `change-record` | `Change`/`Location`/`DiffResult`, canonical ordering, JSON-safe serialization, `SpecRefusal` code list. No diffing logic. |
| `spec-ingest` | `load()`, YAML/JSON parse, version gate, `$ref` resolution with cycle detection, refusal codes for unparseable/wrong-version/external refs. |
| `diff-core` | The walk: paths → operations → parameters → schemas, emitting the M2 kinds for everything except `renamed`. |
| `rename-inference` | The unambiguous-pairing pass over `removed`+`added` records; the only place `confidence: "inferred"` is produced. |
