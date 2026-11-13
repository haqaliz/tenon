# PRD: Typed-function receiver inference — return types (T12c)

- **Slug:** `receiver-inference`
- **Capability:** **T12 Receiver tracking** — deeper slice: **annotated return types**
- **Milestone:** after v0.1.0/T10f; T12c
- **Status:** implemented 2026-11-14 (`src/tenon/locate/*_scan.py`, same-file return annotations; 2,609 tests)
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T12a/T12b root a receiver from an explicit construction (`Client::new`, `new Client`, `Client()`), a
type annotation or a configured factory. A common style hides the construction behind a typed
helper:

```python
def make_client() -> stripe.Client: ...
client = make_client()
client.charges.create(...)
```
```ts
function makeClient(): StripeClient { ... }
const client = makeClient();
client.charges.create({...})
```
```rust
fn make_client() -> Client { ... }
let client = make_client();
client.charges().create(...)
```
```go
func newClient() *stripe.Client { ... }
client := newClient()
client.Charges.New(...)
```
```csharp
static StripeClient MakeClient() => new(...);
var client = MakeClient();
client.Charges.Create(...);
```

The function's return type is written in the signature, but the scanner does not read it, so the
receiver is unrooted. T12c adds **annotated return-type inference**: a same-file function/method with
an explicit SDK return annotation is evidence; a call assigned to a local roots the receiver with that
type. Only a written annotation counts — a bare function name or a body-only construction is not
evidence.

Parameter-type inference (a function parameter annotated with the SDK type is a rooted receiver
inside the body) is T12d if sliced.

**For whom:** a provider migrating a repo that wraps its SDK client in a typed helper, a self-hoster,
and the reviewer of the located sites.

## Goals & Success Metrics

1. **One evidence rule.** A same-file function/method with an annotated return type that resolves
   through the SDK root roots the assigned receiver; no annotation, no evidence.
2. **All five languages.** Python, TypeScript, Rust, Go and C# use the shipped roots/aliases to
   resolve the return type.
3. **The same chain.** `Type.member...` as T12a/T12b; the shared `derive`/`resolve` decides
   certainty; no new shapes/reasons/dynamic kinds.
4. **Honest scope.** Same-file functions only; no cross-file lookup, no unannotated returns, no
   return-type analysis from a function body.
5. **Offline tests.** A helper-typed receiver in each language, an unannotated helper, a
   wrong-return helper, a cross-file helper (not found), a rebinding and the existing suites green.

## Requirements

### Must have

- **M1 — Python.** `scan`: a same-file `def`/method with a `returns` annotation that resolves through
  the imported SDK roots (a direct `Name`/`Attribute`, e.g. `-> stripe.Client`); an `Assign`/`AnnAssign`
  whose RHS is a call to that function binds the receiver to the annotated chain. A string/forward
  annotation, a missing return, or a non-SDK type is not evidence.
- **M2 — TypeScript.** `scan_ts`: a same-file `function`/method/arrow with a `return_type` that
  resolves through the import roots/aliases; `const/let/var = fn(...)` binds the return chain. A
  missing/`any`/non-SDK return type is not evidence.
- **M3 — Rust.** `scan_rust`: a same-file `fn`/method with a `return_type` that resolves through the
  crate roots/aliases (`-> Client`, `-> stripe::Client`); a `let` whose value is a call to that
  function binds the return chain. A missing/`impl`/non-SDK return is not evidence.
- **M4 — Go.** `scan_go`: a same-file `func` with a single result (or a result list whose first type
  is the SDK type) resolving through the import roots/`package_name`; a `var`/`:=` whose value is a
  call to that function binds the return chain. Multiple results: the first type only; a named
  result/method on a local value is not evidence.
- **M5 — C#.** `scan_csharp`: a same-file method/local function with a return type that resolves
  through the namespace usings/aliases (`StripeClient`, `Stripe.ChargeClient`); a `var`/explicit
  declaration whose value is a call to that method binds the return chain. A missing/`void`/
  non-SDK return is not evidence.
