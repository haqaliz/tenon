# Card: feat/locator-rust

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T11 More languages** — first slice: **Rust locator** (`docs/technical/CAPABILITY_ROADMAP.md:17`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), first T11 slice
- **Branch:** `feat/locator-rust/aliz`
- **Worktree:** `.claude/worktrees/feat-locator-rust`

## Brief

Tenon locates Python (stdlib `ast`) and TypeScript/JavaScript (tree-sitter) call sites. Rust SDKs are
common for infrastructure and API clients, and a provider cannot migrate a Rust customer repo today.

T11a adds **`--language rust`** with the same locate contract:
- `RustLocateConfig` (a crate name, operations and fields mappings);
- a read-only tree-sitter-rust scan that reports rooted hits and dynamics, reusing the shared
  certainty policy (`derive`/`resolve`) and the shared `Site`/`LocateResult` types;
- crate matching through `use` declarations (including `use stripe::{Charge, Customer};` and
  `use stripe::Charge as StripeCharge;`) and associated-function calls (`Charge::create(...)`,
  `StripeCharge::create(...)`);
- struct-literal fields (`CreateCharge { amount: 100, ..Default::default() }`) and field access
  (`params.amount`) where the shared policy can call them certain;
- the CLI/config/bundle accept `rust`; OpenAPI only (MCP location stays Python);
- fixture Rust repos and tests for certain sites, aliases, unrooted receivers, unmapped symbols and
  operation/field mappings.

The proof runner is unchanged: a Rust repo uses `--check "cargo test"` or `cargo check` like any
other command. No Rust toolchain is required to locate.

The hard rules do not change: locate reports evidence, the shared policy decides certainty, no
guessing, honest reasons/ambiguity groups, no new proof levels, no network.

## Constraints carried in from the repo

- `src/tenon/locate/resolve.py` is the only certainty policy; the Rust path must not fork it.
- `src/tenon/locate/result.py` is the shared contract (`Site`, `SiteShape`, `LocateReason`,
  `AmbiguityReason`, `LocateResult`).
- `src/tenon/locate/ts_scan.py` is the tree-sitter pattern; the Rust scanner reports `Hit`/`Dynamic`
  evidence only.
- `CliConfig`/`tenon.toml`/`MigrationBundle` validate `language`; extend them to `rust` with named
  errors.
- Offline tests: fixture Rust repos, no network, no Rust toolchain.

## Scope fence

Not this card: Go/C# locators, a Cargo proof preset, MCP Rust location, new ambiguity/proof
vocabularies, a hosted service.
