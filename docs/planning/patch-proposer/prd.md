# PRD: Patch proposer seam (T3)

- **Slug:** `patch-proposer`
- **Capability:** T3 in `docs/technical/CAPABILITY_ROADMAP.md`
- **Milestone:** M1.1 in `docs/ROADMAP.md` (Phase 1)
- **Status:** approved by the user for implementation on 2026-10-29
- **Card:** `docs/planning/_card/issue.md`

## Problem Statement

T1 (`src/tenon/detect/`, shipped 2026-10-26) says what changed. T2 (`src/tenon/locate/`, shipped
2026-10-29) says where it hurts, with a separate ambiguity list. Neither produces a patch, so T4
(the proof runner) has nothing to prove and the Phase 0 gate (M0.3: one real change, one real repo,
one patch that passes a real check) stays out of reach.

The temptation is to point a model at the change and the files and take what comes back. That is
the product `CLAUDE.md` explicitly forbids: a plausible patch with no proof. T3's job is the
opposite shape — a small, deterministic, reviewable edit set that is born unverified and says so.

**For whom:** T4 (primary consumer, applies the diff to a copy and runs checks), T5 (renders the PR
body), and the developer reading a flagged suggestion when no proof level could be reached.

## Goals & Success Metrics

1. **A proposal, never an application.** `propose()` returns a unified diff and a structured edit
   list; it writes no file and runs no command.
2. **Certain only.** Only `LocateResult.certain` sites are edited. Every ambiguous group is carried
   into the proposal as a skipped suggestion with its reason; nothing is silently dropped.
3. **Re-verified at propose time.** The source text at each site must still be the symbol the
   locator reported. A mismatch is refused per site as `STALE_SITE`, not edited blindly.
4. **Named non-results.** Kinds with no mechanical rule return `NO_RULE`; a change with no certain
   sites returns `NO_CERTAIN_SITES`; a change whose every site went stale returns `STALE_SITE`.
5. **Deterministic.** Same change, same locate result, same repo → byte-identical diff, ordered by
   path then line then column, independent of `PYTHONHASHSEED`.
6. **One seam, one rule.** A `Proposer` protocol with a deterministic `RuleProposer`. Tests use a
   recorded fake through the same protocol; no model call ships.

Measured by fixtures and assertions in `tests/propose/`, offline.

## User Personas & Scenarios

- **T4 prove.** "Give me a diff I can apply to an isolated copy, and tell me what was left out so I
  can label the result honestly."
- **T5 PR.** "Give me the diff and the skipped sites so the PR body can show both."
- **Developer.** Sees the proposed change and a list of places Tenon refused to touch.

Scenario: a vendor renames `Charge.amount` to `amount_cents`. T1 emits `renamed` (inferred). T2
finds `client.charges.create(amount=100)` certain and `build_payload(**row)` ambiguous. T3 proposes
a one-line diff for the keyword and lists the `**kwargs` site as `DYNAMIC_KWARGS`. T4 runs the
repo's tests. If they pass, the PR may say `TESTS_PASSED`; if not, the suggestion stays flagged.
T3 itself never claims either.

## Requirements

### Must have

- **M1 — Inputs.** `propose(change: Change, located: LocateResult, root: str | Path) -> Proposal`.
  No re-diff, no re-locate, no spec access.
- **M2 — One mechanical rule.** Field rename (`ChangeKind.RENAMED` with a field name: a property or
  parameter, not an endpoint): replace the old name with the new name. Every other kind returns
  `NO_RULE`. Endpoint renames, removals, required additions and type changes have no mechanical fix
  in this card.
- **M3 — Editable shapes.** `keyword`, `dict_key` and `attribute` sites are editable. A `call` site
  is not (a renamed method is a different rule); certain call sites are carried as skipped with
  `SHAPE_NOT_EDITABLE`.
- **M4 — Exact replacement.** A `keyword`/`attribute` edit replaces the identifier at its column; a
  `dict_key` edit replaces the quoted string including its quotes, preserving the quote character.
  No regex search-and-replace: the edited text is the located span or nothing.
- **M5 — Verification.** Before an edit is accepted, the text at `(line, column)` must equal the
  expected old spelling for that shape. Otherwise `STALE_SITE` for that site and no edit.
- **M6 — In-memory application.** Edits for a file are applied to the in-memory text from the bottom
  of the line upward, then bottom file line upward, so earlier offsets never shift later ones. The
  file on disk is never opened for writing.
- **M7 — Diff.** A unified diff per file with `a/<path>` and `b/<path>`, three lines of context,
  built with `difflib.unified_diff`, newline-stable and byte-stable. Nothing is emitted for a file
  with no surviving edits.
- **M8 — Skipped suggestions.** Every ambiguous group becomes a `Skipped` entry with its reason and
  candidates; uneditable shapes and stale sites join it. The list is ordered by path, line, column.
- **M9 — Named reasons.** `ProposalReason`: `NO_RULE`, `NO_CERTAIN_SITES`, `NO_EDITABLE_SITES`,
  `STALE_SITE`. Set only when `edits` is empty.
