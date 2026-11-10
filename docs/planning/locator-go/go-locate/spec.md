# Spec: `go-locate` (T11b)

- **Feature:** `locator-go`
- **PRD:** `docs/planning/locator-go/prd.md` (§ M1–M3)
- **Boundary:** the Go config, scanner and locate wrapper. No CLI/config-file/bundle.

## Problem slice

A Go repo's SDK calls and composite-literal fields must become the same evidence the shared
certainty policy understands: rooted `Hit`s with a canonical chain, plus honest dynamics. This
aspect adds the Go config, the tree-sitter scan and the wrapper.

## In-scope requirements

- `src/tenon/locate/go_config.py`:
  - `GoLocateConfig(sdk_package: str, package_name: str | None = None, operations={}, fields={})`,
    frozen/slots, mapping proxies.
  - `sdk_package`: a Go import root, non-empty, no whitespace, no leading/trailing `/`, no `::`.
  - `package_name`: optional Go identifier `[A-Za-z_][A-Za-z0-9_]*`.
- `src/tenon/locate/go_scan.py`: `scan_go(root, sdk_package, package_name=None) -> ScanResult`.
  - `.go` files sorted; skip `vendor`, `testdata`, `.git` and hidden directories.
  - Parse with `tree-sitter-go`; emit `Hit`/`Dynamic` evidence only.
  - Imports: a path equal to the root or `root + "/..."` roots the package; canonical prefix = the
    path after the root. An alias wins; otherwise infer the package name: the last segment if a
    valid non-version identifier, the segment before a trailing `vN`, a trailing `-go` stripped,
    else no default. `package_name` overrides the root's inference. `_`/`.` imports root no names.
  - Calls: a selector rooted through a package (`stripe.Charge.New`, `charge.New`) ->
    `SiteShape.CALL`, symbol = the leaf, chain = canonical, `rooted=True`. A selector on a local
    value (`client.Charges.New`) -> an unrooted `CALL` with the chain after the base (for
    `UNROOTED_RECEIVER`), never certain.
  - Composite literals of a rooted type -> `SiteShape.KEYWORD` hits for the keyed element keys.
    An inline literal in a rooted call, or a local `var`/`:=` binding passed to a rooted call, also
    emits the fields with the call chain. A `var` with only a rooted type is a binding for field
    access.
  - Field access (`params.Amount`) through a tracked binding -> `SiteShape.ATTRIBUTE`, rooted, with
    the type chain and (when passed to a rooted call) the call chain.
  - Bindings are tracked per enclosing function (`function_declaration`, `method_declaration`,
    `func_literal`); a rebinding replaces the name.
  - `modules` contains each file that imports the root.
  - No new `SiteShape`/`LocateReason`/`AmbiguityReason`/`DynamicKind`; dot imports and reflection are
    unseen (no hit).
- `src/tenon/locate/go_locate.py`: `locate_go(change, root, config)` = `derive`, `scan_go`,
  `resolve`; no policy copy.
- `src/tenon/locate/__init__.py`: export `GoLocateConfig`, `locate_go`; add go to `LOCATE_TYPES`.
- `pyproject.toml`: add `tree-sitter-go` to the core dependencies.

## Out-of-scope

- CLI/config-file/bundle integration (the `go-integration` aspect).
- Method-chain receiver tracking, dot-import resolution, reflection, generics inference, `go.mod`
  parsing.
- New proof levels, ambiguity reasons or dynamic kinds.

## Acceptance criteria

- **AC1 — Config.** A valid import root/package name loads; a blank/whitespace/leading-slash root or
  a bad package name is a named `ValueError`; the mappings are read-only copies.
- **AC2 — Imports.** The root, a subpackage, an alias, `_` and `.` imports, grouped imports and both
  string forms root the right names; the inference covers `vN` and `-go`; `package_name` overrides
  the root; a file without the root import is not a module.
- **AC3 — Calls.** Rooted package calls (root and subpackage) are `CALL` hits with canonical chains;
  a method chain is an unrooted hit, never certain; a non-SDK selector is unrooted.
- **AC4 — Composite literals.** Inline and bound literals emit rooted `KEYWORD` key hits with the
  type chain, and with the call chain when passed; a `var` type-only binding supports field access;
  a rebinding does not inherit the old type.
- **AC5 — Field access.** A tracked binding's field access is a rooted `ATTRIBUTE` hit with the type
  chain and the call chain when passed.
- **AC6 — Policy.** `locate_go` returns the shared `LocateResult` for operation and component
  changes: certain sites, `UNROOTED_RECEIVER`, `UNMAPPED_SYMBOL`, `MULTIPLE_CANDIDATES` and
  `NO_SITES`/`NO_SDK_IMPORT` as the shared rules decide.
- **AC7 — Files.** `vendor`/`testdata`/hidden directories are skipped; file order is deterministic.
- **AC8 — Offline.** No `go`/`gofmt` subprocess, no network; fixture/temp `.go` files only.

## Dependencies and sequencing

- First; `go-integration` consumes it.
- Reuses `derive`, `resolve`, `Hit`, `Dynamic`, `ScanResult`, `SiteShape`; adds `tree-sitter-go`.

## Open questions / risks

- A package clause the heuristic cannot infer needs `package_name` or an alias.
- A method chain or dot import yields no certain site, not a guess.
- A local variable named like the package alias is a documented false positive.