- **M6 — Policy.** All five reuse the shipped `resolve`; a rooted call on the inferred receiver is
  certain unless the shared rules say otherwise; no new vocabulary.
- **M7 — Tests/docs.** Per-language helper/unannotated/wrong/cross-file/rebinding tests; one
  end-to-end `tenon check` helper fixture (at least one language or the existing fixtures extended);
  README/ARCHITECTURE/CHANGELOG `Unreleased` and the capability roadmap T12c. Offline.

### Should have

- **S1 — One pass.** Build the same-file signature map before the receiver bindings; no second scan.
- **S2 — Named boundaries.** A cross-file or unannotated helper stays unrooted; no guess.
- **S3 — No config change.** `receivers` remains the escape hatch for SDK factories; the inference
  is automatic.

### Nice to have

- **N1 — Typed parameters**; T12d.
- **N2 — Cross-file/package signatures**; a later slice.
- **N3 — Unannotated body-return inference**; not in this slice (a guess beyond the signature).

## Data Model

No new config or hit type. A per-file `name -> type chain` signature map feeds the existing
receiver binding; the hit chain is `Type.member...`.

## API Contract

No CLI/config change. The inferred evidence is automatic; `--receiver` still overrides/extends.

## Technical Considerations

- **Why the annotation.** It is written, language-enforced and resolves through the existing roots;
  a function body or a name is an inference beyond the contract.
- **Why same-file.** A name in another file needs a package/repo index and collision policy; the
  same-file map is certain today.
- **Why reuse the roots.** The return type is just another type expression; the crate/package/
  namespace/import logic already resolves it.
- **Why no new vocabulary.** The inferred receiver is ordinary evidence; the shared policy decides.

## Risks & Open Questions

- **Same-file only.** A helper in another file is missed; the provider can annotate the assignment
  or add a `receivers` mapping. A later slice can index packages.
- **Name collisions.** Two same-file functions with the same name cannot both have one return type in
  the typed languages; Python/TS can shadow, and the last definition wins. Documented.
- **Overloads/generics.** C# overloads share a return type; generic returns are not resolved unless
  the annotation is a concrete SDK type.
- **Go named results.** Out of scope; the first concrete result type is used when there is a list.
- **Python string annotations.** Forward-reference strings are not parsed; a direct annotation is
  required.
- **Open question — should a method on `self`/`this` be evidence?** Only an unqualified same-file
  call or a direct name; a method on an instance needs the instance's type, which T12d may cover.

## Out of Scope

- Typed parameters (T12d), cross-file/package indexes, unannotated body-return inference.
- Generics/overload resolution, `dynamic`/`getattr`, macros, `self`/`this` method-return inference.
- New proof levels/ambiguity reasons; any service/deployment change.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `inference-python-ts` | The Python and TypeScript signature maps + assignment evidence + scanner tests. |
| `inference-rust-go` | The Rust and Go signature maps + assignment evidence + scanner tests. |
| `inference-csharp` | The C# signature map + assignment evidence + scanner tests. |
| `inference-docs` | README/ARCHITECTURE/CHANGELOG/roadmap, the end-to-end fixture, the full suite. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Typed helpers are the common unrooted style. |
| User understanding | 🟢 | Provider/self-hoster/reviewer; the helper scenario is concrete. |
| Success metrics | 🟢 | Annotated returns, all five, same chain, honest scope, offline tests. |
| Scope clarity | 🟢 | Same-file returns only; parameters/cross-file/body excluded. |
| Edge cases & risks | 🟡 | Cross-file misses and collisions are real; documented as unrooted. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Extends the existing scanners/roots; no dependency. |
| Go-to-market | 🟢 | Closes the typed-helper gap without a config burden. |

**Areas to strengthen before sharing:** same-file only; a helper in another file still needs an
annotation on the assignment or a `receivers` mapping. That is the honest, certain boundary.

**The question I would want answered before greenlighting this:** *If a helper is unannotated, does
the report guess?* The answer this card records: no; the assignment stays unrooted and the report
does not claim the site. The provider annotates the helper or maps a factory.
