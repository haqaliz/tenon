# Spec: `csharp-receivers` (T12b)

- **Feature:** `receivers-rest`
- **PRD:** `docs/planning/receivers-rest/prd.md` (§ M2, M5)
- **Boundary:** the C# scanner's receiver evidence and chain hits.

## In-scope requirements

- `scan_csharp(root, sdk_package, receivers=None)` (default `{}`); `locate_csharp` passes
  `config.receivers`.
- Evidence (per method/constructor/accessor/local function; a rebinding replaces; no evidence
  clears):
  - `new Type(...)` / `new Type(...) { ... }` binds the type (the existing `new` tracking).
  - An explicit type on a declaration (`ChargeClient client = ...`, and `var client = ...` with a
    `new`/factory) binds the type.
  - A configured factory (`StripeClient.Create`) whose source/canonical dotted chain matches a
    `receivers` key binds the mapped type.
  - The existing static/`new`-binding and object-initializer behavior remains.
- Receiver chains:
  - `client.Charges.Create(...)` emits a rooted `CALL` with `(Client,Charges,Create)` and the
    intermediate `(Client,Charges)`; `client.Charges` emits the attribute.
  - A chain on an untracked receiver keeps the current behavior.
  - A local receiver wins over a same-name type.
- No new shapes/reasons/dynamic kinds.

## Out-of-scope

- Fluent chains through an untracked value; `dynamic`/reflection; return types.
- Config plumbing; the other languages.

## Acceptance criteria

- **AC1 — Evidence.** `new`, an explicit type and a configured factory bind; an unmapped factory is
  not evidence; a rebinding replaces/clears.
- **AC2 — Chain.** `client.Charges.Create(...)` emits the full and intermediate chains; a field
  access emits the attribute; an untracked chain is unchanged.
- **AC3 — Policy/regression.** A mapped operation/component locates through `locate_csharp`; the
  existing C# tests stay green.
