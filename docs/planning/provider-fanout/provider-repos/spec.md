# Spec: `provider-repos` (T10c)

- **Feature:** `provider-fanout`
- **PRD:** `docs/planning/provider-fanout/prd.md` (§ M1)
- **Boundary:** the repo-list loader. No CLI, pipeline or reporting.

## Problem slice

A provider needs one portable list of local customer checkouts next to the bundle, resolved the same
way the bundle's spec paths are, before any repo is touched. This aspect defines the file format,
the path resolution and the named errors.

## In-scope requirements

- `src/tenon/provider/repos.py`:
  - `load_repos(path: str | Path) -> tuple[Path, ...]`.
- Format: UTF-8 text, one local path per line.
  - Blank lines and lines whose stripped form starts with `#` are ignored.
  - Each kept line is stripped; the rest is the path (an inline `#` is a path character).
  - `~` expands; a relative path resolves against the repos file's parent; an absolute path stays.
  - Order is preserved; no sorting or dedup.
- Errors: a missing, unreadable or non-file path, non-UTF-8 bytes, or a list with no paths is a
  `ValueError` naming the repos file (CLI exit 2).
- The loader does **not** check that a listed path exists or is a directory; that is a per-repo
  failure at run time (PRD M2).
- Export `load_repos` from `tenon.provider`.

## Out-of-scope

- The CLI, the loop, the report, PR/remote.
- Installed/hosted discovery, parallel parsing, a JSON/TOML list format.

## Acceptance criteria

- **AC1 — Parse.** Comments, blanks and surrounding whitespace are ignored; the kept paths are in
  file order.
- **AC2 — Resolve.** Relative paths resolve against the file's parent; absolute paths stay;
  `~` expands; a nested relative path works.
- **AC3 — Empty.** An empty or comment-only file is a `ValueError` naming the file.
- **AC4 — Unreadable.** A missing file, a directory, or non-UTF-8 bytes is a `ValueError` naming the
  file.
- **AC5 — No existence check.** A listed path that does not exist is returned, not rejected.
- **AC6 — Determinism.** The same file loads identically; no clock/network.

## Dependencies and sequencing

- First; `provider-fanout` consumes it.
- Reuses only `pathlib`; no new dependency.

## Open questions / risks

- Duplicate paths run twice; the list is the operator's input and is not deduped.
- A path containing a leading/trailing space cannot be represented; acceptable for checkouts.
- `resolve()` follows symlinks, matching the bundle's spec resolution.
