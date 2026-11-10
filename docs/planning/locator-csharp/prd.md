# PRD: C# locator (T11c)

- **Slug:** `locator-csharp`
- **Capability:** T11 in `docs/technical/CAPABILITY_ROADMAP.md` — **third slice, C# locator**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, third T11 slice
- **Status:** implemented 2026-11-11 (`src/tenon/locate/csharp_*.py`, CLI; 2,099 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

Tenon locates Python, TypeScript/JavaScript, Rust and Go call sites. A provider with a C# customer
repo has no way to find the SDK calls a migration must change: `ChargeService.Create(...)`,
object-initializer properties and property access are invisible to the shipped locators.

T11c adds **`--language csharp`**: a `CSharpLocateConfig` (a namespace root plus the shared
operation/field mappings), a read-only tree-sitter-c-sharp scan that reports rooted hits, and a
wrapper that reuses the shared `derive`/`resolve` certainty policy and the shared
`Site`/`LocateResult` contract. It recognizes namespace/using roots, aliases, static and instance
calls on tracked service bindings, object-initializer properties and property access, and reports
the same honest reasons/ambiguity groups.

No .NET toolchain is required to locate. The proof runner is unchanged: a C# repo uses
`--check "dotnet test"` or `dotnet build` like any other command.

The dangerous shortcuts are rejected here: regex guessing, a second certainty policy, treating a
fluent chain or `dynamic` as certain, and letting a C# bundle skip the shared proof/PR gates.

**For whom:** a provider migrating a C# customer repo, a self-hoster, the reviewer of the diff, and
the provider layer.

## Goals & Success Metrics

1. **One config.** `CSharpLocateConfig(namespace_root, operations, fields)` with a validated dotted
   namespace and the shared mappings.
2. **A real scan.** tree-sitter-c-sharp over `.cs` files, `using`/alias resolution, qualified and
   simple type roots, static/instance calls, object initializers and property access; evidence only.
3. **The shared policy.** `derive`/`resolve` decide certain sites and ambiguity groups unchanged.
4. **CLI/config/bundle.** `--language csharp`, `tenon.toml language = "csharp"` and a bundle
   `language: "csharp"` work; MCP stays Python-only.
5. **Offline tests.** Fixture C# repos, no network, no .NET toolchain.
6. **No regressions.** Python/TS/Rust/Go behavior and all prior tests stay green.

## User Personas & Scenarios

- **Provider.** Ships a bundle with `language: "csharp"`, `sdk_package: "Stripe"`, the mappings and
  `check: ["dotnet", "test"]`; the C# checkout locates the calls and fields.
- **Self-hoster.** Runs `tenon check`/`tenon fix --language csharp` on a C# repo with `tenon.toml`.
- **Reviewer.** Sees the same proof levels and skipped/ambiguous sites as the other languages.
- **Provider layer.** C# bundles work through `provider migrate` like the other languages.

Scenario: a C# repo imports `using Stripe;` and `using Stripe.Services;`, builds
`var options = new ChargeCreateOptions { AmountCents = 100, Currency = "usd" };`, creates
`var service = new ChargeService();`, then calls `service.Create(options)`. The locator reports the
`service.Create` call (chain `ChargeService.Create`) and the `AmountCents` initializer property; an
alias (`using Charge = Stripe.Charge;`) resolves the same way; `client.Charges.Create(...)` (a
fluent property chain) is not certain.

## Requirements

### Must have

- **M1 — Config.** `src/tenon/locate/csharp_config.py`: `CSharpLocateConfig(sdk_package: str,
  operations={}, fields={})`, frozen/slots, mapping proxies. `sdk_package` is a namespace root
  `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`; a blank/path/`::` is a named `ValueError`.
- **M2 — Scanner.** `src/tenon/locate/csharp_scan.py`: `scan_csharp(root, sdk_package) ->
  ScanResult`.
  - Walk `.cs` files; skip `bin`, `obj`, `.git` and hidden directories.
  - Parse with `tree-sitter-c-sharp` (new core dependency); report `Hit`/`Dynamic` evidence only.
  - Usings: `using <root>;`, `using <root>.<sub>;` and `global using` root the namespace; an alias
    (`using Charge = <root>.Charge;`) roots the alias to the simple type name; `using static` roots
    no type names (documented). A file with a root using is a module.
  - Type roots: a fully qualified `<root>[.<sub>].Type` and a simple `Type` used while a root using
    is in scope are rooted; the canonical chain drops the namespace root and subnamespaces and keeps
    the simple type name (`Stripe.Services.ChargeService` -> `ChargeService`). A local type with the
    same simple name is a documented false positive.
  - Calls: a member call on a rooted type (`ChargeService.Create(...)`) or on a tracked binding
    initialized with `new <rooted type>(...)` (`var service = new ChargeService(); service.Create`)
    is a `CALL` hit with the canonical chain and `rooted=True`. A fluent/property chain on an
    untracked value (`client.Charges.Create(...)`) is not certain.
  - Object initializers: `new <rooted type> { Property = value }` emits `KEYWORD` hits for the
    property names with the type chain. An initializer bound to a local and passed to a rooted call
    also emits the properties with the call chain. Bindings are tracked per method/constructor/
    accessor/local function; a rebinding replaces the name.
  - Property access (`options.AmountCents`) through a tracked binding is an `ATTRIBUTE` hit, with the
    type chain and, when passed to a rooted call, the call chain.
  - `modules` contains each file with a root using or a rooted qualified type.
  - No new `SiteShape`/`LocateReason`/`AmbiguityReason`/`DynamicKind`; `dynamic`, reflection and
    `using static` are unseen (no hit).
- **M3 — Wrapper.** `src/tenon/locate/csharp_locate.py`: `locate_csharp(change, root, config)`
  derives the query, calls `scan_csharp`, and applies the shipped `resolve`; no policy copy.
- **M4 — Integration.** `LANGUAGES`/`CliConfig`/`tenon.toml`/`MigrationBundle` accept `csharp` with
  named errors; `--language csharp` is a parser choice; `LOCATE_TYPES`/`LOCATORS` include csharp;
  `source=mcp` still requires `python`. The `tenon check`/`tenon fix` text/JSON and exit codes are
  unchanged.
- **M5 — Docs/tests.** README/ARCHITECTURE document `--language csharp`, the namespace/mapping
  config, the supported shapes and the limits. Tests: config validation; using/alias/qualified/
  simple type roots; static and tracked-instance calls; object initializers inline/bound/rebound;
  property access; component and operation field renames; unrooted fluent chain; unmapped symbol;
  multiple candidates; a real fixture repo through `tenon check --language csharp`; a C# bundle
  through `provider migrate`; all prior tests green. Offline.
- **M6 — No toolchain.** No `dotnet`/`csc` subprocess, no network, no .NET proof preset.

### Should have

- **S1 — Deterministic scan.** Files sorted, hits in source order; the JSON envelopes stay
  byte-stable.
- **S2 — Named limits.** A fluent-chain-only or `using static` site yields `NO_SITES`/an honest
  reason, never a guessed site.
- **S3 — One dependency.** `tree-sitter-c-sharp` added to the core dependencies.

### Nice to have

- **N1 — Fluent-chain receiver tracking**; a later slice.
- **N2 — `using static` member resolution**; a later slice.
- **N3 — A .NET proof preset**; not needed, the runner takes any command.

## Data Model

```
CSharpLocateConfig
  sdk_package: str          # namespace root, e.g. "Stripe"
  operations: Mapping[str, str]
  fields: Mapping[str, str]
```

The scanner reuses `Hit`, `Dynamic`, `ScanResult`; the result is the shared `LocateResult`.

## API Contract

```python
from tenon.locate import CSharpLocateConfig, locate_csharp

config = CSharpLocateConfig(
    sdk_package="Stripe",
    operations={"POST /v1/charges": "ChargeService.Create"},
    fields={"ChargeCreateOptions.AmountCents": "AmountCents"},
)
result = locate_csharp(change, repo, config)
```

CLI:

```sh
tenon check path/to/csharp-repo --old old.yaml --new new.yaml \
  --language csharp --sdk-package Stripe \
  --operation "POST /v1/charges=ChargeService.Create" \
  --field "ChargeCreateOptions.AmountCents=AmountCents"
```

## Technical Considerations

- **Why tree-sitter-c-sharp.** Offline, deterministic and consistent with the other scanners; no
  .NET SDK, no subprocess, no build.
- **Why a namespace root plus simple type names.** C# `using` brings type names into scope; the
  canonical chain `ChargeService.Create` is stable whether the code writes a using or a fully
  qualified name. Subnamespaces are organizational and dropped; a same-name collision is documented.
- **Why track `new` bindings.** The dominant SDK style is `var service = new ChargeService();
  service.Create(...)`; the `new` gives the type explicitly, so rooting it is evidence, not a guess.
- **Why object initializers.** C# params are properties set in an initializer; property renames are
  the common migration. Inline and simple `var` bindings cover the dominant style without type
  inference.
- **Why per-member bindings.** C# scopes are method-local; a file-wide map would misattribute a
  binding across methods.
- **Why no new vocabulary.** The shared reasons/ambiguity groups are a contract; a fluent chain or
  `dynamic` is simply unseen, not a new certainty.

## Risks & Open Questions

- **Fluent chains and `dynamic`.** A `client.Charges.Create(...)` or `dynamic` call is not located;
  the report says no site rather than guessing. A later slice can add receiver tracking.
- **Simple-name collisions.** A local type named like an imported SDK type is a documented false
  positive; the provider can use a fully qualified mapping or an alias.
- **Partial classes / generated code.** The scanner reads every `.cs` file, including generated
  `obj` content? No: `obj`/`bin` are skipped; source-generated files inside the tree are read.
- **Object-initializer data flow.** Only a direct inline initializer or a simple local binding
  passed to a rooted call is followed; a multi-hop or factory-created object is not attributed.
- **Open question — should `--language csharp` imply OpenAPI only?** Yes; MCP location stays Python.
- **Open question — should a subnamespace using root the type?** Yes: the namespace prefix matches
  and the chain keeps only the simple type name.

## Out of Scope

- Fluent-chain receiver tracking, `using static` resolution, reflection, `dynamic`, generics
  inference, `csproj` parsing.
- A .NET proof preset; new proof levels; new ambiguity reasons.
- MCP C# location; a hosted service.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `csharp-locate` | `CSharpLocateConfig`, `scan_csharp`, `locate_csharp`, the dependency, scanner/wrapper tests. No CLI/config-file/bundle. |
| `csharp-integration` | `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, docs, CLI/bundle tests. No scanner internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | C# repos are invisible to the shipped locators. |
| User understanding | 🟢 | Provider/self-hoster/reviewer; the using/initializer scenario is concrete. |
| Success metrics | 🟢 | Config, scan, shared policy, CLI/bundle, offline tests. |
| Scope clarity | 🟢 | C# only; fluent chains/dynamic/using static excluded and named. |
| Edge cases & risks | 🟡 | Simple-name collisions and fluent chains are real; documented as no-site, not guesses. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses the TS/Rust/Go scanner pattern and the shared policy; one grammar dependency. |
| Go-to-market | 🟢 | Completes the four-language locator set; the provider layer covers all of them. |

**Areas to strengthen before sharing:** C# SDK layouts vary; the namespace-root/simple-type model
and the `new` binding are the honest minimum. Fluent chains are the main gap.

**The question I would want answered before greenlighting this:** *If the customer's SDK is used
through a fluent client (`client.Charges.Create(...)`), does the report lie?* The answer this card
records: no; fluent calls are not certain, so the site is absent and the report does not claim it.
The provider sees no site and can fall back to manual review; receiver tracking is a later slice.
