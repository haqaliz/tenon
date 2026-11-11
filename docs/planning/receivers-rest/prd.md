# PRD: Receiver tracking — C#, Python and TypeScript (T12b)

- **Slug:** `receivers-rest`
- **Capability:** **T12 Receiver tracking** — **second slice: C#, Python and TypeScript**
- **Milestone:** next phase after Phase 3; T12a (Rust/Go) shipped 2026-11-12
- **Status:** draft for review
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T12a roots a Rust/Go client object from explicit evidence, so
`client.charges().create(...)` / `client.Charges.New(...)` locate as `Type.member...`. The other
three locators still leave the same style unrooted:

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

T12b extends the T12a contract to **C#, Python and TypeScript**: a visible construction
(`new Type(...)`, `Type(...)`), a type annotation, or a configured `receivers` factory roots the
receiver; the canonical chain is `Type.member...`; the shared `derive`/`resolve` policy decides
certainty. An untracked receiver keeps the current no-site/unrooted behavior.

This completes T12 across all five locators.

**For whom:** a provider migrating a C#/Python/TS customer repo with a client-object SDK, a
self-hoster, and the existing T10 provider layer.

## Goals & Success Metrics

1. **Same contract as T12a.** Explicit evidence only; `Type.member...`; certain when explicit; no
   new shapes/reasons/dynamic kinds.
2. **All five configs.** `receivers` is on `LocateConfig`, `TsLocateConfig` and
   `CSharpLocateConfig`, and the TOML/bundle/`--receiver` plumbing serves every language.
3. **Three scanners.** C#, Python and TypeScript bind a receiver from construction/annotation/factory
   and root its chains; an untracked receiver is unchanged.
4. **Offline tests.** Fixtures/temp files for every evidence type, chain, rebinding and no-evidence
   case in each language.
5. **No regressions.** All prior tests and the T12a behavior stay green.

## Requirements

### Must have

- **M1 — Config.** `LocateConfig`/`TsLocateConfig`/`CSharpLocateConfig` gain the same read-only
  `receivers` mapping and named validation; `[locate.receivers]`, a bundle `locate.receivers` and a
  repeatable `--receiver KEY=VALUE` apply to all five languages. The T12a "ignored for other
  languages" behavior is removed; a malformed entry is still a named error.
- **M2 — C# evidence/chain.** In `scan_csharp`:
  - `new Type(...)` / `new Type(...) { ... }`, a type annotation (`ChargeClient client = ...`), or a
    configured factory (`StripeClient.Create`) binds the receiver.
  - A member/call chain on a bound receiver emits rooted `CALL`/`ATTRIBUTE` hits with
    `(Type, ..., member)`: `client.Charges.Create(...)` -> `("Client","Charges","Create")` and the
    intermediate `("Client","Charges")`.
  - The existing static/`new`-binding behavior remains.
- **M3 — Python evidence/chain.** In `scan`:
  - `client = stripe.Client(...)` (a call whose callee is a rooted imported name), a type annotation
    (`client: stripe.Client = ...`), or a configured factory (`stripe.make_client`) binds the
    receiver.
  - A method/attribute chain on a bound receiver emits rooted `CALL`/`ATTRIBUTE` hits with
    `(Type, ..., member)`: `client.charges.create(...)` -> `("Client","charges","create")` and the
    intermediate `("Client","charges")`; keyword arguments are attributed to the call chain.
  - An untracked receiver keeps the current unrooted behavior.
- **M4 — TypeScript evidence/chain.** In `scan_ts`:
  - `const client = new StripeClient(...)`, a type annotation (`const client: Client = ...`), or a
    configured factory (`StripeClient.create`) binds the receiver.
  - A method/property chain on a bound receiver emits rooted `CALL`/`ATTRIBUTE` hits with
    `(Type, ..., member)`: `client.charges.create({...})` -> `("Client","charges","create")` and the
    intermediate `("Client","charges")`; object keys are attributed to the call chain.
  - An untracked receiver keeps the current unrooted behavior.
- **M5 — Policy.** All three reuse the shipped `resolve`; no new vocabulary.
- **M6 — Tests/docs.** Per-language evidence/chain/rebinding/no-evidence/policy tests; config and
  plumbing tests for all five; README/ARCHITECTURE/status updates. Offline.
