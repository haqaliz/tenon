# Spec: `inference-docs` (T12c)

- **Feature:** `receiver-inference`
- **PRD:** `docs/planning/receiver-inference/prd.md` (§ M7)
- **Boundary:** docs/status, the end-to-end helper fixture/test and the final suite. No scanner
  internals.

## In-scope requirements

- A `tenon check` end-to-end test on a temp repo whose `make_client() -> acme.client.StripeClient`
  helper wraps the client and whose `client.charges.create(amount=...)` is located by a component
  rename; exit 1 and the site.
- README language paragraphs (a sentence on annotated return-type helpers), ARCHITECTURE, the
  CHANGELOG `Unreleased`, the capability roadmap T12c row/section and the status surfaces.
- The full suite green.

## Out-of-scope

- New scanner behavior; a committed fixture (the test builds a temp repo).

## Acceptance Criteria

- **AC1 — End-to-end.** The helper-typed Python repo locates the `amount` site through `tenon check`.
- **AC2 — Docs.** README/ARCHITECTURE/CHANGELOG/roadmap describe annotated return inference and the
  same-file limits.
- **AC3 — Regression.** All prior tests and the new scanner tests green.
