# Tenon: Architecture

Design intent, not built behavior. Nothing is implemented yet.

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

## Layout (planned)

```
src/tenon/
  detect/     T1: spec parsers, differ, Change records
  locate/     T2/T6: per-language call-site finders
  propose/    T3: proposer seam, rule-based mechanical fixes
  prove/      T4/T7: working-copy runner, proof levels
  pr/         T5: branch and PR writer
  probe/      T8: agent run against an API or MCP server
  corpus/     T9: benchmark records
  cli/        tenon check | fix | probe
tests/        offline; fixture repos and specs; no network, no model calls
```

## Key decisions

- **Change record is the unit.** Everything downstream consumes typed Change records, so adding a
  source (MCP, SDK metadata) does not touch locate or prove.
- **Proof is a ladder, chosen by the user.** `--require TESTS_PASSED|CHARACTERIZED|REPLAYED|TYPES_BUILD_ONLY`.
  If the required level cannot be reached, the result is a flagged suggestion, not a verified PR.
- **Isolated working copy.** Patches apply to a copy; the user's checkout is never modified.
- **Determinism.** Detection, location and PR text are deterministic for the same inputs. The
  model proposer is the only non-deterministic piece, behind an injectable seam; tests use
  recorded proposals.
- **BYOK / local only** for any model use. Keys come from the environment and are never committed.
- **UNVERIFIED causes** (draft): `NO_MACHINE_READABLE_CHANGE`, `AMBIGUOUS_CALL_SITE`,
  `NO_TESTS_FOUND`, `TESTS_FAILED_BEFORE` (baseline already red), `PATCH_DID_NOT_APPLY`,
  `REQUIRED_LEVEL_UNREACHED`.
- **Baseline first.** Run the user's checks before patching, so a red baseline is reported as such
  and not blamed on the patch.

## CLI shape (target)

`tenon check <repo> --old SPEC --new SPEC` lists affected call sites.
`tenon fix <repo> --old SPEC --new SPEC [--require LEVEL] [--proposer CMD] [--open-pr]`
`tenon probe <api-or-mcp-url> [--agent CMD]`

Exit 0 when the required proof level was reached, 1 otherwise, 2 on usage. Never a traceback.

## Open questions

- Language-server or tree-sitter for TypeScript location; decide at T6.
- Where TypeScript analysis lives if the core stays Python (subprocess helper vs. separate package).
- PyPI distribution name: `tenon` is taken; `tenonhq` was free when checked.
