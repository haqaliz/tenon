# Spec: `go-receivers` (T12a)

- **Feature:** `receiver-tracking`
- **PRD:** `docs/planning/receiver-tracking/prd.md` (§ M3, M4)
- **Boundary:** the Go scanner's receiver evidence and chain hits. No config/CLI plumbing.

## Problem slice

A Go client object built with a composite literal, a type annotation or a configured factory must
root its selector chain as `Type.member...`, so the shared policy can locate the operation.

## In-scope requirements

- `scan_go(root, sdk_package, package_name=None, receivers=None)` (default `{}`); `locate_go` passes
  `config.receivers`.
- Evidence (per function; a rebinding replaces; no evidence clears):
  - `var name *pkg.Type`, `var name pkg.Type`, `name := &pkg.Type{...}`, `var name = pkg.Type{...}`
    bind the type chain (the existing package/alias/root logic; a pointer is unwrapped).
  - `name := pkg.Factory(...)` / `var name = pkg.Factory(...)` whose source dotted chain
    (`stripe.NewClient`) or canonical chain (`NewClient`) is a `receivers` key binds the mapped type
    chain.
  - The existing composite-literal field binding remains.
- Receiver chains:
  - A selector call on a bound receiver emits a rooted `CALL` with `(Type, ..., member)`; an
    intermediate selector/call emits its prefix too (`client.Charges` -> `("Client","Charges")`,
    `client.Charges()` -> `("Client","Charges")`).
  - A field access on a bound receiver emits a rooted `ATTRIBUTE` with `(Type, ..., field)`.
  - A method chain on an untracked value keeps the current unrooted behavior.
  - A local receiver binding wins over a package alias with the same name.
- The shared `derive`/`resolve` is unchanged; no new shapes/reasons/dynamic kinds.

## Out-of-scope

- Full type inference, generics/return types, interprocedural flow, reflection.
- Other languages; config plumbing.

## Acceptance criteria

- **AC1 — Annotation.** `var c *pkg.Type` and `var c pkg.Type` bind the type; a pointer unwraps.
- **AC2 — Composite.** `&pkg.Type{}` and `pkg.Type{}` bind the type (and fields, as before).
- **AC3 — Factory map.** A `receivers` key matches the source (`stripe.NewClient`) and canonical
  (`NewClient`) chains; the mapped type is used; an unmapped factory is not evidence.
- **AC4 — Chain.** `client.Charges.New(...)` emits `(Client,Charges,New)` and the intermediate
  `(Client,Charges)`; a field access emits the attribute; an untracked chain is not certain.
- **AC5 — Rebind.** A `var`/`:=` with new evidence replaces the name; a declaration without evidence
  clears it.
- **AC6 — Policy/regression.** The existing Go locate/scan tests stay green; no new vocabulary.

## Dependencies and sequencing

- Depends on `receiver-config`; independent of `rust-receivers`.

## Open questions / risks

- The root package's selector chain drops the package name (`NewClient`); the mapping accepts both
  the source and canonical forms.
- A local variable named like the package alias is a documented false positive; a tracked receiver
  wins.
