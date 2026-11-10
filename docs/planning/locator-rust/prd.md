# PRD: Rust locator (T11a)

- **Slug:** `locator-rust`
- **Capability:** T11 in `docs/technical/CAPABILITY_ROADMAP.md` — **first slice, Rust locator**
- **Milestone:** Phase 3 in `docs/ROADMAP.md`, first T11 slice
- **Status:** implemented 2026-11-10 (`src/tenon/locate/rust_*.py`, CLI; 1,925 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

Tenon locates Python and TypeScript/JavaScript call sites. A provider with a Rust customer repo has
no way to find the SDK calls a migration must change: `Charge::create(...)`, imported aliases,
struct-literal params and field access are invisible to the shipped locators.

T11a adds **`--language rust`**: a `RustLocateConfig` (crate identifier plus the shared operation and
field mappings), a read-only tree-sitter-rust scan that reports rooted hits and dynamics, and a
wrapper that reuses the shared `derive`/`resolve` certainty policy and the shared `Site`/`LocateResult`
contract. It recognizes crate-rooted associated calls and struct-literal fields, resolves `use`
aliases, and reports the same honest reasons/ambiguity groups.

No Rust toolchain is required to locate. The proof runner is unchanged: a Rust repo uses
`--check "cargo test"` or `cargo check` like any other command. Go and C# follow as T11b/T11c.

The dangerous shortcuts are rejected here: regex guessing, a second certainty policy, treating a
macro or a method chain as certain, and letting a Rust bundle skip the shared proof/PR gates.

**For whom:** a provider migrating a Rust customer repo, a self-hoster, the reviewer of the diff, and
T11b/T11c.

## Goals & Success Metrics

1. **One config.** `RustLocateConfig(crate, operations, fields)` with the shared mapping shape and a
   validated crate identifier.
2. **A real scan.** tree-sitter-rust over `.rs` files, `use`/alias resolution, associated calls,
   struct literals and field access; evidence only, no certainty decisions.
3. **The shared policy.** `derive`/`resolve` decide certain sites and ambiguity groups unchanged.
4. **CLI/config/bundle.** `--language rust`, `tenon.toml language = "rust"` and a bundle
   `language: "rust"` work; MCP stays Python-only.
5. **Offline tests.** Fixture Rust repos, no network, no Rust toolchain.
6. **No regressions.** Python/TS behavior and all prior tests stay green.

## User Personas & Scenarios

- **Provider.** Ships a bundle with `language: "rust"`, `sdk_package: "stripe"`, the operation and
  field mappings, and `check: ["cargo", "test"]`; the Rust checkout locates the calls and fields.
- **Self-hoster.** Runs `tenon check`/`tenon fix --language rust` on a Rust repo with `tenon.toml`.
- **Reviewer.** Sees the same proof levels and skipped/ambiguous sites as the other languages.
- **T11b/T11c.** Reuse the config/scanner/wrapper pattern.

Scenario: a Rust repo imports `use stripe::{Charge, CreateCharge};`, builds
`let params = CreateCharge { amount: 100, ..Default::default() };`, then calls
`Charge::create(&params, &client).await`. The locator reports the `Charge::create` call and the
`amount` struct field on the same chain; an aliased `StripeCharge::create` resolves to the same
canonical chain; a local `charge.create(...)` method call is not certain.

## Requirements

### Must have

- **M1 — Config.** `src/tenon/locate/rust_config.py`: `RustLocateConfig(sdk_package: str,
  operations: Mapping[str,str] = {}, fields: Mapping[str,str] = {})`, frozen/slots, mapping proxies.
  `sdk_package` is a single Rust crate identifier (`[A-Za-z_][A-Za-z0-9_]*`, e.g. `stripe`,
  `async_stripe`); a path/`::`/blank is a named `ValueError`.
- **M2 — Scanner.** `src/tenon/locate/rust_scan.py`: `scan_rust(root, sdk_package) -> ScanResult`.
  - Walk `.rs` files; skip `target`, `vendor`, `.git` and hidden directories.
  - Parse with `tree-sitter-rust` (new core dependency); report `Hit`/`Dynamic` evidence only.
  - Rooting: a `use <crate>::...` declaration (simple, grouped, nested groups, `as` aliases, crate
    aliases and globs) and a path whose first segment is the crate identifier; aliases resolve to the
    canonical chain after the crate root (`use stripe::resources::Charge;` -> `resources.Charge`).
  - Calls: associated/path calls (`Charge::create(...)`, `stripe::Charge::create(...)`,
    `StripeCharge::create(...)`) are `CALL` hits with the canonical chain and `rooted=True`.
    Method calls (`client.charge(...)`) are not certain in this slice.
  - Struct literals: `Type { field: value, ..Default::default() }` of a rooted type emits `KEYWORD`
    field hits. A literal inline in a rooted call, or a local `let` binding to one passed to a rooted
    call, attributes its fields to the call chain, so operation-scope field renames are certain.
    A standalone literal keeps the type chain for component-scope fields. Bindings are tracked per
    enclosing function; a rebinding replaces the name.
  - Field access (`params.amount`) through a tracked struct binding is an `ATTRIBUTE` hit, with the
    type chain and, when the binding is passed to a rooted call, the call chain.
  - `use ...::*;` does not root individual names; paths through the crate root still do.
  - No new `SiteShape`, `LocateReason`, `AmbiguityReason` or `DynamicKind`; macro-generated calls are
    not seen (documented).
- **M3 — Wrapper.** `src/tenon/locate/rust_locate.py`: `locate_rust(change, root, config)` derives
  the query, calls `scan_rust`, and applies the shipped `resolve`; no policy copy.
- **M4 — Integration.** `LANGUAGES`/`CliConfig`/`tenon.toml`/`MigrationBundle` accept `rust` with
  named errors; `--language rust` is a parser choice; `_locate` and the config/bundle locate-type
  dispatch use one table for python/ts/rust; `source=mcp` still requires `python`. The `tenon check`
  and `tenon fix` text/JSON and exit codes are unchanged.
- **M5 — Docs/tests.** README/ARCHITECTURE document `--language rust`, the crate/mapping config, the
  supported shapes and the limits. Tests: config validation; scanner rooting/aliases/grouped imports;
  associated calls; inline and bound struct literals; field access; component and operation field
  renames; unrooted receiver; unmapped symbol; multiple candidates; a real fixture repo through
  `tenon check --language rust`; a Rust bundle through `provider migrate`; all prior tests green.
  Offline.
- **M6 — No toolchain.** No `cargo`/`rustc` subprocess, no network, no Cargo proof preset.

### Should have

- **S1 — Deterministic scan.** Files sorted, hits in source order; the JSON envelopes stay
  byte-stable.
- **S2 — Named limits.** A macro or method-chain-only site yields `NO_SITES`/an honest reason, never
  a guessed site.
- **S3 — One dependency.** `tree-sitter-rust` added to the core dependencies, like the TS grammars.

### Nice to have

- **N1 — Method-chain receiver tracking**; a later slice.
- **N2 — Go and C# locators**; T11b/T11c.
- **N3 — A Cargo proof preset**; not needed, the runner takes any command.

## Data Model

```
RustLocateConfig
  sdk_package: str          # crate identifier as written in `use`
  operations: Mapping[str, str]
  fields: Mapping[str, str]
```

The scanner reuses `Hit`, `Dynamic`, `ScanResult`; the result is the shared `LocateResult`.

## API Contract

```python
from tenon.locate import RustLocateConfig, locate_rust

config = RustLocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/charges": "Charge.create"},
    fields={"Charge.amount": "amount_cents"},
)
result = locate_rust(change, repo, config)
```

CLI:

```sh
tenon check path/to/rust-repo --old old.yaml --new new.yaml \
  --language rust --sdk-package stripe \
  --operation "POST /v1/charges=Charge.create" \
  --field "Charge.amount=amount_cents"
```

## Technical Considerations

- **Why tree-sitter-rust.** It is offline, deterministic and matches the shipped TS approach; no
  Rust toolchain, no subprocess, no build.
- **Why reuse `derive`/`resolve`.** The mapping and certainty rules are language-independent; a
  second policy would drift and could upgrade a guess.
- **Why associated functions.** Rust SDKs overwhelmingly call associated functions on imported types;
  method chains need receiver type inference and are honestly out of scope.
- **Why struct literals.** Rust params are structs; field renames are the common migration. Inline
  literals and simple `let` bindings cover the dominant SDK style without type inference.
- **Why per-function bindings.** Rust scopes and shadowing are function-local; a file-wide map would
  misattribute a binding across functions.
- **Why no new vocabulary.** The shared reasons/ambiguity groups are a contract; a macro is simply
  unseen, not a new certainty.

## Risks & Open Questions

- **Macros and builders.** A macro-generated call or a pure builder chain is not located; the report
  says no site rather than guessing. A later slice can add method-chain tracking.
- **Re-exports.** `use my_sdk::stripe::Charge` (a wrapper crate re-exporting the vendor SDK) is not
  followed; the config must name the crate the code actually imports. Documented.
- **Crate aliases in Cargo.toml.** A renamed dependency (`stripe = { package = "async-stripe" }`) is
  not read; the config uses the name in `use`.
- **Struct data flow.** Only a direct `let` binding and inline args are followed; a struct passed
  through several variables or a function is not attributed.
- **Open question — should `--language rust` imply OpenAPI only?** Yes; MCP location stays Python, as
  for TS.
- **Open question — should a bare `stripe::...` path root without a `use`?** Yes: Rust 2018 puts
  extern crates in scope, so the crate name is evidence. A local module with the same name is a
  documented false-positive risk.

## Out of Scope

- Go/C# locators, method-chain receiver tracking, macro expansion, re-export following, Cargo.toml
  parsing.
- A Cargo proof preset; new proof levels; new ambiguity reasons.
- MCP Rust location; a hosted service.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `rust-locate` | `RustLocateConfig`, `rust_scan`, `locate_rust`, the dependency, scanner/wrapper tests. No CLI/config/bundle. |
| `rust-integration` | `LANGUAGES`, CLI/config/`tenon.toml`/bundle dispatch, docs, CLI/bundle tests. No scanner internals. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Rust repos are invisible to the shipped locators. |
| User understanding | 🟢 | Provider/self-hoster/reviewer/T11b; the struct-literal scenario is concrete. |
| Success metrics | 🟢 | Config, scan, shared policy, CLI/bundle, offline tests. |
| Scope clarity | 🟢 | Rust only; methods/macros/re-exports excluded and named. |
| Edge cases & risks | 🟡 | Macro/builder and re-export limits are real; documented as no-site, not guesses. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Reuses the TS scanner pattern and the shared policy; one grammar dependency. |
| Go-to-market | 🟢 | A third language broadens the provider surface; Go/C# follow. |

**Areas to strengthen before sharing:** method chains and macros are common in some Rust SDKs; the
locator is honest but may miss them. The per-function struct binding is the smallest useful data flow.

**The question I would want answered before greenlighting this:** *If the customer's SDK uses a
builder (`client.charges().create(...)`) rather than associated functions, does the report lie?* The
answer this card records: no; method calls are not certain, so the site is absent and the report does
not claim it. The provider sees no site and can fall back to a manual review; method-chain tracking is
a later slice.