- **M10 — Seam.** `Proposer` protocol: `propose(change, located, root) -> tuple[Edit, ...]`.
  `RuleProposer` implements it. A `Proposal` is assembled from whichever proposer ran, so a future
  model proposer cannot bypass verification or the skipped list — those live in the assembly, not
  in the rule.
- **M11 — Serialization.** `Proposal.to_dict()/to_json()` with the change, edits, skipped, files and
  reason; byte-stable.

### Should have

- **S1 — `files` convenience.** The sorted list of repo-relative paths the diff touches, so T4 can
  scope a build/test command.
- **S2 — Round-trip.** `Proposal.to_dict()` is JSON-safe and contains no dataclass reprs or enums as
  objects.

### Nice to have

- **N1 — `line_text` on an edit**, for a PR body preview. Free from the same read.

## Data Model

```
Edit
  path: str            # repo-relative, forward slashes
  line: int            # 1-based
  column: int          # 1-based character column, from the locator
  shape: SiteShape     # keyword | dict_key | attribute
  old: str             # the located spelling
  new: str             # the renamed spelling

Skipped
  site: Site
  reason: SkipReason   # one of the ambiguity reasons, SHAPE_NOT_EDITABLE, STALE_SITE

Proposal
  change: Change
  edits: tuple[Edit, ...]
  skipped: tuple[Skipped, ...]
  files: tuple[str, ...]
  diff: str            # unified diff, "" when no edits
  reason: ProposalReason | None   # set iff edits == (); NO_RULE | NO_CERTAIN_SITES | NO_EDITABLE_SITES | STALE_SITE
  to_dict() / to_json()
```

Deliberately absent: an applied file, a patch command, a proof level, a model prompt. T3 proposes;
T4 executes; T5 labels.

## API Contract

```python
from tenon.detect import diff, parse
from tenon.locate import LocateConfig, locate
from tenon.propose import RuleProposer, propose

change = diff(parse(old, "v1"), parse(new, "v2")).changes[0]
located = locate(change, "path/to/repo", LocateConfig(sdk_package="stripe"))
proposal = propose(change, located, "path/to/repo", proposer=RuleProposer())
proposal.diff       # unified diff; "" when nothing is editable
proposal.edits      # structured edits
proposal.skipped    # suggestions with reasons
proposal.reason     # NO_RULE | NO_CERTAIN_SITES | NO_EDITABLE_SITES | STALE_SITE | None
proposal.to_json()  # byte-stable
```

No CLI, no exit codes, no file writes.

## Technical Considerations

- **Reuse, not new surface.** `Site`, `SiteShape`, `AmbiguityReason` and `LocateResult` come from
  `tenon.locate`; the only new vocabulary is `SkipReason` and `ProposalReason`, both closed sets.
- **The rename is inferred.** T1's `renamed` carries `confidence: "inferred"`. The proposal keeps
  that record unchanged (`proposal.change`), so T4/T5 can state it. T3 does not upgrade it.
- **Why not a model now.** A model proposer needs a prompt, a provider, a key and recorded fixtures;
  none of that is needed to unblock T4. The seam is the deliverable; the model is a later card with
  `CLAUDE.md` §4 (local/BYOK, opt-in) in force.
- **Trust boundaries.** Reading source at propose time is the only I/O. Paths come from T2 sites and
  are repo-relative; the renderer must reject absolute paths and `..` segments before reading.

## Risks & Open Questions

- **R2 (a verified PR still breaks production).** T3 adds no proof, so it cannot create a false
  `TESTS_PASSED`. It can create a wrong edit; the skipped list and `STALE_SITE` keep the failure
  visible, and T4 decides.
- **Inferred rename is wrong.** If T1 paired two unrelated names, the proposal renames a real call
  site. Mitigation: the proposal carries `confidence: "inferred"`; T4's tests are the arbiter. This
  is the same risk T1 accepted, surfaced rather than hidden.
- **Stale repository.** A file may change between locate and propose. `STALE_SITE` catches the
  common case (the symbol moved); it cannot catch semantic drift elsewhere on the line. T4 applies
  to a copy and runs checks.
- **Open question — duplicate sites.** The same keyword can be reported once per locator hit; edits
  are deduplicated by `(path, line, column, shape, old)`. If two different changes target the same
  span, a later card needs a conflict policy; this card handles one change at a time.

## Out of Scope

- Applying or executing anything (T4).
- Test execution, proof levels, `UNVERIFIED` causes (T4).
- Branch/PR creation (T5).
- Any model provider, prompt, key or network call.
- Mechanical fixes for removals, required additions, type changes, enum narrowing, schema changes.
- Endpoint renames and method renames.
- Formatting, import rewriting, multi-file refactors, codemods.
- A CLI (`tenon fix`, M1.4).

## Aspect Proposals (for `tech-plan`)

| Aspect | Boundary |
|---|---|
| `proposal-result` | `Edit`, `Skipped`, `Proposal`, `ProposalReason`, `SkipReason`, invariants, order, JSON. No file reads. |
| `rename-rule` | `RuleProposer`: kind gate, certain-site loop, shape filter, dedupe. Pure — no file reads; verification happens in assembly. |
| `diff-render` | Span verification (`STALE_SITE`), in-memory application per file, unified diff, path safety, skipped assembly, reason selection, `files`, determinism, `git apply --check`. No rule logic. |
