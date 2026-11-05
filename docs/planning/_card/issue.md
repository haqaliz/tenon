# Card: feat/typescript-locator

- **Source:** FALLBACK — no GitHub issue (`gh issue view typescript-locator` is not an issue id; `gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** **T6 TypeScript/JavaScript locator** (`docs/technical/CAPABILITY_ROADMAP.md:12`)
- **Milestone:** M2.1 (`docs/ROADMAP.md`)
- **Branch:** `feat/typescript-locator/aliz`
- **Worktree:** `.claude/worktrees/feat-typescript-locator`

## Brief

T2 locates Python call sites. T6 must do the same for TypeScript/JavaScript: given a T1 `Change` and
a repository root, return the same `LocateResult` — certain sites with file/line/column, ambiguity
groups with named reasons, and a named non-result — rooted in imports of the configured npm SDK
package.

The deep dig found a viable path: `tree-sitter` 0.26 with `tree-sitter-typescript` 0.23 and
`tree-sitter-javascript` 0.25 installs as wheels and parses TS/TSX/JS without Node. T2's `Hit`,
`Dynamic`, `ScanResult`, `Query`, `derive` and the entire `resolve` certainty policy are
language-agnostic; T6 needs a TypeScript scanner that emits the same evidence plus a TS config and a
`locate_ts` wrapper.

## Constraints carried in from the repo

- `CLAUDE.md` §1–2: execution decides; a location is certain only when the call chain is rooted in an
  SDK import; ambiguity is reported, never guessed.
- Same contract as T2 (`docs/technical/CAPABILITY_ROADMAP.md` T6): reuse `Site`, `SiteShape`,
  `AmbiguousGroup`, `LocateResult`, `LocateReason` and the existing certainty policy.
- `docs/technical/ARCHITECTURE.md` open question: "Language-server or tree-sitter for TypeScript
  location; decide at T6." The dig recommends tree-sitter in Python.
- Determinism: byte-stable JSON, ordered by `(path, line, column)`.
- Offline: committed fixture repos; no network, no Node, no `tsc`, no type inference.
- R8: each language behind its own fixtures.

## Scope fence

Not this card: new proposer rules for TS (T3 still edits `keyword`/`dict_key`/`attribute` spans),
T7 proof levels, MCP/probe (T8), the benchmark (T9), and raw-HTTP call sites with no SDK import.
