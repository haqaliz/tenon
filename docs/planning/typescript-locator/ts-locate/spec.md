# Spec: `ts-locate` (T6)

- **Feature:** `typescript-locator`
- **PRD:** `docs/planning/typescript-locator/prd.md` (§ M1, M2, M10–M11)
- **Boundary:** config, query reuse, the `locate_ts` wrapper, fixtures and the decoy. No new scanner,
  no CLI.

## Problem slice

The scanner produces evidence; the shipped resolver decides certainty. This aspect is the seam that
lets a TS repository use that resolver without forking it, and the contract tests that prove the
result matches T2.

## In-scope requirements

- `TsLocateConfig`: `sdk_package: str`, `operations: Mapping[str, str]`, `fields: Mapping[str, str]`.
  Frozen, slots. Validate the package as an npm name: non-empty, no whitespace, optional
  `@scope/`, letters/digits/`.`/`-`/`_`; a subpath belongs in the import, not the config.
- `QueryConfig` Protocol in `query.py` with `operations` and `fields`. Change the type hints of
  `derive`, `_mapped_operation` and `_mapped_field` to `QueryConfig`; no behaviour change. Change
  `resolve`'s unused `config` hint to `QueryConfig` (or `object`) so both configs fit.
- `locate_ts(change, root, config) -> LocateResult`: `derive(change, config)`; if it carries a
  reason, return an empty result with that reason; otherwise
  `resolve(change, query, scan_ts(root, config.sdk_package), config)`.
- Export `TsLocateConfig` and `locate_ts` from `tenon.locate`.
- Fixtures:
  - `ts-sdk-basic`: ESM `.ts`, `new Stripe()`, object key + quoted key.
  - `ts-cjs`: `.cjs` with `require`.
  - `ts-js`: `.js`/`.mjs` call sites.
  - `ts-tsx`: `.tsx` call/object sites; no JSX props.
  - `ts-decoy`: a reachable SDK module plus an unrelated `{ amount: 1 }` module; no certain decoy.
  - `ts-alias`: one-hop certain and two-hop `ALIAS_CHAIN`.
  - `ts-dynamic`: object variable, spread, computed member/key, dynamic import.
  - `ts-no-sdk`: no import → `NO_SDK_IMPORT`.
- The test `Change` records use the same T1 `diff(parse(...))` path as the Python locator; no
  hand-written `Change` unless a kind needs it.

## Out-of-scope

- The scanner internals (`ts-scan`), CLI (`ts-cli`).
- New `SiteShape`, `AmbiguityReason`, `LocateReason` values.
- Type inference, tsconfig aliases, JSX props.

## Acceptance criteria

- **AC1 — Config.** A valid npm name (including `@scope/pkg`) constructs; an empty, whitespace or
  path-like package raises `ValueError`; mappings are immutable copies.
- **AC2 — Parity.** A `renamed` field on the basic fixture returns the expected certain `Site`s with
  path/line/column/shape/symbol; the same `Change` on the Python path is unaffected.
- **AC3 — Decoy.** The unrelated `{ amount: 1 }` is never certain; a reachable non-SDK receiver
  appears only as an `UNROOTED_RECEIVER` candidate.
- **AC4 — Operation scope.** A mapped operation resolves the rooted call chain; two candidates yield
  `MULTIPLE_CANDIDATES`; an unmapped operation yields `OPERATION_NOT_MAPPED`.
- **AC5 — Dynamics.** Object variable/spread → `DYNAMIC_KWARGS`; computed member → `DYNAMIC_GETATTR`;
  multi-hop → `ALIAS_CHAIN`; each group carries its candidates.
- **AC6 — Non-results.** No SDK import → `NO_SDK_IMPORT`; no matching site → `NO_SITES`; an
  unsupported kind → `UNSUPPORTED_CHANGE_KIND`.
- **AC7 — Determinism.** `to_json()` is byte-identical across runs and hash seeds; sites are ordered.
- **AC8 — No new vocabulary.** The shipped enums are unchanged; a test pins their values.

## Dependencies and sequencing

- Depends on `ts-scan`, the shipped `query.derive` and `resolve`.
- Before `ts-cli`.
- The `QueryConfig` refactor must keep all 870 Python tests green.

## Open questions / risks

- `resolve` currently takes an unused `LocateConfig`; the Protocol hint is the only change. If a type
  checker is added later, both configs must satisfy it.
- A `Change` with a component-scoped field and no operation relies on `UNMAPPED_SYMBOL`; the TS
  fixture covers it.
