# Card: feat/locator-csharp

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T11 More languages** — third slice: **C# locator** (`docs/technical/CAPABILITY_ROADMAP.md:17`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), third T11 slice
- **Branch:** `feat/locator-csharp/aliz`
- **Worktree:** `.claude/worktrees/feat-locator-csharp`

## Brief

Tenon locates Python, TypeScript/JavaScript, Rust and Go call sites. C# SDKs are common in
enterprise repos, and a provider cannot migrate a C# customer repo today.

T11c adds **`--language csharp`** with the same locate contract:
- `CSharpLocateConfig` (a namespace root, the shared operations/fields mappings);
- a read-only tree-sitter-c-sharp scan that reports rooted hits and dynamics, reusing the shared
  `derive`/`resolve` certainty policy and the shared `Site`/`LocateResult` types;
- namespace/using matching (`using Stripe;`, `using Stripe.Services;`,
  `using StripeCharge = Stripe.Charge;`) and qualified type usage;
- static/instance calls (`ChargeService.Create(...)`, `Stripe.ChargeService.Create(...)`),
  object-initializer properties (`new ChargeCreateOptions { Amount = ... }`) and property access
  through a tracked binding;
- the CLI/config/bundle accept `csharp`; OpenAPI only (MCP location stays Python);
- fixture C# repos and tests for certain sites, aliases, unrooted receivers, unmapped symbols and
  operation/field mappings.

The proof runner is unchanged: a C# repo uses `--check "dotnet test"` or `dotnet build` like any
other command. No .NET toolchain is required to locate.

The hard rules do not change: locate reports evidence, the shared policy decides certainty, no
guessing, honest reasons/ambiguity groups, no new proof levels, no network.

## Constraints carried in from the repo

- `src/tenon/locate/resolve.py` is the only certainty policy; the C# path must not fork it.
- `src/tenon/locate/result.py` is the shared contract (`Site`, `SiteShape`, `LocateReason`,
  `AmbiguityReason`, `LocateResult`).
- `src/tenon/locate/{ts,rust,go}_scan.py` are the tree-sitter patterns; the C# scanner reports
  `Hit`/`Dynamic` evidence only.
- `LOCATE_TYPES`/`LOCATORS` are the one dispatch registry; extend them, do not add if-chains.
- `CliConfig`/`tenon.toml`/`MigrationBundle` validate `language`; extend them to `csharp` with named
  errors.
- Offline tests: fixture C# repos, no network, no .NET toolchain.

## Scope fence

Not this card: Go/Rust changes, a .NET proof preset, MCP C# location, new ambiguity/proof
vocabularies, fluent-chain receiver tracking, a hosted service.
