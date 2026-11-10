# Card: feat/locator-go

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T11 More languages** — second slice: **Go locator** (`docs/technical/CAPABILITY_ROADMAP.md:17`)
- **Milestone:** Phase 3 (`docs/ROADMAP.md`), second T11 slice
- **State:** shipped 2026-11-10 (`src/tenon/locate/go_*.py`, CLI; 2,013 tests)
- **Branch:** `feat/locator-go/aliz`
- **Worktree:** `.claude/worktrees/feat-locator-go`

## Brief

Tenon locates Python, TypeScript/JavaScript and Rust call sites. Go SDKs are a large share of vendor
APIs, and a provider cannot migrate a Go customer repo today.

T11b adds **`--language go`** with the same locate contract:
- `GoLocateConfig` (an import path, an optional package name, the shared operations/fields mappings);
- a read-only tree-sitter-go scan that reports rooted hits and dynamics, reusing the shared
  `derive`/`resolve` certainty policy and the shared `Site`/`LocateResult` types;
- import-path matching with aliases (`import stripe "github.com/stripe/stripe-go/v76"`) and the
  default package name (the last non-version path segment);
- package-qualified calls (`stripe.Charge.New(...)`, `charge.New(...)`), composite-literal fields
  (`stripe.ChargeParams{Amount: ...}`) and field access through a tracked binding;
- the CLI/config/bundle accept `go`; OpenAPI only (MCP location stays Python);
- fixture Go repos and tests for certain sites, aliases, unrooted receivers, unmapped symbols and
  operation/field mappings.

The proof runner is unchanged: a Go repo uses `--check "go test ./..."` or `go build ./...` like any
other command. No Go toolchain is required to locate.

The hard rules do not change: locate reports evidence, the shared policy decides certainty, no
guessing, honest reasons/ambiguity groups, no new proof levels, no network.

## Constraints carried in from the repo

- `src/tenon/locate/resolve.py` is the only certainty policy; the Go path must not fork it.
- `src/tenon/locate/result.py` is the shared contract (`Site`, `SiteShape`, `LocateReason`,
  `AmbiguityReason`, `LocateResult`).
- `src/tenon/locate/{ts,rust}_scan.py` are the tree-sitter patterns; the Go scanner reports
  `Hit`/`Dynamic` evidence only.
- `LOCATE_TYPES`/`LOCATORS` are the one dispatch registry; extend them, do not add if-chains.
- `CliConfig`/`tenon.toml`/`MigrationBundle` validate `language`; extend them to `go` with named
  errors.
- Offline tests: fixture Go repos, no network, no Go toolchain.

## Scope fence

Not this card: C# locator, a Go proof preset, MCP Go location, new ambiguity/proof vocabularies,
method-chain receiver tracking, a hosted service.
