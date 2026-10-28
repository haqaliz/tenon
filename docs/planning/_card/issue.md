# Card: feat/python-call-site-locator

- **Source:** FALLBACK — no GitHub issue (`gh issue list` → empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T2 — Call-site location (Python)** (`docs/technical/CAPABILITY_ROADMAP.md`)
- **Milestone:** M0.2 (`docs/ROADMAP.md`, Phase 0)
- **Branch:** `feat/python-call-site-locator/aliz`
- **Worktree:** `.claude/worktrees/feat-python-call-site-locator`

## Brief (verbatim from the `tenon-next` handoff)

> Build `src/tenon/locate/` (path reserved in `docs/technical/ARCHITECTURE.md`) so that, given a
> `Change` record from `src/tenon/detect/` and a Python repo root, it returns call sites with
> `file`, `line`, `column`, and a `certain`/`ambiguous` verdict — never a guessed one. Fix the
> spec→Python-symbol contract first: an explicit mapping plus safe inference from `operationId`
> and field/parameter names, with everything else reported as ambiguity. Use the stdlib `ast`
> module plus imports/`pyproject.toml` scanning; no new dependency unless `ast` genuinely cannot
> do it, and no language server.

## Acceptance tests named in the handoff

1. A rename record locates `client.things.create(foo=...)` at the right file and line in a fixture repo.
2. `**kwargs`, `getattr` and multi-candidate sites are returned as ambiguous with their
   candidates, never silently resolved.
3. Same input yields byte-stable JSON ordered by path then line.
4. Unresolvable cases surface the `AMBIGUOUS_CALL_SITE` cause from `docs/technical/ARCHITECTURE.md`.
5. Tests stay offline — no network, no model calls.

## Constraints carried in from the repo

- `CLAUDE.md` §1: execution decides, never the model — a locator never upgrades confidence.
- `CLAUDE.md` §7: test-first.
- `CAPABILITY_ROADMAP.md` T2 guardrail: "Ambiguity reported, never guessed".
- `ARCHITECTURE.md`: "Change record is the unit" — the locator consumes `Change` records and
  nothing else from T1.
- `ARCHITECTURE.md`: determinism — same inputs, same output, byte-stable.
- Risk register `R4` (call-site location wrong in dynamic code) and `R8` (language sprawl).
- `docs/technical/ARCHITECTURE.md`: T2 is the first stage behind `locate/`; T6 (TS/JS) reuses its
  contract, so keep the language behind a package boundary.

## Attachments

None.

## Open question parked for this card

T1 records carry HTTP identity only (`Location.pointer`, `method`, `path`) and no Python symbol.
The spec→Python-symbol contract is the design decision this card must settle before the locator
is written — see the PRD.

## Scope fence

Not this card: T3 propose, T4 prove, T5 PR, T6 TS/JS, the `tenon check` CLI surface (M1.4).
T2 stops at "here are the call sites, and here is what we refuse to claim".
