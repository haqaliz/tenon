# Spec: `python-receivers` (T12b)

- **Feature:** `receivers-rest`
- **PRD:** `docs/planning/receivers-rest/prd.md` (§ M3, M5)
- **Boundary:** the Python scanner's receiver evidence and chain hits.

## In-scope requirements

- `scan(root, sdk_package, receivers=None)` (default `{}`); `locate` passes `config.receivers`.
- Evidence (per function; a rebinding replaces; no evidence clears):
  - `client = stripe.Client(...)` / `client = Client(...)` where the call's callee is rooted through
    the SDK: bind the canonical chain (`Client`).
  - `client: stripe.Client = ...` / `client: Client = ...` annotation: bind the annotation chain.
  - `client = make_client(...)` whose source/canonical dotted chain matches a `receivers` key: bind
    the mapped type.
  - The existing alias/import behavior stays.
- Receiver chains:
  - `client.charges.create(...)` emits a rooted `CALL` with `(Client,charges,create)` and the
    intermediate `(Client,charges)`; a `client.charges` attribute emits the prefix.
  - Keyword arguments on the tracked call are attributed to its chain (the shared `_argument`
    behavior).
  - A chain on an untracked receiver keeps the current behavior.
- No new shapes/reasons/dynamic kinds.

## Out-of-scope

- Return types, `getattr`, interprocedural flow, branch-sensitive reassignment.
- Config plumbing; the other languages.

## Acceptance criteria

- **AC1 — Evidence.** A rooted constructor call, an annotation and a configured factory bind; an
  unmapped factory is not evidence; a rebinding replaces/clears.
- **AC2 — Chain.** `client.charges.create(...)` emits the full and intermediate chains; kwargs are
  attributed; an untracked chain is unchanged.
- **AC3 — Policy/regression.** A mapped operation/component locates through `locate`; the existing
  Python tests stay green.
