# PRD: Provider migration bundle (T10b)

- **Slug:** `provider-bundle`
- **Capability:** T10 in `docs/technical/CAPABILITY_ROADMAP.md` — **second slice, provider migration bundle**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, second slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T10a gives the hosted writer an app identity. A provider still has no portable way to describe a
migration: which vendor and release, which OpenAPI/MCP documents, how the vendor's operations and
fields map to the customer's SDK, and what proof level the customer's repo must reach. Today every
customer run re-specifies all of it by hand or with a repo-specific `tenon.toml`.

T10b adds a **migration bundle** (JSON) and `tenon provider migrate <repo> --bundle PATH`: the bundle
carries the identity, source/language, spec paths, locate config, proof requirement and stage
commands; the command runs the shipped detect → locate → propose → prove pipeline on one target repo,
prints a provider report, and with `--open-pr` opens the PR through `gh` or the T10a app remote.

One repo per invocation. Multi-repo/installed fan-out, webhooks, a database and the hosted service
are T10c. The bundle is the portable artifact a provider can hand to a customer or a self-hoster.

The dangerous shortcuts are rejected here: trusting an unvalidated bundle, letting the bundle
upgrade a proof level, letting a provider run merge/push the default branch, and treating a bundle's
`require` as proof that the requirement was met.

**For whom:** a provider packaging a migration, a self-hoster running it for a customer, the customer
reviewing the PR, and T10c's fan-out/hosted layer.

## Goals & Success Metrics

1. **One portable bundle.** A JSON file with provider/migration, source/language, old/new spec paths
   (relative to the bundle), locate config, proof requirement and stage commands; validated with
   named errors.
2. **One command.** `tenon provider migrate <repo> --bundle PATH [--open-pr] [--remote gh|app]
   [--json]` runs the same pipeline and exit codes as `fix`.
3. **Same guardrails.** T5's clone/commit/push/PR, dirty-tree/default-branch/branch-exists refusals,
   required-level gate and no-merge stance are unchanged.
4. **Provider report.** Text and a provider JSON envelope (`provider`, `migration`, `repo`,
   `results`, `summary`); the proof levels are the shipped ones, never upgraded.
5. **App or gh.** `--open-pr` reuses T5/T10a; the app flags/env are the same as `fix`.
6. **Offline tests.** Fixture bundles/specs/repos; no network or live GitHub.

## User Personas & Scenarios

- **Provider.** Writes `stripe-v2500-v2596.json` with the two specs, the locate mapping, the required
  proof and the check command; ships it with the specs.
- **Self-hoster.** Runs `tenon provider migrate customer-repo --bundle ... --open-pr --remote app`;
  the app opens the PR under its installation.
- **Customer/reviewer.** Sees the normal T5 PR (no provider branding in this slice) with the stated
  proof level and the skipped sites.
- **T10c.** Reuses the bundle schema for fan-out over installed repos.

Scenario: the M0.3 Stripe rename. The bundle names `stripe`, the v2500/v2596 files, the
`POST /v1/checkout/sessions = checkout.Session.create` mapping, `TESTS_PASSED` and the focused test.
The command runs on the FHI checkout, prints the three-edit diff and `TESTS_PASSED`, and with
`--open-pr` opens the app PR.

## Requirements

### Must have

- **M1 — Bundle schema.** JSON with:
  - `provider`, `migration`: non-empty strings;
  - `source`: `openapi` or `mcp`; `language`: `python` or `ts`; `source=mcp` requires `python`;
  - `old`, `new`: non-empty paths resolved relative to the bundle file; both must be readable;
  - `locate`: an object with `sdk_package` (required) and optional `operations`/`fields` string
    mappings; the config type follows `source`/`language`;
  - `require`: one of the five proof levels (default `TESTS_PASSED`);
  - `check`, `build`, `characterize`, `replay`: optional arrays of non-empty strings;
  - `breaking_only`: optional bool (default false);
  - unknown keys ignored; `description`/`provider_url` allowed and ignored in this slice.
