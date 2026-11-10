# Spec: `rust-locate` (T11a)

- **Feature:** `locator-rust`
- **PRD:** `docs/planning/locator-rust/prd.md` (§ M1–M3)
- **Boundary:** the Rust config, scanner and locate wrapper. No CLI/config-file/bundle.

## Problem slice

A Rust repo's SDK calls and struct fields must become the same evidence the shared certainty policy
already understands: rooted `Hit`s with a canonical chain, plus honest dynamics. This aspect adds the
Rust config, the tree-sitter scan and the wrapper.

## In-scope requirements

- `src/tenon/locate/rust_config.py`:
  - `RustLocateConfig(sdk_package: str, operations={}, fields={})`, frozen/slots, mapping proxies.
  - `sdk_package` is one crate identifier `[A-Za-z_][A-Za-z0-9_]*`; blank/`::`/path is a named
    `ValueError`.
- `src/tenon/locate/rust_scan.py`: `scan_rust(root, sdk_package) -> ScanResult`.
  - `.rs` files under `root`, sorted; skip `target`, `vendor`, `.git` and hidden directories.
  - Parse with `tree-sitter-rust`; emit `Hit`/`Dynamic` evidence only.
  - Rooting:
    - `use <crate>::...` (simple, grouped, nested groups, `as`, crate alias, `self`); a glob roots
      no individual names.
    - A path whose first segment is the crate identifier.
    - Aliases resolve to the canonical chain after the crate root.
  - Associated/path calls (`Charge::create(...)`, `stripe::Charge::create(...)`,
    `StripeCharge::create(...)`) -> `SiteShape.CALL`, symbol = the leaf, chain = canonical,
    `rooted=True`.
  - Struct literals of a rooted type -> `SiteShape.KEYWORD` field hits. A literal inline in a rooted
    call, or a local `let` binding to one passed to a rooted call, also emits field hits with the call
    chain. Standalone literals keep the type chain.
  - Field access (`params.amount`) through a tracked binding -> `SiteShape.ATTRIBUTE`, rooted, with the
    type chain and (when passed to a rooted call) the call chain.
  - Bindings are tracked per enclosing `function_item`; a rebinding replaces the name.
  - `modules` contains each file that roots the crate (a `use <crate>` or a crate-rooted path).
  - No new `SiteShape`/`LocateReason`/`AmbiguityReason`/`DynamicKind`; method calls and macros are
    unseen (no hit).
- `src/tenon/locate/rust_locate.py`: `locate_rust(change, root, config)` = `derive`, `scan_rust`,
  `resolve`; no policy copy.
- `src/tenon/locate/__init__.py`: export `RustLocateConfig`, `locate_rust`.
- `pyproject.toml`: add `tree-sitter-rust` to the core dependencies (same as the TS grammars).

## Out-of-scope

- CLI/config-file/bundle integration (the `rust-integration` aspect).
- Method-chain receiver tracking, macro expansion, re-export following, Cargo.toml parsing.
- New proof levels, ambiguity reasons or dynamic kinds.

## Acceptance criteria

- **AC1 — Config.** A valid crate loads; a blank/path/`::` crate is a named `ValueError`; the
  mappings are read-only copies.
- **AC2 — Rooting.** Simple, grouped, nested, `as`, crate-alias and `self` imports root the right
  names/chains; a glob roots only paths through the crate; a bare crate path roots; no crate import
  means `modules` is empty.
- **AC3 — Calls.** Associated calls and their aliases are rooted `CALL` hits with the canonical
  chain; an unrooted method call is not a hit; a non-SDK path is unrooted.
- **AC4 — Struct literals.** Inline and `let`-bound literals emit rooted `KEYWORD` field hits with
  the type chain, and with the enclosing call chain when passed to a rooted call; a rebinding does
  not inherit the old struct.
- **AC5 — Field access.** A tracked binding's field access is a rooted `ATTRIBUTE` hit with the type
  chain and the call chain when passed.
- **AC6 — Policy.** `locate_rust` returns the shared `LocateResult` for an operation and a component
  change: certain sites, `UNROOTED_RECEIVER`, `UNMAPPED_SYMBOL`, `MULTIPLE_CANDIDATES` and
  `NO_SITES`/`NO_SDK_IMPORT` as the shared rules decide.
- **AC7 — Files.** `target`/`vendor`/hidden directories are skipped; file order is deterministic.
- **AC8 — Offline.** No cargo/rustc subprocess, no network; fixture/temp `.rs` files only.

## Dependencies and sequencing

- First; `rust-integration` consumes it.
- Reuses `derive`, `resolve`, `Hit`, `Dynamic`, `ScanResult`, `SiteShape`; adds `tree-sitter-rust`.

## Open questions / risks

- A re-exported SDK crate is not followed; the config names the imported crate.
- A macro or builder-only call yields no site, not a guess.
- A local module sharing the crate name is a documented false positive.
