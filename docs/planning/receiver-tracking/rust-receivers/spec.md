# Spec: `rust-receivers` (T12a)

- **Feature:** `receiver-tracking`
- **PRD:** `docs/planning/receiver-tracking/prd.md` (§ M2, M4)
- **Boundary:** the Rust scanner's receiver evidence and chain hits. No config/CLI plumbing.

## Problem slice

A Rust client object built with `Client::new`/`default`, an annotation or a configured factory must
root its method chain as `Type.member...`, so the shared policy can locate the operation.

## In-scope requirements

- `scan_rust(root, sdk_package, receivers=None)` (default `{}`); `locate_rust` passes
  `config.receivers`.
- Evidence (per function; a rebinding replaces; no evidence clears):
  - `let name = Type::new(...)`, `let name = <crate>::Type::new(...)` and
    `let name = Type::default()` bind `name -> (Type,)` (the canonical chain minus the constructor).
  - `let name: <crate>::Type = ...` / `let name: Type = ...` binds the annotated type (aliases and
    the crate root resolved).
  - `let name = factory(...)` whose source/canonical dotted chain is a `receivers` key binds the
    mapped type chain (`"A.B" -> ("A","B")`); both `factory` and `<crate>::factory` match.
  - The existing struct-literal binding (type + fields) remains.
- Receiver chains:
  - A method call on a bound receiver emits a rooted `CALL` with `(Type, ..., method)`; an
    intermediate method call emits its prefix too (`client.charges()` -> `("Client","charges")`).
  - A field access on a bound receiver emits a rooted `ATTRIBUTE` with `(Type, ..., field)`.
  - A chain on an untracked receiver keeps the current behavior (no certain hit / unrooted evidence).
  - No duplicate hits for the same node/chain (the shared result dedupes sites, but the scan should
    be clean).
- The shared `derive`/`resolve` is unchanged; no new shapes/reasons/dynamic kinds.

## Out-of-scope

- Full type inference, generics/return types, interprocedural flow.
- Other languages; config plumbing.

## Acceptance criteria

- **AC1 — Construction.** `Client::new`, `crate::Client::new` and `Client::default` bind the type.
- **AC2 — Annotation.** `let c: Client` and `let c: crate::Client` bind the type; an alias resolves.
- **AC3 — Factory map.** A `receivers` key matches the source and canonical chains; the mapped type
  is used; an unmapped factory is not evidence.
- **AC4 — Chain.** `client.charges().create(...)` emits `(Client,charges,create)` and the
  intermediate `(Client,charges)`; a field access emits `(Client,field)`; an untracked chain is not
  certain.
- **AC5 — Rebind.** A `let` with new evidence replaces the name; a `let` without evidence clears it.
- **AC6 — Policy/regression.** The existing Rust locate/scan tests stay green; no new vocabulary.

## Dependencies and sequencing

- Depends on `receiver-config`; `go-receivers` follows independently.

## Open questions / risks

- `Type::new`/`default` are the only implicit constructors; other factories need the mapping.
- A local type named like the mapped type is a documented false positive.