- **M2 — Loader.** `load_bundle(path) -> MigrationBundle`: a bad JSON, a missing/blank key, a bad
  source/language/require, a non-array command, a non-object locate, a non-string mapping, a missing
  spec file or an unsupported `mcp`+`ts` combination is a `ValueError` naming the bundle/key (CLI exit
  2). No partial bundle.
- **M3 — CLI.** `tenon provider migrate <repo> --bundle PATH [--open-pr] [--remote gh|app] [--app-id
  ID] [--app-installation-id ID] [--app-private-key PATH] [--api-url URL] [--check CMD]
  [--require LEVEL] [--allow-below-required] [--allow-unverified] [--json]`.
  `--check`/`--require` override the bundle; the other app/remote flags are the T10a ones.
  `--remote` requires `--open-pr`.
- **M4 — Run.** Build the `CliConfig` from the bundle (locate/commands/require/source/language/
  breaking_only), apply the `--check`/`--require` overrides, and run the same fix pipeline
  (`_diff_and_filter` → `_locate` → `propose` → `prove_plan` → optional `write_pr`). The exit code is
  `fix_exit`; a required level not reached is exit 1 and the PR gate is T5's.
- **M5 — Report.** Text: a `provider`/`migration` header then the fix report. JSON:
  `{"command":"provider","provider":...,"migration":...,"repo":...,"results":[<fix result
  items>],"summary":<fix summary>}`; byte-stable. The results/summary reuse the shipped fix items.
- **M6 — Guardrails/errors.** No merge/default-branch/force; the bundle never changes the proof
  level; a bad bundle/spec/usage is exit 2 with a named message and a `--json` error object; no
  traceback.
- **M7 — Docs/tests.** The bundle format, the command, the one-repo scope and the T10c deferral are
  documented. Tests: the loader/validation, a real fixture repo+bundle through the CLI, the
  `--json` envelope, `--open-pr` with a fake remote, the overrides, the errors, and the existing
  commands green. Offline.
- **M8 — No service.** No database, webhook, installation discovery, multi-repo fan-out or hosted
  deployment in this slice.

### Should have

- **S1 — `--check`/`--require` overrides** for a customer-specific command or a stricter level.
- **S2 — Relative spec paths** make the bundle directory portable.
- **S3 — The bundle's `breaking_only`** maps to the config filter.

### Nice to have

- **N1 — Provider note in the PR body**; needs a `write_pr` extension, a later card.
- **N2 — Multi-repo/installed fan-out**; T10c.
- **N3 — Bundle signing/provenance**; a later security card.

## Data Model

```
MigrationBundle
  provider: str
  migration: str
  source: Literal["openapi", "mcp"]
  language: Literal["python", "ts"]
  old: Path                 # resolved relative to the bundle
  new: Path
  locate: LocateConfig | TsLocateConfig | McpLocateConfig
  command/build/characterize/replay: tuple[str, ...]
  require: ProofLevel = TESTS_PASSED
  breaking_only: bool = False
```

The bundle maps to the shipped `CliConfig`; no new pipeline type. The provider JSON envelope wraps
the shipped fix result items.

## API Contract

```python
from tenon.provider import MigrationBundle, load_bundle

bundle = load_bundle("stripe-v2500-v2596.json")
bundle.provider      # "stripe"
bundle.migration     # "v2500-v2596-payment-method-types"
bundle.old/new       # resolved paths
bundle.locate        # LocateConfig(...)
```

CLI:

```sh
tenon provider migrate path/to/customer-repo \
  --bundle stripe-v2500-v2596.json \
  --open-pr --remote app \
  --app-id 123 --app-installation-id 456 --app-private-key app.pem
```

No service, no fan-out, no PR branding.

## Technical Considerations

- **Why a bundle, not a new config file.** `tenon.toml` is repo-specific and lives in the customer
  repo; a provider needs a portable artifact with the specs and the mapping. JSON is easy to ship,
  validate and later sign.
