# Spec: `release-examples` (v0.1.0)

- **Feature:** `release-v0.1.0`
- **PRD:** `docs/planning/release-v0.1.0/prd.md` (§ M3, M6)
- **Boundary:** the quickstart files, `examples/README.md`, the README links and the example tests.

## In-scope requirements

- `examples/quickstart/old.yaml` and `new.yaml`: the `Charge.amount` -> `Charge.amount_cents`
  component rename.
- `examples/quickstart/bundle.json`: provider `acme`, migration `amount-cents`, source openapi,
  language python, `old`/`new` relative, `locate.sdk_package: acme.client`, `require: TESTS_PASSED`,
  `check: ["python3", "-c", "import acme.billing"]`.
- `examples/README.md`: the copy-paste `tenon check`, `tenon fix` and `tenon provider migrate`
  commands against `tests/fixtures/repos/proof-basic`, with the expected site/diff/proof and exit
  codes; a note that the fixture is read-only and no PR is opened without `--open-pr`.
- README: a version badge (`0.1.0`), `CHANGELOG.md`/`examples/README.md`/`docs/RELEASE.md` links.
- Tests: the bundle loads via `load_bundle`; the specs exist; the check command locates the
  `amount` site (exit 1); the provider bundle runs to `TESTS_PASSED`/exit 0; the README links exist.

## Out-of-scope

- A per-language example matrix, new fixtures, the release tag.

## Acceptance criteria

- **AC1 — Bundle.** `load_bundle` accepts the example bundle; old/new resolve; the check is the
  documented command.
- **AC2 — Check/Fix.** `tenon check` reports `amount` (exit 1); `tenon fix` proposes the rename and
  proves `TESTS_PASSED` (exit 0) without writing the fixture.
- **AC3 — Provider.** `tenon provider migrate ... --bundle examples/quickstart/bundle.json` exits 0
  with `TESTS_PASSED`.
- **AC4 — Docs/links.** `examples/README.md` has the commands and expectations; the README links to
  the changelog/examples/release checklist.
- **AC5 — Regression.** All prior tests green.
