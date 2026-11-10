# PRD: Go locator (T11b)

- **Slug:** `locator-go`
- **Capability:** T11 in `docs/technical/CAPABILITY_ROADMAP.md` — **second slice, Go locator**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, second T11 slice
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

Tenon locates Python, TypeScript/JavaScript and Rust call sites. A provider with a Go customer repo
has no way to find the SDK calls a migration must change: `stripe.Charge.New(...)`,
`charge.New(...)`, composite-literal params and field access are invisible to the shipped locators.

T11b adds **`--language go`**: a `GoLocateConfig` (an import root, an optional package-name override
and the shared operation/field mappings), a read-only tree-sitter-go scan that reports rooted hits,
and a wrapper that reuses the shared `derive`/`resolve` certainty policy and the shared
`Site`/`LocateResult` contract. It recognizes package-qualified calls and composite-literal fields,
resolves import aliases and the default package name, and reports the same honest reasons/ambiguity
groups.

No Go toolchain is required to locate. The proof runner is unchanged: a Go repo uses
`--check "go test ./..."` or `go build ./...` like any other command. C# follows as T11c.

The dangerous shortcuts are rejected here: regex guessing, a second certainty policy, treating a
client method chain or a dot import as certain, and letting a Go bundle skip the shared proof/PR
gates.

**For whom:** a provider migrating a Go customer repo, a self-hoster, the reviewer of the diff, and
T11c.

## Goals & Success Metrics

1. **One config.** `GoLocateConfig(import_root, package_name=None, operations, fields)` with a
   validated import path, an optional package identifier and the shared mappings.
2. **A real scan.** tree-sitter-go over `.go` files, import/alias resolution, package-qualified
   calls, composite literals and field access; evidence only, no certainty decisions.
3. **The shared policy.** `derive`/`resolve` decide certain sites and ambiguity groups unchanged.
4. **CLI/config/bundle.** `--language go`, `tenon.toml language = "go"` and a bundle `language: "go"`
   work, including `locate.package_name`; MCP stays Python-only.
5. **Offline tests.** Fixture Go repos, no network, no Go toolchain.
6. **No regressions.** Python/TS/Rust behavior and all prior tests stay green.

## User Personas & Scenarios

- **Provider.** Ships a bundle with `language: "go"`, `sdk_package: "github.com/stripe/stripe-go/v76"`,
  `package_name: "stripe"`, the mappings and `check: ["go", "test", "./..."]`; the Go checkout
  locates the calls and fields.
- **Self-hoster.** Runs `tenon check`/`tenon fix --language go` on a Go repo with `tenon.toml`.
- **Reviewer.** Sees the same proof levels and skipped/ambiguous sites as the other languages.
- **T11c.** Reuses the config/scanner/wrapper pattern.

Scenario: a Go repo imports `github.com/stripe/stripe-go/v76` and
`github.com/stripe/stripe-go/v76/charge`, builds
`params := &stripe.ChargeParams{Amount: stripe.Int64(100)}`, then calls `charge.New(params)`. The
locator reports `charge.New` (chain `charge.New`) and the `Amount` field on the literal; an aliased
import resolves the same way; `client.Charges.New(...)` (a method on a local value) is not certain.

## Requirements

### Must have

- **M1 — Config.** `src/tenon/locate/go_config.py`: `GoLocateConfig(sdk_package: str,
  package_name: str | None = None, operations={}, fields={})`, frozen/slots, mapping proxies.
  - `sdk_package` is a Go import root: non-empty, no whitespace, no leading/trailing `/`, no `::`.
  - `package_name` is optional and, when present, a Go identifier `[A-Za-z_][A-Za-z0-9_]*`.
