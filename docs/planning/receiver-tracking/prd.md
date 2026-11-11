# PRD: Receiver tracking — Rust and Go (T12a)

- **Slug:** `receiver-tracking`
- **Capability:** **T12 Receiver tracking** (post-T11 hardening; the original roadmap ends at T11)
  — **first slice: Rust and Go**
- **Milestone:** the next phase after Phase 3; T12b (C#, Python, TypeScript) follows
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

The shipped locators root names through imports, package names and explicit `new`/struct bindings.
The common client-object style is not rooted:

```rust
let client = Client::new(key);
client.charges().create(params);
```

```go
client := stripe.NewClient(key)
client.Charges.New(params)
```

A provider with a Rust or Go customer repo using this style gets no certain site, even though the
client's type is written in the code or can be declared in the config. T12a adds **receiver
tracking**: infer a local receiver's SDK type from explicit evidence, then root its method/property
chain so the shared certainty policy can decide.

Evidence is explicit, never a name guess:
- a visible construction (`let client = Client::new(...)`, `var client = &stripe.Client{}`,
  `client := &stripe.Client{}`);
- a type annotation (`let client: stripe::Client = ...`, `var client *stripe.Client`);
- an operator `receivers` mapping for factories (`{"stripe.NewClient": "Client"}`).

The canonical chain keeps the type and its members: `client.charges().create(...)` ->
`Client.charges.create`; `client.Charges.New(...)` -> `Client.Charges.New`. A receiver with no
explicit evidence stays unrooted/absent, never a guess.

**For whom:** a provider migrating a Rust/Go customer repo with a client-object SDK, a self-hoster,
and the later T12b languages.

## Goals & Success Metrics

1. **Explicit evidence only.** A construction, annotation or configured factory roots the receiver;
   a bare name never does.
2. **A stable chain.** Type + members, shared by Rust and Go, so the provider writes one mapping.
3. **One policy.** The rooted hits flow through the shipped `derive`/`resolve`; no second resolver,
   no new proof levels or ambiguity reasons.
4. **Config everywhere.** `receivers` works in the in-memory config, `tenon.toml`, the bundle and a
   repeatable CLI flag, with named validation.
5. **Offline tests.** Rust/Go source fixtures for every evidence type, chain and rebinding.
6. **No regressions.** The existing Rust/Go/Python/TS/C# tests and all prior behavior stay green.

## User Personas & Scenarios

- **Provider.** Sets `receivers: {"stripe.NewClient": "Client"}` in the bundle; the Go repo's
  `client := stripe.NewClient(key); client.Charges.New(params)` locates `Client.Charges.New`.
- **Rust provider.** The repo's `let client = Client::new(key); client.charges().create(params)`
  locates `Client.charges.create` without any config.
- **Self-hoster.** Uses `--receiver "NewClient=Client"` for a Go factory the scanner cannot see.
- **Reviewer.** Sees the same proof levels; an untracked receiver still reports no site.

Scenario: a Go repo binds `client := stripe.NewClient(key)` and calls
`client.Charges.New(params)`. With `receivers: {"stripe.NewClient": "Client"}`, the locator reports
the call at the member site; a repo with `client := buildClient()` and no mapping/annotation reports
no site.

## Requirements

### Must have

- **M1 — Config.** `RustLocateConfig`/`GoLocateConfig` gain
  `receivers: Mapping[str, str] = {}` (read-only copies); `tenon.toml` `[locate.receivers]`, a bundle
  `locate.receivers`, and a repeatable `--receiver KEY=VALUE` on `check`/`fix` feed it. Keys/values
  are non-empty strings; a bad entry is a named `ValueError` (CLI exit 2). A flag entry overrides a
  config entry with the same key.
- **M2 — Rust evidence.** In `scan_rust`:
  - `let name = Type::new(...)`, `let name = <crate>::Type::new(...)` and
    `let name = Type::default()` bind `name -> (Type,)`.
  - `let name: <crate>::Type = ...` / `let name: Type = ...` binds the annotated type (aliases
    resolved).
  - `let name = factory(...)` whose canonical chain is a `receivers` key binds the mapped type.
  - A struct-literal binding keeps its existing type + fields; a rebinding replaces the name; a
    `let` with no evidence clears it.
  - A method/property chain on a bound receiver emits `CALL`/`ATTRIBUTE` hits with the chain
    `(Type, ..., member)`: `client.charges().create(...)` -> `("Client","charges","create")` and
    the intermediate `("Client","charges")`; a chain on an untracked receiver stays unrooted.
- **M3 — Go evidence.** In `scan_go`:
  - `var name *pkg.Type`, `var name pkg.Type`, `name := &pkg.Type{...}`,
    `var name = pkg.Type{...}` bind the type chain (the existing package/alias/root logic).
  - `name := pkg.Factory(...)` / `var name = pkg.Factory(...)` whose canonical chain is a
    `receivers` key binds the mapped type.
  - A selector chain on a bound receiver emits `CALL`/`ATTRIBUTE` hits with the chain
    `(Type, ..., member)`: `client.Charges.New(...)` -> `("Client","Charges","New")` and the
    intermediate `("Client","Charges")`; a method chain on an untracked value stays unrooted.
  - A rebinding replaces the name; a `var` with no evidence clears it.
- **M4 — Policy.** Both scanners reuse the shipped `resolve`; a rooted chain is certain unless the
  shared rules say otherwise (multiple candidates, etc.). No new `SiteShape`/`LocateReason`/
  `AmbiguityReason`/`DynamicKind`.
- **M5 — Tests.** Config validation and precedence; Rust construction/annotation/factory/rebinding/
  no-evidence/chain; Go annotation/composite/factory/rebinding/no-evidence/chain; a CLI/TOML/bundle
  plumbing test for `receivers`; the existing suites green. Offline.
- **M6 — Docs.** README/ARCHITECTURE document `receivers`, the evidence types, the chain shape, the
  certainty and the limits; the capability roadmap gains T12/T12a.

### Should have

- **S1 — One mapping for both languages.** The same key/value shape, so a provider can reuse it.
- **S2 — Named errors.** A bad key/value/flag is a named error, never a traceback.
- **S3 — Determinism.** Receiver bindings are per function/file; the same input gives the same hits.

### Nice to have

- **N1 — C#, Python and TypeScript**; T12b.
- **N2 — Return-type/factory inference without config**; a later slice, if it can be certain.
- **N3 — Interprocedural receiver flow**; out of scope.

## Data Model

```
RustLocateConfig / GoLocateConfig
  sdk_package: str
  operations: Mapping[str, str]
  fields: Mapping[str, str]
  receivers: Mapping[str, str]   # factory/constructor expression -> type chain
```

A bound receiver is scanner-local state (name -> type chain); the hits carry the canonical chain.

## API Contract

```toml
[locate]
language = "go"
sdk_package = "github.com/stripe/stripe-go/v76"
package_name = "stripe"

[locate.receivers]
"stripe.NewClient" = "Client"
```

```sh
tenon check path/to/repo --old old.yaml --new new.yaml \
  --language go --sdk-package github.com/stripe/stripe-go/v76 \
  --receiver "stripe.NewClient=Client"
```

## Technical Considerations

- **Why explicit evidence.** A receiver's type is only knowable from syntax (construction/annotation)
  or operator config; a name heuristic is the guessing the project refuses.
- **Why type + members.** The provider can distinguish `Client.charges.create` from
  `Other.charges.create`; dropping the type collides.
- **Why a config mapping.** Go's dominant factory style (`NewClient`) has no visible type; the
  mapping is explicit, portable and testable.
- **Why per-function bindings.** Both languages scope locally; a file-wide map would misattribute.
- **Why no new resolver.** A rooted receiver chain is ordinary `Hit` evidence; the shared policy
  already handles multiple candidates and ambiguity.

## Risks & Open Questions

- **Factory coverage.** A factory not in `receivers` and not annotated stays absent; the provider
  adds a mapping. Documented.
- **False positives.** A local type with the same name as the mapped/rooted type is a documented
  risk (as with the existing simple-name roots).
- **Method vs field.** Rust intermediate members are method calls; a field access chain is not
  followed unless it is a tracked struct binding.
- **Rebinding.** A later `let`/`var` without evidence clears the receiver; the scanner does not
  merge branches.
- **Open question — should a constructor other than `new`/`default` be implicit evidence?** No in
  this slice; `receivers` covers it.
- **Open question — should the chain include the client type for Go pointer methods?** Yes; the type
  is the base, members follow.

## Out of Scope

- T12b (C#, Python, TypeScript).
- Full type inference, generics/return types, interprocedural flow, `dynamic`/reflection, macros.
- New proof levels, ambiguity reasons, dynamic kinds; a service/deployment change.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `receiver-config` | `receivers` on the Rust/Go configs, `[locate.receivers]`, bundle, `--receiver`, precedence/validation. No scanners. |
| `rust-receivers` | Rust evidence bindings and receiver-chain hits. No config/CLI. |
| `go-receivers` | Go evidence bindings and receiver-chain hits. No config/CLI. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Client-object SDKs are the main unrooted style. |
| User understanding | 🟢 | Provider/self-hoster/reviewer; the factory mapping is concrete. |
| Success metrics | 🟢 | Explicit evidence, one chain, shared policy, config everywhere, offline tests. |
| Scope clarity | 🟢 | Rust/Go only; T12b and inference excluded. |
| Edge cases & risks | 🟡 | Factory coverage and false positives are real; documented as no-site/config. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Extends the existing scanners/configs; no new dependency. |
| Go-to-market | 🟢 | Closes the biggest locator gap for the two client-object languages. |

**Areas to strengthen before sharing:** the mapping is a manual provider step; a future return-type
analysis could infer more, but only if it stays certain. The explicit mapping is the honest MVP.

**The question I would want answered before greenlighting this:** *If a Go repo's factory is not in
`receivers`, does the report lie?* The answer this card records: no; the receiver is untracked, the
chain stays unrooted/absent, and the provider adds a mapping or annotates the variable.
