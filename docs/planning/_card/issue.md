# Card: feat/openapi-differ

- **Source:** FALLBACK — no GitHub issue (`gh issue view openapi-differ` → not found; `gh issue list` → empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T1 — Change detection** (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** M0.1 (`docs/ROADMAP.md`, Phase 0)
- **Branch:** `feat/openapi-differ/aliz`
- **Worktree:** `.claude/worktrees/feat-openapi-differ`

## Brief (verbatim from the `tenon-next` handoff)

> Build T1: a deterministic OpenAPI v1→v2 differ producing typed `Change` records, per M0.1 in
> `docs/ROADMAP.md` and the "Change record is the unit" decision in
> `docs/technical/ARCHITECTURE.md`. Acceptance tests: two spec versions diff into typed records for
> at least removed endpoints, renamed fields/methods, newly-required parameters, and type changes;
> unparseable or non-OpenAPI input returns a named refusal rather than an exception or a partial
> result; output is byte-stable for identical inputs. Test-first (`CLAUDE.md` constraint 7), fully
> offline with spec fixtures, no network and no model calls. Scaffold the Python package here too
> (`uv`, `src/tenon/detect/`, `tests/` per the planned layout) since nothing exists yet — but keep
> the diff to T1 alone; `tenon check`'s CLI, exit codes and JSON surface are M1.4, not this card.

## Constraints carried in from the repo

- `CLAUDE.md` §3: machine-readable sources only — a changelog paragraph is a hint, not a source.
- `CLAUDE.md` §7: test-first.
- `ARCHITECTURE.md`: "Change record is the unit" — everything downstream (T2 locate, T3 propose,
  T4 prove) consumes these records.
- `ARCHITECTURE.md`: determinism — same inputs, same records.
- Offline tests: no network, no model calls (`ARCHITECTURE.md` layout note).

## Attachments

None.

## Open question parked for this card

`CAPABILITY_ROADMAP.md` asks *which vendor/SDK is the first real case?* T1 does not need the answer
to be built (offline fixtures), but the first real spec pair should become a fixture when picked.