- **M2 — Scanner.** `src/tenon/locate/go_scan.py`: `scan_go(root, sdk_package, package_name=None) ->
  ScanResult`.
  - Walk `.go` files; skip `vendor`, `.git`, `testdata` and hidden directories.
  - Parse with `tree-sitter-go` (new core dependency); report `Hit`/`Dynamic` evidence only.
  - Imports: a path equal to the root or starting with `root + "/"` roots the package; the canonical
    prefix is the path after the root (`.../v76/charge` -> `("charge",)`). An explicit alias wins;
    otherwise infer the package name (the last segment if a valid non-version identifier; the
    segment before a trailing `vN`; a trailing `-go` stripped; otherwise no default). `package_name`
    overrides the inference for the root import. `_`/`.` imports root no names.
  - Calls: a selector rooted through a package (`stripe.Charge.New(...)`, `charge.New(...)`) is a
    `CALL` hit with the canonical chain and `rooted=True`. A selector on a local value
    (`client.Charges.New(...)`) is a method chain and is not certain.
  - Composite literals: `stripe.ChargeParams{Amount: ...}` or `charge.Params{...}` of a rooted type
    emit `KEYWORD` field hits (the keyed element's key) with the type chain. A literal inline in a
    rooted call, or a local `var`/`:=` binding passed to a rooted call, also emits field hits with
    the call chain. Bindings are tracked per enclosing function; a rebinding replaces the name.
  - Field access (`params.Amount`) through a tracked binding is an `ATTRIBUTE` hit, with the type
    chain and, when passed to a rooted call, the call chain.
  - `modules` contains each file that imports the root.
  - No new `SiteShape`/`LocateReason`/`AmbiguityReason`/`DynamicKind`; dot imports and reflection
    are unseen (no hit).
- **M3 — Wrapper.** `src/tenon/locate/go_locate.py`: `locate_go(change, root, config)` derives the
  query, calls `scan_go`, and applies the shipped `resolve`; no policy copy.
- **M4 — Integration.** `LANGUAGES`/`CliConfig`/`tenon.toml`/`MigrationBundle` accept `go` with named
  errors; `--language go` is a parser choice; `LOCATE_TYPES`/`LOCATORS` include go; `--package-name`
  and `locate.package_name` set the override (Go only); `source=mcp` still requires `python`. The
  `tenon check`/`tenon fix` text/JSON and exit codes are unchanged.
- **M5 — Docs/tests.** README/ARCHITECTURE document `--language go`, the import-root/package config,
  the supported shapes and the limits. Tests: config validation; import/alias/inference; package
  calls; composite literals inline/bound/rebound; field access; component and operation field
  renames; unrooted receiver; unmapped symbol; multiple candidates; a real fixture repo through
  `tenon check --language go`; a Go bundle through `provider migrate`; all prior tests green.
  Offline.
- **M6 — No toolchain.** No `go`/`gofmt` subprocess, no network, no Go proof preset.

### Should have

- **S1 — Deterministic scan.** Files sorted, hits in source order; the JSON envelopes stay
  byte-stable.
- **S2 — Named limits.** A method-chain-only or dot-import site yields `NO_SITES`/an honest reason,
  never a guessed site.
- **S3 — One dependency.** `tree-sitter-go` added to the core dependencies, like the other grammars.

### Nice to have

- **N1 — Method-chain receiver tracking**; a later slice.
- **N2 — C# locator**; T11c.
- **N3 — A Go proof preset**; not needed, the runner takes any command.

## Data Model

```
GoLocateConfig
  sdk_package: str          # import root
  package_name: str | None  # override for the root import's package clause
  operations: Mapping[str, str]
  fields: Mapping[str, str]
```

The scanner reuses `Hit`, `Dynamic`, `ScanResult`; the result is the shared `LocateResult`.

## API Contract

```python
from tenon.locate import GoLocateConfig, locate_go

config = GoLocateConfig(
    sdk_package="github.com/stripe/stripe-go/v76",
    package_name="stripe",
    operations={"POST /v1/charges": "charge.New"},
    fields={"ChargeParams.Amount": "AmountCents"},
)
result = locate_go(change, repo, config)
```

CLI:

```sh
tenon check path/to/go-repo --old old.yaml --new new.yaml \
  --language go --sdk-package github.com/stripe/stripe-go/v76 \
  --package-name stripe \
  --operation "POST /v1/charges=charge.New" \
  --field "ChargeParams.Amount=AmountCents"
```

## Technical Considerations

- **Why tree-sitter-go.** Offline, deterministic and consistent with the TS/Rust scanners; no Go
  toolchain, no subprocess, no build.
- **Why an import root plus subpackages.** Go SDKs span many subpackages; the root plus the relative
  prefix keeps chains stable (`charge.New`, `ChargeParams`) without listing every package.
- **Why an optional package name.** The root import `.../stripe-go/v76` does not spell its package
  clause (`stripe`); an alias or the config resolves it. Subpackages usually infer cleanly.
- **Why package-qualified calls and composite literals.** They are the dominant Go SDK style;
  client method chains need receiver type inference and are honestly out of scope.
- **Why per-function bindings.** Go scopes are function-local; a file-wide map would misattribute a
  binding across functions.
- **Why no new vocabulary.** The shared reasons/ambiguity groups are a contract; a dot import or
  reflection is simply unseen, not a new certainty.

## Risks & Open Questions

- **Method chains and dot imports.** A `client.Charges.New(...)` or `. "sdk"` import is not located;
  the report says no site rather than guessing. A later slice can add receiver tracking.
- **Package-name inference.** A renamed package clause that the heuristic cannot infer needs
  `package_name` or an import alias; otherwise the file is unrooted and reports `NO_SDK_IMPORT`.
- **Shadowing.** A local variable named like the package alias is a documented false positive.
- **Composite data flow.** Only a direct inline literal or a `var`/`:=` binding passed to a rooted
  call is followed; a literal passed through several variables or a function is not attributed.
- **Open question — should `--language go` imply OpenAPI only?** Yes; MCP location stays Python.
- **Open question — should a subpackage import root the whole SDK?** Yes: the root prefix matches
  every subpackage, and the chain keeps the relative subpackage.

## Out of Scope

- C# locator, method-chain receiver tracking, dot-import name resolution, reflection, generics
  inference, `go.mod` parsing.
- A Go proof preset; new proof levels; new ambiguity reasons.
- MCP Go location; a hosted service.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `go-locate` | `GoLocateConfig`, `scan_go`, `locate_go`, the dependency, scanner/wrapper tests. No CLI/config-file/bundle. |
| `go-integration` | `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, `package_name`, docs, CLI/bundle tests. No scanner internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Go repos are invisible to the shipped locators. |
| User understanding | 🟢 | Provider/self-hoster/reviewer/T11c; the import-root scenario is concrete. |
| Success metrics | 🟢 | Config, scan, shared policy, CLI/bundle, offline tests. |
| Scope clarity | 🟢 | Go only; methods/dot imports/reflection excluded and named. |
| Edge cases & risks | 🟡 | Package-name inference and shadowing are real; documented as no-site, not guesses. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses the TS/Rust scanner pattern and the shared policy; one grammar dependency. |
| Go-to-market | 🟢 | A fourth language broadens the provider surface; C# follows. |

**Areas to strengthen before sharing:** Go SDK layouts vary; the import-root/prefix model and the
package-name override are the honest minimum. Method chains are the main gap.

**The question I would want answered before greenlighting this:** *If the customer's SDK is used
through a client value (`client.Charges.New(...)`), does the report lie?* The answer this card
records: no; method calls are not certain, so the site is absent and the report does not claim it.
The provider sees no site and can fall back to manual review; method-chain tracking is a later slice.
