# Spec: `pr-result` (T5 PR writer)

- **Feature:** `pr-writer`
- **PRD:** `docs/planning/pr-writer/prd.md` (§ Data Model, M1, M9, M13)
- **Boundary:** the answer types only. No rendering, no filesystem, no subprocess, no network.

## Problem slice

T5 needs one honest answer type before any text is rendered or any remote is touched: what was
opened, or exactly why nothing was opened. T4's `ProofResult` says what ran; `PrResult` says what was
done with that proof. Keeping this vocabulary closed and serialisable lets M1.4 map outcomes to exit
codes without parsing prose.

## In-scope requirements

- `PrStatus`: `OPENED`, `REFUSED`.
- `PrRefusal`: `NOT_A_GIT_REPO`, `DIRTY_CHECKOUT`, `NO_REMOTE`, `UNKNOWN_DEFAULT_BRANCH`, `NO_PATCH`,
  `DEFAULT_BRANCH`, `BRANCH_EXISTS`, `UNVERIFIED_NOT_ALLOWED`, `PATCH_DID_NOT_APPLY`,
  `COPY_FAILED`, `COMMIT_FAILED`, `PUSH_FAILED`, `PR_FAILED`.
- `PrDraft`: `title`, `body`, `branch`, `commit_message`; frozen; non-empty.
- `PrResult`: `status`, `level`, `draft`, `url`, `refusal`, `detail`; frozen.
- Invariants: `OPENED` → `url` is a non-empty string and `refusal is None`; `REFUSED` → `refusal` is
  set and `url is None`; `detail` is `""` unless a refusal carries command output.
- String coercion for `status`, `refusal` and `level`, matching `ProofResult`.
- `to_dict()` / `to_json()`: JSON primitives only, byte-stable key order, no enum or dataclass reprs.
- `PrDraft.to_dict()` / `to_json()` for the dry-run path.

## Out-of-scope

- Rendering the title, body or branch (see `pr-render`).
- Git, `gh`, subprocess, temp directories (see `pr-write`).
- Adding a new `ProofLevel` or `ProofCause` (T4/T7).
- A merge status, a score, a duration or a confidence.

## Acceptance criteria

- **AC1 — Closed vocabularies.** `PrStatus` has exactly two values and `PrRefusal` exactly thirteen,
  in the order above. Every value constructs from its string and appears as a plain string in JSON.
- **AC2 — Draft invariants.** A `PrDraft` with an empty title, body, branch or commit message raises
  `ValueError`; a valid draft is frozen and its sequence-free fields are unchanged on access.
- **AC3 — Result invariants.** `OPENED` without a URL raises; `OPENED` with a refusal raises;
  `REFUSED` without a refusal raises; `REFUSED` with a URL raises. A valid result accepts `detail=""`.
- **AC4 — Coercion.** `PrResult(status="OPENED", level="TESTS_PASSED", ...)` and
  `PrResult(..., refusal="DIRTY_CHECKOUT")` produce enums, not strings.
- **AC5 — JSON contract.** `to_dict()` keys are exactly `status`, `level`, `draft`, `url`, `refusal`,
  `detail`; `draft` keys are exactly `title`, `body`, `branch`, `commit_message`; `to_json()` is
  byte-identical across `PYTHONHASHSEED` values.
- **AC6 — Detail.** The default is `""`; a refusal can carry a capped command tail.

## Dependencies and sequencing

- Depends on `tenon.prove.ProofLevel` (shipped).
- First aspect: `pr-render` and `pr-write` import these types. Land this before either.

## Open questions / risks

- Adding a `PrRefusal` value is a contract change; the test suite pins the list so the addition is
  deliberate.
- `detail` is free text; it must never be parsed for control flow.
