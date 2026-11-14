# PRD: Typed-parameter receiver inference (T12d)

- **Slug:** `parameter-inference`
- **Capability:** **T12 Receiver tracking** — deeper slice: **annotated parameters**
- **Milestone:** after T12c; the receiver follow-up
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T12c roots a receiver from a same-file helper's annotated **return** type. The other common style is
a typed **parameter**: a function/method receives the SDK client as an annotated argument and uses it
inside the body.

```python
def create_charge(client: stripe.Client, amount: int):
    return client.charges.create(amount=amount)
```
```ts
function createCharge(client: StripeClient, amount: number) {
  return client.charges.create({ amount });
}
```
```rust
fn create_charge(client: &Client, amount: i64) {
    client.charges().create(amount);
}
```
```go
func createCharge(client *stripe.Client, amount int64) {
    client.Charges.New(params)
}
```
```csharp
static void CreateCharge(StripeClient client, long amount) {
    client.Charges.Create(options);
}
```

The parameter type is written in the signature, but the scanner does not root it, so the body's chain
is unrooted. T12d adds **annotated parameter inference**: a parameter whose written type resolves
through the SDK roots is a rooted receiver inside that function/method body. Only a written
annotation counts; an unannotated parameter, `self`/`this`, `any`/`void`, a generic or a non-SDK type
is not evidence.

This completes the deeper receiver work (returns in T12c, parameters in T12d). The scope decisions
carry over from T12c: all five languages, annotated-only, per-function.

**For whom:** a provider migrating a repo that passes its SDK client through typed functions, a
self-hoster, and the reviewer of the located sites.

## Goals & Success Metrics

1. **One evidence rule.** A parameter with an explicit SDK annotation is a rooted receiver inside its
   function/method; no annotation, no evidence.
2. **All five languages.** Python, TypeScript, Rust, Go and C# resolve the parameter type through the
   shipped roots/aliases.
3. **The same chain.** `Type.member...` as T12a–T12c; the shared `derive`/`resolve` decides
   certainty; no new shapes/reasons/dynamic kinds.
4. **Honest scope.** Per function/method; no `self`/`this`, generic/overload or cross-file
   inference.
5. **Offline tests.** A typed parameter, an unannotated/`any`/`void`/wrong type, a nested function,
   a rebinding and the existing suites green.

## Requirements

### Must have

- **M1 — Python.** `scan`: for each function/method, the annotated `args`/`posonlyargs`/`kwonlyargs`
  (a direct `Name`/`Attribute` resolving through the SDK roots) seed the receiver bindings for the
  body; an unannotated parameter (including `self`), a string/`Optional`/generic annotation or a
  non-SDK type is not evidence.
- **M2 — TypeScript.** `scan_ts`: each `required_parameter`/`optional_parameter` with a
  `type_annotation` resolving through the import roots/aliases seeds the function/method/arrow body;
  a missing/`any`/non-SDK parameter is not evidence.
- **M3 — Rust.** `scan_rust`: each `function_item` `parameter` with a `type` resolving through the
  crate roots/aliases (`client: Client`, `client: &Client`, `client: stripe::Client`) seeds the body;
  an untyped `self`, a generic/`impl` or non-SDK parameter is not evidence.
- **M4 — Go.** `scan_go`: each `function_declaration` `parameter_declaration` type resolving through
  the import roots/`package_name` (`client *stripe.Client`, `client stripe.Client`) seeds the body;
  a grouped name list (`a, b *Client`) binds each name; an untyped/non-SDK parameter is not evidence.
- **M5 — C#.** `scan_csharp`: each method/local-function `parameter` type resolving through the
  namespace usings/aliases (`StripeClient client`) seeds the body; a missing/`object`/`dynamic`/
  generic/non-SDK parameter is not evidence.
- **M6 — Policy/scope.** The parameter binding is the initial binding for the function body; a local
  assignment rebinds/clears; a nested function's parameters are its own; the hit chain is
  `Type.member...`; the shared `resolve` decides; no new vocabulary.
- **M7 — Tests/docs.** Per-language typed/unannotated/wrong/nested/rebinding tests, a policy case,
  one end-to-end `tenon check` typed-parameter fixture; README/ARCHITECTURE/CHANGELOG `Unreleased`/
  capability roadmap T12d. Offline.

### Should have

- **S1 — One pass.** The parameter bindings are seeded at function entry from the signature; no
  second scan.
- **S2 — Named boundaries.** An unannotated/generic/cross-file parameter stays unrooted; no guess.
- **S3 — No config change.** `receivers` remains the escape hatch; the parameter inference is
  automatic.

### Nice to have

- **N1 — Cross-file/package signature indexes**; a later slice.
- **N2 — `self`/`this` method-return inference**; not in this slice.
- **N3 — Generic parameter instantiation**; not in this slice.

## Data Model

No new config or hit type. Per-function parameter bindings feed the existing receiver map; the hit
chain is `Type.member...`.

## API Contract

No CLI/config change. The inferred evidence is automatic; `--receiver` still overrides/extends.

## Technical Considerations

- **Why the annotation.** It is written, language-enforced and resolves through the existing roots;
  an unannotated parameter is a guess.
- **Why per-function.** A parameter is scoped to its function; a file-wide name would leak across
  functions.
- **Why no `self`/`this`.** The receiver's type is the class, not the SDK client; a method call on
  `self` is not the SDK receiver in this contract.
- **Why reuse the roots.** The parameter type is just another type expression.

## Risks & Open Questions

- **Nested functions/closures.** A nested function's parameters are its own; an outer parameter is
  not carried into a nested function (documented). A closure capture is a later slice.
- **Shadowing.** A parameter name rebound locally replaces/clears the binding (the existing
  assignment rule).
- **Generics.** A parameter typed as a generic SDK type (`Client<T>`) is not resolved unless the
  annotation is a concrete SDK type.
- **Go grouped/typed lists.** A grouped name list binds each name; an unnamed parameter has no name
  to bind.
- **Open question — should an annotated `self: Client` bind?** It is unusual; the rule would bind it,
  but the contract targets ordinary parameters. The scanner can skip `self` uniformly; documented.

## Out of Scope

- Unannotated parameters, `self`/`this`, generics/overloads, cross-file/package indexes.
- New proof levels/ambiguity reasons; a service/deployment change.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `parameters-python-ts` | Python/TS parameter seeding + receiver-chain tests. |
| `parameters-rust-go` | Rust/Go parameter seeding + receiver-chain tests. |
| `parameters-csharp` | C# parameter seeding + receiver-chain tests. |
| `parameters-docs` | README/ARCHITECTURE/CHANGELOG/roadmap, the end-to-end fixture, the full suite. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Typed parameters are a common unrooted style. |
| User understanding | 🟢 | Provider/self-hoster/reviewer; the parameter scenario is concrete. |
| Success metrics | 🟢 | Annotated parameters, all five, same chain, honest scope, offline tests. |
| Scope clarity | 🟢 | Per-function parameters only; self/generic/cross-file excluded. |
| Edge cases & risks | 🟡 | Nested closures, shadowing and generics are real; documented/unrooted. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Extends the existing scanners/roots; no dependency. |
| Go-to-market | 🟢 | Completes the deeper receiver work without a config burden. |

**Areas to strengthen before sharing:** per-function only; a closure capturing an outer typed
parameter is not followed. That is the honest, certain boundary.

**The question I would want answered before greenlighting this:** *If a parameter is unannotated, does
the report guess?* The answer this card records: no; the body's chain stays unrooted and the report
does not claim the site. The provider annotates the parameter or maps a factory.