- **M7 — No inference expansion.** No return-type/interprocedural analysis, `dynamic`/`getattr`,
  reflection, macros or a factory-name heuristic.

### Should have

- **S1 — One mapping.** The same `receivers` key/value shape as T12a.
- **S2 — Named errors.** Bad keys/values/pairs are named.
- **S3 — Determinism.** Bindings are per function/file; no clock/network.

### Nice to have

- **N1 — Return-type inference** only if it can stay certain; a later card.
- **N2 — Interprocedural receiver flow**; out of scope.

## Data Model

The three configs gain:

```
receivers: Mapping[str, str]   # factory/constructor expression -> type chain
```

A receiver binding is scanner-local (name -> type chain); the hits carry `(Type, ..., member)`.

## API Contract

```toml
[locate]
language = "python"
sdk_package = "stripe"

[locate.receivers]
"stripe.make_client" = "Client"
```

```sh
tenon check path/to/repo --old old.yaml --new new.yaml \
  --language csharp --sdk-package Stripe --receiver "StripeClient.Create=Client"
```

## Technical Considerations

- **Why the same contract.** The provider writes one mapping and one chain shape across languages;
  the shared policy handles certainty.
- **Why a visible construction is evidence.** `new Type(...)` / `Type(...)` names the type; an
  annotation is explicit; a factory needs the operator map.
- **Why drop C#/Python/TS module prefixes?** The canonical chain is the type and its members, like
  T12a; the existing language roots handle imports.
- **Why no inference.** A dynamic receiver whose type is not written or configured is a guess; the
  report stays silent.

## Risks & Open Questions

- **Dynamic typing.** Python/TS can reassign a receiver to another type; a later assignment without
  evidence clears the binding, but branch-sensitive flow is not modeled.
- **Simple-name collisions.** A local class/type sharing a rooted/mapped name is a documented false
  positive (as in T11).
- **C# property chains.** The intermediate `Charges` type is not known; the chain is rooted by the
  explicit client type. A property that returns an unrelated type could over-root; the mapping and
  the shared policy are the guard.
- **Python/TS computed access.** `getattr`/bracket access is not followed; no new dynamic kind.
- **Open question — should a Python annotation without a value bind?** Yes; the annotation is explicit
  evidence for later uses.
- **Open question — should a TS `as` cast bind?** A cast is an annotation-like assertion; include it
  if the scanner can see the type node; otherwise a later card.

## Out of Scope

- Return-type/interprocedural inference, `dynamic`/reflection, macros, a factory-name heuristic.
- New proof levels/ambiguity reasons; a service/deployment change.

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `receiver-config-all` | `receivers` on the three remaining configs; TOML/bundle/CLI for all five; the T12a ignore rule removed. No scanners. |
| `csharp-receivers` | C# evidence bindings and receiver chains. |
| `python-receivers` | Python evidence bindings and receiver chains. |
| `ts-receivers` | TypeScript evidence bindings and receiver chains. |

## Self-critique (prd-generator pass)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | The client-object style is unrooted in three languages. |
| User understanding | 🟢 | Provider/self-hoster; the per-language evidence is concrete. |
| Success metrics | 🟢 | Same contract, all configs, three scanners, offline tests. |
| Scope clarity | 🟢 | C#/Python/TS only; inference/dynamic excluded. |
| Edge cases & risks | 🟡 | Dynamic reassignment and C# property chains are real; documented. |
| Stakeholder alignment | 🟡 | Solo project; the review gate is the approver. |
| Feasibility | 🟢 | Extends the existing scanners/configs; no new dependency. |
| Go-to-market | 🟢 | Completes receiver tracking across all five locators. |

**Areas to strengthen before sharing:** Python/TS dynamic reassignment and C# intermediate property
types are not modeled; the explicit evidence rule is the honest boundary.

**The question I would want answered before greenlighting this:** *If a Python receiver is reassigned
to a mock in a test, does the locator treat the mock as the SDK type?* The answer this card records:
a reassignment without evidence clears the binding; a reassignment to another explicit construction
binds that type. Branch-sensitive flow is not modeled, so a mock built from the same class is a
documented limitation.
