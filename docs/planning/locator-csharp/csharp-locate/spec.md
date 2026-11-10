# Spec: `csharp-locate` (T11c)

- **Feature:** `locator-csharp`
- **PRD:** `docs/planning/locator-csharp/prd.md` (§ M1–M3)
- **Boundary:** the C# config, scanner and locate wrapper. No CLI/config-file/bundle.

## Problem slice

A C# repo's SDK calls, object-initializer properties and property access must become the same
evidence the shared certainty policy understands: rooted `Hit`s with a canonical chain, plus honest
dynamics. This aspect adds the C# config, the tree-sitter scan and the wrapper.

## In-scope requirements

- `src/tenon/locate/csharp_config.py`:
  - `CSharpLocateConfig(sdk_package: str, operations={}, fields={})`, frozen/slots, mapping proxies.
  - `sdk_package` is a dotted namespace `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*`; a
    blank/path/`::` is a named `ValueError`.
- `src/tenon/locate/csharp_scan.py`: `scan_csharp(root, sdk_package) -> ScanResult`.
  - `.cs` files sorted; skip `bin`, `obj`, `.git` and hidden directories.
  - Parse with `tree-sitter-c-sharp`; emit `Hit`/`Dynamic` evidence only.
  - Usings: `using <root>;`, `using <root>.<sub>;` and `global using` root the namespace; an alias
    (`using Charge = <root>.Charge;`) maps the alias to the simple type name; `using static` roots no
    type names. A file with a root using is a module.
  - Type roots: a fully qualified `<root>[.<sub>].Type` and a simple `Type` used while a root using
    is in scope are rooted; the canonical chain is the simple type name (subnamespaces dropped).
  - Calls: a member call on a rooted type (`ChargeService.Create`) or on a tracked binding
    initialized with `new <rooted type>(...)` (`var service = new ChargeService(); service.Create`)
    is a `CALL` hit with the canonical chain and `rooted=True`. A fluent/property chain on an
    untracked value (`client.Charges.Create`) is an unrooted `CALL` with the chain after the base,
    never certain.
  - Object initializers: `new <rooted type> { Property = value }` emits `KEYWORD` hits for the
    property names with the type chain. An initializer inline in a rooted call, or a local binding
    passed to a rooted call, also emits the properties with the call chain. Bindings are tracked per
    method/constructor/accessor/local function; a rebinding replaces the name.
  - Property access (`options.AmountCents`) through a tracked binding is an `ATTRIBUTE` hit, with the
    type chain and, when passed to a rooted call, the call chain.
  - `modules` contains each file with a root using or a rooted qualified type.
  - No new `SiteShape`/`LocateReason`/`AmbiguityReason`/`DynamicKind`; `dynamic`, reflection and
    `using static` are unseen (no hit).
- `src/tenon/locate/csharp_locate.py`: `locate_csharp(change, root, config)` = `derive`, `scan_csharp`,
  `resolve`; no policy copy.
- `src/tenon/locate/__init__.py`: export `CSharpLocateConfig`, `locate_csharp`; add csharp to
  `LOCATE_TYPES`.
- `pyproject.toml`: add `tree-sitter-c-sharp` to the core dependencies.

## Out-of-scope

- CLI/config-file/bundle integration (the `csharp-integration` aspect).
- Fluent-chain receiver tracking, `using static` resolution, reflection, `dynamic`, generics
  inference, `csproj` parsing.
- New proof levels, ambiguity reasons or dynamic kinds.

## Acceptance criteria

- **AC1 — Config.** A valid namespace loads; a blank/path/`::` namespace is a named `ValueError`;
  the mappings are read-only copies.
- **AC2 — Usings.** Root, subnamespace, `global using`, alias and `using static` directives root the
  right names; a file without a root using and without a qualified root type is not a module.
- **AC3 — Calls.** Rooted type calls and tracked `new` bindings are `CALL` hits with canonical
  chains; a fluent chain is an unrooted hit, never certain; a non-SDK member access is unrooted.
- **AC4 — Initializers.** Inline and bound initializers emit rooted `KEYWORD` property hits with the
  type chain, and with the call chain when passed; a rebinding does not inherit the old type.
- **AC5 — Property access.** A tracked binding's property access is a rooted `ATTRIBUTE` hit with
  the type chain and the call chain when passed.
- **AC6 — Policy.** `locate_csharp` returns the shared `LocateResult` for operation and component
  changes: certain sites, `UNROOTED_RECEIVER`, `UNMAPPED_SYMBOL`, `MULTIPLE_CANDIDATES` and
  `NO_SITES`/`NO_SDK_IMPORT` as the shared rules decide.
- **AC7 — Files.** `bin`/`obj`/hidden directories are skipped; file order is deterministic.
- **AC8 — Offline.** No `dotnet`/`csc` subprocess, no network; fixture/temp `.cs` files only.

## Dependencies and sequencing

- First; `csharp-integration` consumes it.
- Reuses `derive`, `resolve`, `Hit`, `Dynamic`, `ScanResult`, `SiteShape`; adds
  `tree-sitter-c-sharp`.

## Open questions / risks

- A simple name from an imported namespace roots local types with the same name (documented).
- A fluent chain or `dynamic`/`using static` site yields no certain site, not a guess.
- Subnamespace collisions are resolved to the simple type name; the provider can use a fully
  qualified mapping.
