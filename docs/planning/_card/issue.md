# Card: feat/receivers-rest

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T12 Receiver tracking** — second slice: **C#, Python and TypeScript** (T12b)
- **Milestone:** next phase after Phase 3; T12a (Rust/Go) shipped
- **State:** shipped 2026-11-12 (`src/tenon/locate/{scan,ts_scan,csharp_scan}.py`, `--receiver`; 2,453 tests)
- **Branch:** `feat/receivers-rest/aliz`
- **Worktree:** `.claude/worktrees/feat-receivers-rest`

## Brief

T12a roots a client object in Rust and Go from explicit evidence and a `receivers` mapping, so
`client.charges().create(...)` / `client.Charges.New(...)` locate as `Type.member...`. The other
three languages still leave the client-object style unrooted:

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

T12b adds **receiver tracking for C#, Python and TypeScript** with the same contract:
- explicit evidence only: a visible construction (`new Type(...)`, `Type(...)`), a type annotation,
  or an operator `receivers` mapping for factories;
- the canonical chain keeps the type and its members (`Client.charges.create`, `Client.Charges.Create`);
- the shared `derive`/`resolve` policy decides certainty; no new shapes/reasons/dynamic kinds;
- an untracked receiver keeps the current no-site/unrooted behavior.

This completes T12 across all five locators.

The hard rules do not change: no full type inference, no guessing from a name, no new proof levels,
no network, offline fixtures/tests.

## Constraints carried in from the repo

- T12a's `receivers` contract and the T11 language scanners are the base; extend, do not fork.
- `LocateConfig`/`TsLocateConfig`/`CSharpLocateConfig` gain the same read-only mapping; the
  TOML/bundle/`--receiver` plumbing already exists for Rust/Go and must serve all five.
- `src/tenon/locate/{scan,ts_scan,csharp_scan}.py` own the syntax; the shared policy stays untouched.
- Offline fixtures/tests; no new dependency (tree-sitter/Python `ast` already exist).

## Scope fence

Not this card: full type inference, return-type/interprocedural flow, `dynamic`/reflection, macros,
new proof levels/ambiguity reasons, a service/deployment change.
