# Card: feat/receiver-tracking

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **Post-T11 hardening — receiver tracking** (a follow-up to the T11 locator limits)
- **Milestone:** next phase after Phase 3; the original roadmap ends at T11
- **State:** T12a (Rust/Go) shipped 2026-11-12 (`src/tenon/locate/{rust,go}_*.py`, `--receiver`; 2,338 tests); T12b (C#/Python/TS) not started
- **Branch:** `feat/receiver-tracking/aliz`
- **Worktree:** `.claude/worktrees/feat-receiver-tracking`

## Brief

The shipped locators root names through imports (`use`, `using`, `import`), package names and
explicit `new`/struct bindings. The common alternative style — a client object built once and then
used through method/property chains — is either unrooted or not seen:

```rust
let client = Client::new(key);
client.charges().create(params);
```
```go
client := stripe.NewClient(key)
client.Charges.New(params)
```
```csharp
var client = new StripeClient(key);
client.Charges.Create(options);
```
```python
client = stripe.Client(key)
client.charges.create(amount=100)
```
```ts
const client = new StripeClient(key);
client.charges.create({ amount: 100 });
```

This phase adds **receiver tracking**: infer the SDK type of a local receiver from explicit evidence
(a visible constructor/`new`, a type annotation, or an operator-provided `receivers` mapping for
factories), then root the subsequent method/property chain and let the shared certainty policy
decide. The canonical chain keeps the type and its members, so the provider can map
`POST /v1/charges` -> `Client.charges.create`.

The hard rules do not change: no full type inference, no guessing from a name alone, no new proof
levels or ambiguity vocabulary, the shared `derive`/`resolve` policy decides, and a chain whose
receiver is not explicitly known stays unrooted/absent.

## Constraints carried in from the repo

- `src/tenon/locate/{scan,resolve}.py` is the shared policy; receiver evidence must arrive as
  `Hit`s with a canonical chain, not a second resolver.
- The five scanners (`scan`/`ts_scan`/`rust_scan`/`go_scan`/`csharp_scan`) own the language syntax;
  the shared configs gain the optional receiver mapping.
- `CliConfig`/`tenon.toml`/`MigrationBundle` are the config seams; a provider must be able to declare
  factories without writing code.
- Offline fixtures/tests; no new dependency (tree-sitter grammars already exist).

## Scope fence

Not this phase: full type inference, generics/return-type analysis, `dynamic`/reflection, macros,
interprocedural data flow, new proof levels, new ambiguity reasons, a service/deployment change.
