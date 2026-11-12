# Spec: `ts-receivers` (T12b)

- **Feature:** `receivers-rest`
- **PRD:** `docs/planning/receivers-rest/prd.md` (§ M4, M5)
- **Boundary:** the TypeScript/JavaScript scanner's receiver evidence and chain hits.

## In-scope requirements

- `scan_ts(root, sdk_package, receivers=None)` (default `{}`); `locate_ts` passes
  `config.receivers`.
- Evidence (per function/scope; a rebinding replaces; no evidence clears):
  - `const client = new StripeClient(...)` / `new Client(...)`: bind the canonical type chain.
  - `const client: Client = ...` / `const client: StripeClient = ...`: bind the annotation type.
  - `const client = StripeClient.create(...)` / `makeClient(...)` whose source/canonical dotted chain
    matches a `receivers` key: bind the mapped type.
  - The existing import/alias behavior stays.
- Receiver chains:
  - `client.charges.create({...})` emits a rooted `CALL` with `(Client,charges,create)` and the
    intermediate `(Client,charges)`; a `client.charges` member access emits the prefix.
  - Object keys on the tracked call are attributed to its chain (the shared argument behavior).
  - A chain on an untracked receiver keeps the current behavior.
- No new shapes/reasons/dynamic kinds.

## Out-of-scope

- Return types, computed member access, interprocedural flow, branch-sensitive reassignment.
- Config plumbing; the other languages.

## Acceptance criteria

- **AC1 — Evidence.** `new`, an annotation and a configured factory bind; an unmapped factory is not
  evidence; a rebinding replaces/clears.
- **AC2 — Chain.** `client.charges.create({...})` emits the full and intermediate chains; object keys
  are attributed; an untracked chain is unchanged.
- **AC3 — Policy/regression.** A mapped operation/component locates through `locate_ts`; the existing
  TS/JS tests stay green.
