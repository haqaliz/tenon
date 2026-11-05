# Card: feat/cli

- **Source:** FALLBACK — no GitHub issue (`gh issue view cli` is not an issue id; `gh issue list` is empty).
- **Owner:** aliz
- **Type:** feat
- **Capability:** M1.4 in `docs/ROADMAP.md` (no T-id; exposes T1–T5)
- **Milestone:** M1.4 — `tenon check` / `tenon fix`
- **State:** shipped 2026-11-05 (`src/tenon/cli/`, 870 tests)
- **Branch:** `feat/cli/aliz`
- **Worktree:** `.claude/worktrees/feat-cli`

## Brief

T1–T5 are a library with no entry point. Add `src/tenon/cli/` and a `tenon` console script with two
commands:

- `tenon check <repo> --old SPEC --new SPEC` runs detect -> locate and reports the affected call
  sites, certain and ambiguous, with file and line.
- `tenon fix <repo> --old SPEC --new SPEC` runs detect -> locate -> propose -> prove, prints the
  candidate diff and the `ProofResult`, and with `--open-pr` calls `write_pr`.

Both accept `--json` for a byte-stable machine report. Exit codes reflect the result: `0` when the
required proof was reached (or the check is clean), `1` when it was not, `2` on usage or bad input.
No traceback ever reaches the terminal.

## Constraints carried in from the repo

- `CLAUDE.md` §1–2: only what ran is labelled; `UNVERIFIED` is never presented as verified.
- `CLAUDE.md` §5: `tenon fix` never writes the user's checkout by default and never merges;
  `--open-pr` goes through T5, which refuses a dirty tree, the default branch and an existing branch.
- `docs/technical/ARCHITECTURE.md` CLI shape: `tenon check`, `tenon fix [--require LEVEL]
  [--proposer CMD] [--open-pr]`.
- `docs/ROADMAP.md` M1.4: exit codes reflect proof; JSON output byte-stable.
- `tenon.toml` `[locate]` already loads through `tenon.locate.load_config`; the CLI may extend the
  file, but the in-memory API stays the real contract.
- Offline: tests must not call `gh`, a model, or the network. The CLI is tested as a subprocess or
  by calling `main(argv)`.

## Scope fence

Not this card: `tenon probe` (T8), T6/T7, new proposer rules, a hosted app, releases.
