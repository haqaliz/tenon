# The Tenon benchmark corpus

`corpus.jsonl` is the labelled history of changes Tenon proposed and proved: one JSON object per
line, one record per change. Each record carries the change, the proposed diff, the proof result,
the PR (if any), the human outcome, the date and the evidence. The record id is the first 12 hex of
the canonical `(repo, commit, change, diff)` hash, so an outcome update never changes it.

## Record and update

Record a `tenon fix --json` run once the change and its proof are known:

```sh
tenon corpus record --from fix.json --repo https://github.com/o/r --commit SHA \
  --outcome local_only --date 2026-11-07 --corpus corpus.jsonl \
  --evidence docs/planning/.../evidence.md --notes "focused test, no PR"
```

The outcome is a human statement, not a Tenon inference. Update it by id after a human merge,
reject, close or incident:

```sh
tenon corpus outcome --corpus corpus.jsonl --id <id> --outcome merged \
  --outcome-url https://github.com/o/r/pull/1
```

The six outcomes are `pending`, `merged`, `rejected`, `closed`, `incident` and `local_only`.
Only `merged`, `rejected`, `closed` and `incident` are known outcomes; `local_only` and `pending`
are not successes and never count in the merge rate. The merge rate is `merged / known` and is
`n/a` when no known outcome exists.

## The public seed

`corpus.jsonl` holds the two public M0.3 cases, both `local_only` with `TESTS_PASSED`:

| id | repository | commit | change | proof | recorded | evidence |
|---|---|---|---|---|---|---|
| `5a2911fd0e6e` | `fighthealthinsurance/fighthealthinsurance` | `56e69cf` | 3-edit rename on `POST /v1/checkout/sessions` | `TESTS_PASSED` (focused test) | 2026-11-02 | `docs/planning/m0-3-first-real-case/evidence.md` |
| `066e7e77f93d` | `yezz123/stripe-template` | `9d9178c` | 2-file rename on `POST /v1/checkout/sessions` | `TESTS_PASSED` (offline subset) | 2026-10-31 | `docs/planning/m0-3-real-case/evidence.md` |

**No merge outcomes yet; merge rate n/a.** Both cases are local checks: neither opened a PR, so
there is nothing to count as merged, rejected, closed or incident. The report says `known = 0` and
`rate = n/a`; that is the honest state, not a 100% success rate. The first human-merged PR is the
first datum.

## Report

```sh
tenon corpus report --corpus docs/benchmark/corpus.jsonl
tenon corpus report --corpus docs/benchmark/corpus.jsonl --json
```

The text report has one row per proof level and the outcome counts; the JSON report is byte-stable
(`total`, `by_level`, `outcomes`).

## Local and opt-in

The corpus is local by default: nothing is uploaded and no network or GitHub call is made. You
choose whether to commit your corpus. This public seed is only the two cases already published in
the committed evidence; a user's corpus and code stay on their machine unless they share them.
