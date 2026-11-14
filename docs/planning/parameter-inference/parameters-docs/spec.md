# Spec: `parameters-docs` (T12d)

- **Feature:** `parameter-inference`
- **PRD:** `docs/planning/parameter-inference/prd.md` (§ M7)
- **Boundary:** docs/status, the end-to-end typed-parameter fixture/test and the final suite.

## In-scope requirements

- A `tenon check` end-to-end test on a temp repo whose `create_charge(client: StripeClient, amount)`
  function uses the parameter receiver; a component rename locates the site (exit 1).
- README language paragraphs (a sentence on typed-parameter inference), ARCHITECTURE, the CHANGELOG
  `Unreleased`, the capability roadmap T12d row/section and the status surfaces.
- The full suite green.

## Out-of-scope

- New scanner behavior; a committed fixture (the test builds a temp repo).

## Acceptance criteria

- **AC1 — End-to-end.** The typed-parameter Python repo locates the `amount` site through `tenon check`.
- **AC2 — Docs.** README/ARCHITECTURE/CHANGELOG/roadmap describe parameter inference and the
  per-function limits.
- **AC3 — Regression.** All prior tests and the new scanner tests green.
