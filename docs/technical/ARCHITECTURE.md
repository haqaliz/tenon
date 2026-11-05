# Tenon: Architecture

Design intent. **T1 (detect), T2 (locate, Python), T3 (propose), T4 (prove), T5 (PR), T6
(locate, TypeScript/JavaScript) and the `tenon check` / `tenon fix` CLI are implemented** under
`src/tenon/detect/`, `src/tenon/locate/`, `src/tenon/propose/`, `src/tenon/prove/`, `src/tenon/pr/`
and `src/tenon/cli/`. The probe and the later stages are not.

## Pipeline

```
API change source (OpenAPI v1 -> v2 | MCP schema | SDK metadata)
        |
        v
  T1 detect   ---->  typed Change records
        |
        v
  T2 locate   ---->  call sites in the user's repo (file, line, confidence)
        |
        v
  T3 propose  ---->  candidate diff (rules first; BYOK model optional)
        |
        v
  T4 prove    ---->  apply in isolated copy, run user's checks -> proof level
        |
        v
  T5 PR       ---->  branch + PR that states the proof level
```

## Layout

```text
src/tenon/
  detect/     T1: spec parsers, differ, Change records      <- built
  locate/     T2/T6: per-language call-site finders       <- built (Python + TS/JS)
  propose/    T3: proposer seam, rule-based mechanical fixes  <- built (rename only)
  prove/      T4/T7: working-copy runner, proof levels     <- built (TESTS_PASSED)
  pr/         T5: branch and PR writer                     <- built (git + gh seam)
  probe/      T8: agent run against an API or MCP server
  corpus/     T9: benchmark records
  cli/        tenon check | fix                           <- built
tests/        offline; fixture repos and specs; no network, no model calls
```

## Key decisions

- **Change record is the unit.** Everything downstream consumes typed Change records, so adding a
  source (MCP, SDK metadata) does not touch locate or prove.
- **One certainty policy, per-language scanners.** T2 and T6 both emit `Hit`/`Dynamic`/`ScanResult`
  evidence and call the same `resolve` rule table. Python parses with `ast`, TypeScript/JavaScript
  with tree-sitter; neither runs the scanned code, needs Node, or infers types.
- **Proof is a ladder, chosen by the user.** `--require TESTS_PASSED|CHARACTERIZED|REPLAYED|TYPES_BUILD_ONLY`.
  If the required level cannot be reached, the result is a flagged suggestion, not a verified PR.
- **Isolated working copy and clone.** T4 patches a copy; T5 clones the clean checkout to a temporary
  directory and commits there. The user's checkout is never modified or given a Tenon branch.
- **The PR is a seam, not a merge.** T5 renders a deterministic draft, pushes only the new branch and
  opens the PR through `GitGhRemote` (`git` + `gh`). It never force-pushes, never pushes the base
  branch and has no merge path. `UNVERIFIED` refuses by default; `allow_unverified=True` opens a
  draft that names the cause.
- **Determinism.** Detection, location and PR text are deterministic for the same inputs. The
  model proposer is the only non-deterministic piece, behind an injectable seam; tests use
  recorded proposals.
- **BYOK / local only** for any model use. Keys come from the environment and are never committed.
- **UNVERIFIED causes** (shipped): `NO_PATCH_PROPOSED`, `PATCH_DID_NOT_APPLY`, `NO_TESTS_FOUND`,
  `TESTS_FAILED_BEFORE` (baseline already red), `TESTS_FAILED_AFTER`, `CHECK_TIMED_OUT`,
  `COPY_FAILED`. T7 adds the weaker levels and their causes.
- **A thin CLI with honest exit codes.** `tenon check` and `tenon fix` parse, configure, compose and
  render; they add no detection or proof logic. `check` exits 0 clean / 1 affected or unanalyzable /
  2 usage; `fix` exits 0 required proof / 1 not / 2 usage. `--json` is one byte-stable object;
  `fix` prints unless `--open-pr`, which delegates to T5. No traceback.
- **Baseline first.** Run the user's checks before patching, so a red baseline is reported as such
  and not blamed on the patch.

## CLI

`tenon check <repo> --old SPEC --new SPEC [--language python|ts] [--json]` lists affected call sites
and exits 0 when clean, 1 when a site or an unanalyzable repository is found.
`tenon fix <repo> --old SPEC --new SPEC [--language python|ts] [--require LEVEL] [--check CMD]
[--open-pr] [--json]` proposes, proves and prints the diff; `--open-pr` delegates to T5.
`tenon probe <api-or-mcp-url> [--agent CMD]` (T8, not built).

`tenon.toml` provides `[locate]` (`language`, `sdk_package`, mappings) and `[tenon]` defaults; flags
override. Exit 2 on usage or bad input. Never a traceback.

## Open questions

- T6 follow-ups: `tsconfig`/workspace path aliases, JSX attribute sites, and a T4 copy policy for
  `node_modules` so a real TS `npm test` can run in the proof copy.
- T5 follow-ups: fork remotes, cleanup of a branch left by a failed PR call, and submodule/LFS
  content in the clone. The current writer refuses a dirty tree and never force-pushes.
- PyPI distribution name: `tenon` is taken; `tenonhq` was free when checked.
