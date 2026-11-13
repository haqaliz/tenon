# Card: feat/webhook-runs

- **Source:** FALLBACK — no GitHub issue (`gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T10 Provider layer** — follow-up slice: **webhook-triggered runs** (T10f)
- **Milestone:** after v0.1.0; the last T10e follow-up
- **Branch:** `feat/webhook-runs/aliz`
- **Worktree:** `.claude/worktrees/feat-webhook-runs`

## Brief

The T10e service verifies `POST /webhooks/github` with the HMAC and records the delivery, but it
never queues a run. A provider still posts every migration to `POST /runs` by hand.

T10f adds **webhook-triggered runs**:
- an operator mapping from a GitHub event (and optional action) to a registered bundle, e.g.
  `--trigger installation_repositories.added=demo.json` or `--trigger push=demo.json`;
- on a verified, matching delivery, the service queues a normal installed-fan-out run through the
  existing store/worker, with the delivery id as the run's idempotency key;
- the webhook response names the queued run; a non-matching event is still recorded only;
- a trigger requires the webhook secret; bundle names are confined to `--bundles`; the mapping is
  operator CLI config, not bundle content (a bundle cannot auto-run itself);
- no new pipeline, proof, PR or merge behavior.

## Constraints carried in from the repo

- T10e's `Api`/`RunStore`/`Worker` and the HMAC webhook are the base; extend, do not fork.
- The bundle name validation (`resolve_bundle`) and the store's unique idempotency key are the
  dedupe/confine seams.
- Stdlib only; offline tests (a signed body, a temp store, no network).
- `CLAUDE.md` §1–5: no merge/default branch, secrets never logged/stored.

## Scope fence

Not this card: per-repo targeting/filters, bundle-level trigger declarations, a trigger UI/API,
new GitHub event semantics, auto-merge, a web UI, multi-tenant triggers.
