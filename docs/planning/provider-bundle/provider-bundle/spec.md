# Spec: `provider-bundle` (T10b)

- **Feature:** `provider-bundle`
- **PRD:** `docs/planning/provider-bundle/prd.md` (§ M1, M2)
- **Boundary:** the bundle type and loader. No CLI/pipeline.

## Problem slice

A provider needs a portable, validated description of a migration before any repo is touched. This
aspect defines the schema, resolves the relative spec paths and maps the locate section to the
shipped config types.

## In-scope requirements

- `src/tenon/provider/bundle.py`:
  - `MigrationBundle(provider, migration, source, language, old, new, locate, command, build,
    characterize, replay, require, breaking_only)`; frozen, slots.
  - `load_bundle(path) -> MigrationBundle`; JSON only.
- Schema:
  - `provider`/`migration` non-empty strings;
  - `source` `openapi|mcp`, `language` `python|ts`; `source=mcp` requires `python`;
  - `old`/`new` non-empty strings, resolved against the bundle's parent, and both readable;
  - `locate` an object with `sdk_package` (required) and optional `operations`/`fields` string
    mappings; the config type is `LocateConfig` (openapi/python), `TsLocateConfig` (openapi/ts) or
    `McpLocateConfig` (mcp);
  - `require` one of the five `ProofLevel`s (default `TESTS_PASSED`);
  - `check`/`build`/`characterize`/`replay` optional arrays of non-empty strings (a bare string is an
    error);
  - `breaking_only` optional bool (default false);
  - unknown keys ignored; `description`/`provider_url` allowed and ignored.
- Every invalid case is a `ValueError` naming the bundle path and the key; a missing/unreadable file
  is named; no partial bundle.
- Export `MigrationBundle`/`load_bundle` from `tenon.provider`.

## Out-of-scope

- The CLI, pipeline, PR/remote.
- Signing/provenance, remote spec URLs, archives.
- `CliConfig` (the CLI maps the bundle to it).

## Acceptance criteria

- **AC1 — Valid.** A full bundle loads; the fields/commands/require/breaking_only are as given; the
  locate config is the right type.
- **AC2 — Paths.** `old`/`new` resolve relative to the bundle's directory; an absolute path works; a
  missing file is an error.
- **AC3 — Matrix.** `mcp` + `ts` is an error; an unknown source/language is an error.
- **AC4 — Validation.** A missing/blank provider/migration/locate/sdk_package, a non-object locate, a
  non-string mapping, a bad require, a non-array command, an empty command element and a non-bool
  breaking_only each raise a `ValueError` naming the key.
- **AC5 — JSON.** A malformed/empty JSON is a `ValueError`; unknown/description keys are ignored.
- **AC6 — Determinism.** The same bundle loads identically; no clock/network.

## Dependencies and sequencing

- First; `provider-cli` consumes it.
- Reuses `LocateConfig`/`TsLocateConfig`/`McpLocateConfig` and `ProofLevel`.

## Open questions / risks

- A bundle can point outside its directory; this card allows it (local operator input). A later
  security card can enforce a bundle dir/signature.
- The locate `operations`/`fields` keys are strings; the config validates the package.