- **Why reuse `CliConfig`.** The pipeline is already configured by `CliConfig`; the bundle is a
  serialized provider-side config. The command only loads it and runs the same functions.
- **Why relative paths.** The provider ships a directory (bundle + specs); resolving against the
  bundle file makes it relocatable. The customer's repo is the positional argument, not a bundle
  path.
- **Why one repo.** Fan-out needs orchestration, partial-failure reporting, installation discovery
  and a service; T10c. One repo per run is the smallest complete provider flow.
- **Why no PR branding.** The T5 title/body are deterministic and already carry the proof level; a
  provider line is a `write_pr` contract change with new tests. The bundle/report carry the identity
  now; T10c can add the PR note.
- **Why the app remote is optional.** A provider/self-hoster can use `gh` for a local trial; the app
  is the hosted path. Both share T5's guardrails.
- **Trust boundary.** The bundle is user/provider input; every key is validated, the spec files are
  read through the shipped loaders, and the proof requirement is a `ProofLevel` enum. No code is
  executed from the bundle except the stage commands the operator explicitly chose.

## Risks & Open Questions

- **Untrusted bundle.** A bundle can point at arbitrary local spec paths and commands; the operator
  chose to run it. Validation names bad keys; it is not a sandbox.
- **Proof requirement is not proof.** `require: TESTS_PASSED` is the bar; `fix_exit` and the PR gate
  decide whether it was met. The bundle never upgrades a level.
- **Spec path portability.** A bundle that references `../` or absolute paths still works; a
  provider shipping a directory should keep the specs inside it. A future `--bundle-dir` can enforce.
- **Provider branding.** Reviewers see a normal Tenon PR; the provider identity is in the report,
  not the PR. T10c can add a body note.
- **Fan-out.** A provider with 50 customers must run 50 invocations or wait for T10c; the bundle
  schema is the shared input.
- **Open question — should the bundle embed the specs?** No in this card; paths keep the artifact
  small and diffable. A signed archive is a later security card.
- **Open question — should `provider migrate` support `--repo` repeated?** Not now; T10c.

## Out of Scope

- Multi-repo/installed fan-out, webhooks, installation discovery, a database, a hosted service.
- Provider branding in the PR body.
- Bundle signing/provenance, remote spec URLs, archive formats.
- T11 languages; new proof levels; new proposer rules.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `provider-bundle` | `MigrationBundle`, `load_bundle`, validation, relative path resolution, the `CliConfig` mapping. No CLI/pipeline. |
| `provider-cli` | `tenon provider migrate`, the fix-flow reuse/refactor, provider text/JSON envelope, overrides/errors, docs/tests. No new pipeline. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | A provider has no portable migration artifact; every run is hand-configured. |
| User understanding | 🟢 | Provider/self-hoster/customer/T10c scenarios; the bundle is concrete. |
| Success metrics | 🟢 | Schema/loader, one command, same guardrails, provider envelope, offline tests. |
| Scope clarity | 🟢 | One repo; fan-out/hosted/branding excluded. |
| Edge cases & risks | 🟡 | The bundle is untrusted input and the proof requirement is not proof; documented. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses `CliConfig`, the pipeline and the T10a remote; stdlib JSON. |
| Go-to-market | 🟢 | The portable artifact a provider can ship to customers; T10c is the fan-out. |

**Areas to strengthen before sharing:** the bundle does not sign or prove provenance; a provider can
ship any spec/command. The operator runs it knowingly. A later security card can add signing.

**The question I would want answered before greenlighting this:** *If a provider ships a bundle with
`require: TYPES_BUILD_ONLY` and a trivial build command, the PR says `[TYPES_BUILD_ONLY]` and the
customer may accept a weak fix. What stops that?* The answer this card records: the customer's
`--require` override can raise the bar, the PR states the level, and the bundle never upgrades it.
The provider chooses its bar; the customer can choose a higher one.
