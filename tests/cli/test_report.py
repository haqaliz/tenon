"""Exit codes, text reports and JSON envelopes for the CLI report surface."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tenon.cli.report import (
    _LEVEL_RANK,
    FixResult,
    check_exit,
    fix_exit,
    render_check_json,
    render_check_text,
    render_error,
    render_fix_json,
    render_fix_text,
)
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    AmbiguousGroup,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
)
from tenon.propose import Edit, Proposal, ProposalReason, SkipReason, Skipped
from tenon.prove import (
    PROOF_RANK,
    CheckResult,
    ProofCause,
    ProofLevel,
    ProofResult,
    ProofStage,
    proof_rank,
)
from tenon.pr import PrDraft, PrRefusal, PrResult, PrStatus

POINTER = "#/components/schemas/Charge/properties"
COMMAND = ("python", "-m", "pytest", "-q")


def a_change(**overrides):
    values = {
        "kind": ChangeKind.RENAMED,
        "location": Location(
            pointer=POINTER,
            method="post",
            path="/v1/checkout/sessions",
        ),
        "before": "payment_method_types",
        "after": "allowed_payment_method_types",
    }
    values.update(overrides)
    return Change(**values)


def a_site(**overrides):
    values = {
        "path": "acme/billing.py",
        "line": 7,
        "column": 30,
        "shape": SiteShape.KEYWORD,
        "symbol": "payment_method_types",
    }
    values.update(overrides)
    return Site(**values)


def an_ambiguous_group(**overrides):
    values = {
        "reason": AmbiguityReason.DYNAMIC_KWARGS,
        "symbol": "payment_method_types",
        "candidates": (
            a_site(path="acme/a.py", line=3, column=1),
            a_site(path="acme/b.py", line=9, column=4, shape=SiteShape.CALL),
        ),
    }
    values.update(overrides)
    return AmbiguousGroup(**values)


def a_locate(*, change=None, certain=(), ambiguous=(), reason=None):
    if not certain and not ambiguous and reason is None:
        reason = LocateReason.NO_SITES
    return LocateResult(
        change=change if change is not None else a_change(),
        certain=certain,
        ambiguous=ambiguous,
        reason=reason,
    )


def an_edit(**overrides):
    values = {
        "path": "acme/billing.py",
        "line": 7,
        "column": 30,
        "shape": SiteShape.KEYWORD,
        "old": "payment_method_types",
        "new": "allowed_payment_method_types",
    }
    values.update(overrides)
    return Edit(**values)


def a_proposal(*, edits=(), skipped=(), diff="", reason=None):
    if not edits and reason is None:
        reason = ProposalReason.NO_RULE
    return Proposal(
        change=a_change(),
        edits=edits,
        skipped=skipped,
        diff=diff,
        reason=reason,
    )


def a_check(**overrides):
    values = {
        "kind": "baseline",
        "command": COMMAND,
        "returncode": 0,
        "timed_out": False,
    }
    values.update(overrides)
    return CheckResult(**values)


def a_passed_proof(**overrides):
    values = {
        "level": ProofLevel.TESTS_PASSED,
        "cause": None,
        "baseline": a_check(kind="baseline"),
        "after": a_check(kind="after"),
        "patch_applied": True,
    }
    values.update(overrides)
    return ProofResult(**values)


def an_unverified_proof(cause=ProofCause.NO_TESTS_FOUND, **overrides):
    values = {
        "level": ProofLevel.UNVERIFIED,
        "cause": cause,
        "baseline": None,
        "after": None,
        "patch_applied": False,
    }
    values.update(overrides)
    return ProofResult(**values)


STAGE_FOR_LEVEL = {
    ProofLevel.TESTS_PASSED: ProofStage.TESTS,
    ProofLevel.CHARACTERIZED: ProofStage.CHARACTERIZE,
    ProofLevel.REPLAYED: ProofStage.REPLAY,
    ProofLevel.TYPES_BUILD_ONLY: ProofStage.BUILD,
}


def a_proof_for(level):
    """A green proof of ``level`` with the matching stage's baseline/after checks."""
    stage = STAGE_FOR_LEVEL[level]
    baseline = a_check(kind="baseline", stage=stage)
    after = a_check(kind="after", stage=stage)
    return a_passed_proof(
        level=level,
        baseline=baseline,
        after=after,
        checks=(baseline, after),
    )


def a_two_stage_proof(*, test_after=0, cause=None):
    """A green build plus a tests stage; a cause makes the result UNVERIFIED."""
    build_baseline = a_check(
        kind="baseline", command=("python", "-c", "import acme"), stage=ProofStage.BUILD
    )
    test_baseline = a_check(kind="baseline", command=COMMAND, stage=ProofStage.TESTS)
    build_after = a_check(
        kind="after", command=("python", "-c", "import acme"), stage=ProofStage.BUILD
    )
    test_after_check = a_check(
        kind="after", command=COMMAND, returncode=test_after, stage=ProofStage.TESTS
    )
    checks = (build_baseline, test_baseline, build_after, test_after_check)
    if cause is not None:
        return an_unverified_proof(
            cause=cause,
            baseline=test_baseline,
            after=test_after_check,
            patch_applied=True,
            checks=checks,
        )
    return a_passed_proof(
        baseline=test_baseline,
        after=test_after_check,
        checks=checks,
    )


def a_draft(**overrides):
    values = {
        "title": "[TESTS_PASSED] tenon: renamed",
        "body": "body",
        "branch": "tenon/renamed-1234abcd",
        "commit_message": "tenon: renamed",
    }
    values.update(overrides)
    return PrDraft(**values)


def an_opened_pr(**overrides):
    values = {
        "status": PrStatus.OPENED,
        "level": ProofLevel.TESTS_PASSED,
        "draft": a_draft(),
        "url": "https://github.com/example/repo/pull/7",
    }
    values.update(overrides)
    return PrResult(**values)


def a_refused_pr(**overrides):
    values = {
        "status": PrStatus.REFUSED,
        "level": ProofLevel.TESTS_PASSED,
        "draft": a_draft(),
        "refusal": PrRefusal.DIRTY_CHECKOUT,
        "detail": "working tree has uncommitted changes",
    }
    values.update(overrides)
    return PrResult(**values)


def a_fix_result(**overrides):
    values = {
        "change": a_change(),
        "locate": a_locate(certain=(a_site(),)),
        "proposal": a_proposal(
            edits=(an_edit(),),
            diff="--- a/acme/billing.py\n+++ b/acme/billing.py\n",
        ),
        "proof": a_passed_proof(),
        "pr": None,
    }
    values.update(overrides)
    return FixResult(**values)


# Spec AC1: a certain site makes the check fail.
def test_check_exit_is_one_for_a_certain_site():
    assert check_exit([a_locate(certain=(a_site(),))]) == 1


# Spec AC1: an ambiguity group also makes the check fail.
def test_check_exit_is_one_for_an_ambiguous_group():
    assert check_exit([a_locate(ambiguous=(an_ambiguous_group(),))]) == 1


# Spec AC1: no sites and an unsupported change are clean.
@pytest.mark.parametrize(
    "reason", [LocateReason.NO_SITES, LocateReason.UNSUPPORTED_CHANGE_KIND]
)
def test_check_exit_is_zero_for_clean_reasons(reason):
    assert check_exit([a_locate(reason=reason)]) == 0


# Spec AC1: a repository that could not be analyzed is not clean.
@pytest.mark.parametrize(
    "reason", [LocateReason.NO_SDK_IMPORT, LocateReason.OPERATION_NOT_MAPPED]
)
def test_check_exit_is_one_for_unanalyzable_reasons(reason):
    assert check_exit([a_locate(reason=reason)]) == 1


# Spec AC1: no changes means nothing to report.
def test_check_exit_is_zero_without_results():
    assert check_exit([]) == 0


# Spec AC1: one dirty result makes the whole check fail.
def test_check_exit_requires_every_result_to_be_clean():
    results = [a_locate(reason=LocateReason.NO_SITES), a_locate(certain=(a_site(),))]

    assert check_exit(results) == 1


# Spec AC2: zero changes is clean even with no results.
def test_fix_exit_is_zero_when_nothing_changed():
    assert fix_exit(0, [], ProofLevel.TESTS_PASSED) == 0


# Spec AC2: a passed proof with no requested PR is clean.
def test_fix_exit_is_zero_for_a_passed_proof_without_a_pr():
    assert fix_exit(1, [a_fix_result()], ProofLevel.TESTS_PASSED) == 0


# Spec AC2: an unverified proof does not meet the default requirement.
def test_fix_exit_is_one_for_an_unverified_proof_under_tests_passed():
    result = a_fix_result(proof=an_unverified_proof())

    assert fix_exit(1, [result], ProofLevel.TESTS_PASSED) == 1


# Spec AC2: UNVERIFIED meets UNVERIFIED.
def test_fix_exit_is_zero_for_an_unverified_proof_under_unverified():
    result = a_fix_result(proof=an_unverified_proof())

    assert fix_exit(1, [result], ProofLevel.UNVERIFIED) == 0


# Spec AC2: a requested PR must have opened.
def test_fix_exit_is_one_for_a_refused_pr():
    result = a_fix_result(pr=a_refused_pr())

    assert fix_exit(1, [result], ProofLevel.TESTS_PASSED) == 1


# Spec AC2: an opened PR keeps the clean exit.
def test_fix_exit_is_zero_for_an_opened_pr():
    result = a_fix_result(pr=an_opened_pr())

    assert fix_exit(1, [result], ProofLevel.TESTS_PASSED) == 0


# Spec AC2 / PRD M5: a non-empty change set with no proposals is not clean.
def test_fix_exit_is_one_for_changes_without_results():
    assert fix_exit(1, [], ProofLevel.TESTS_PASSED) == 1


# Spec AC2: every result must meet the requirement, not only the last one.
def test_fix_exit_requires_every_proof_to_meet_the_requirement():
    results = [a_fix_result(), a_fix_result(proof=an_unverified_proof())]

    assert fix_exit(2, results, ProofLevel.TESTS_PASSED) == 1


# Spec AC2: a refused PR among opened ones still fails the run.
def test_fix_exit_requires_every_requested_pr_to_open():
    results = [a_fix_result(pr=an_opened_pr()), a_fix_result(pr=a_refused_pr())]

    assert fix_exit(2, results, ProofLevel.TESTS_PASSED) == 1


# Spec AC7/M9: the report ranks with the shipped five-level ladder.
def test_level_rank_is_the_shipped_ladder():
    assert _LEVEL_RANK == PROOF_RANK
    assert {level: proof_rank(level) for level in ProofLevel} == PROOF_RANK


# Spec AC7/M9: every proof level is compared with every requirement by rank.
@pytest.mark.parametrize("level", list(ProofLevel))
@pytest.mark.parametrize("require", list(ProofLevel))
def test_fix_exit_compares_every_level_with_every_requirement(level, require):
    proof = (
        an_unverified_proof()
        if level is ProofLevel.UNVERIFIED
        else a_proof_for(level)
    )
    result = a_fix_result(proof=proof)
    expected = 0 if proof_rank(level) >= proof_rank(require) else 1

    assert fix_exit(1, [result], require) == expected


# Spec: the PR field is optional and defaults to no request.
def test_fix_result_defaults_to_no_pr_request():
    result = FixResult(
        change=a_change(),
        locate=a_locate(certain=(a_site(),)),
        proposal=a_proposal(
            edits=(an_edit(),),
            diff="--- a/acme/billing.py\n+++ b/acme/billing.py\n",
        ),
        proof=a_passed_proof(),
    )

    assert result.pr is None


CHECK_TEXT = """\
renamed POST /v1/checkout/sessions: payment_method_types -> allowed_payment_method_types
acme/billing.py:7:30  keyword  payment_method_types
acme/checkout.py:42:9  call  payment_method_types

endpoint_removed #/paths/~1v1~1charges
no affected sites (NO_SITES)

2 changes, 2 certain sites, 0 ambiguity groups
"""


def an_untouched_change():
    return a_change(
        kind=ChangeKind.ENDPOINT_REMOVED,
        location=Location(pointer="#/paths/~1v1~1charges"),
        before=None,
        after=None,
    )


# Spec AC3: the whole check report is one pinned deterministic text.
def test_check_text_is_the_golden_text():
    results = [
        a_locate(
            certain=(
                a_site(path="acme/checkout.py", line=42, column=9, shape=SiteShape.CALL),
                a_site(),
            )
        ),
        a_locate(change=an_untouched_change(), reason=LocateReason.NO_SITES),
    ]

    assert render_check_text(results) == CHECK_TEXT


# Spec AC3: one ambiguity line names the reason, symbol and every candidate.
def test_check_text_renders_an_ambiguity_group():
    text = render_check_text([a_locate(ambiguous=(an_ambiguous_group(),))])

    assert text == (
        "renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types\n"
        "ambiguous DYNAMIC_KWARGS: payment_method_types at "
        "acme/a.py:3:1, acme/b.py:9:4\n"
        "\n"
        "1 change, 0 certain sites, 1 ambiguity group\n"
    )


# Spec AC3: a reason with no sites is named instead of an empty block.
def test_check_text_renders_a_reason_with_no_sites():
    text = render_check_text(
        [a_locate(reason=LocateReason.UNSUPPORTED_CHANGE_KIND)]
    )

    assert text == (
        "renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types\n"
        "no affected sites (UNSUPPORTED_CHANGE_KIND)\n"
        "\n"
        "1 change, 0 certain sites, 0 ambiguity groups\n"
    )


# Spec AC3: blocks follow the input order.
def test_check_text_keeps_the_input_order():
    results = [
        a_locate(change=an_untouched_change(), reason=LocateReason.NO_SITES),
        a_locate(certain=(a_site(),)),
    ]

    text = render_check_text(results)

    assert text.index("no affected sites") < text.index("acme/billing.py:7:30")


# Spec AC3 / S1: zero results still carry the summary.
def test_check_text_without_results_is_only_the_summary():
    assert render_check_text([]) == "0 changes, 0 certain sites, 0 ambiguity groups\n"


# Spec AC3: exactly one trailing newline and no colour.
def test_check_text_has_one_trailing_newline_and_no_colour():
    text = render_check_text([a_locate(certain=(a_site(),))])

    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "\x1b[" not in text


# Spec AC3: container values use the same canonical spelling as the PR summary.
def test_check_text_renders_container_values_canonically():
    change = a_change(before={"b": 2, "a": 1}, after=[2, {"z": 1, "a": 0}])

    text = render_check_text([a_locate(change=change, reason=LocateReason.NO_SITES)])

    assert text.startswith(
        'renamed POST /v1/checkout/sessions: {"a":1,"b":2} -> [2,{"a":0,"z":1}]\n'
    )


FIX_DIFF = (
    "--- a/acme/billing.py\n"
    "+++ b/acme/billing.py\n"
    "@@ -7 +7 @@\n"
    "-    payment_method_types=payment_method_types,\n"
    "+    payment_method_types=allowed_payment_method_types,\n"
)

FIX_TEXT = """\
renamed POST /v1/checkout/sessions: payment_method_types -> allowed_payment_method_types
--- a/acme/billing.py
+++ b/acme/billing.py
@@ -7 +7 @@
-    payment_method_types=payment_method_types,
+    payment_method_types=allowed_payment_method_types,
Proof: TESTS_PASSED
Command: python -m pytest -q
Baseline exit: 0
After exit: 0
Skipped: none

1 change, 1 proposal, 1 passed, 0 characterized, 0 replayed, 0 build-only, 0 unverified, 0 PRs opened, 0 PRs refused
"""


# Spec AC4: the whole passed fix report is one pinned deterministic text.
def test_fix_text_is_the_golden_text():
    result = a_fix_result(
        proposal=a_proposal(edits=(an_edit(),), diff=FIX_DIFF),
    )

    assert render_fix_text([result]) == FIX_TEXT


# Spec AC4: UNVERIFIED names the cause and the missing checks.
def test_fix_text_names_the_unverified_cause_and_missing_checks():
    result = a_fix_result(
        proposal=a_proposal(reason=ProposalReason.NO_RULE),
        proof=an_unverified_proof(),
    )

    text = render_fix_text([result])

    assert text == (
        "renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types\n"
        "No patch: NO_RULE\n"
        "Proof: UNVERIFIED\n"
        "Cause: NO_TESTS_FOUND\n"
        "Command: not run\n"
        "Baseline exit: not run\n"
        "After exit: not run\n"
        "Skipped: none\n"
        "\n"
        "1 change, 0 proposals, 0 passed, 0 characterized, 0 replayed, "
        "0 build-only, 1 unverified, 0 PRs opened, 0 PRs refused\n"
    )


# Spec AC4: every skipped site is listed with its reason.
def test_fix_text_lists_the_skipped_sites():
    skipped = (
        Skipped(
            site=a_site(path="acme/other.py", line=3, column=1, symbol="x"),
            reason=SkipReason.DYNAMIC_KWARGS,
        ),
        Skipped(
            site=a_site(path="acme/third.py", line=5, column=2, symbol="y"),
            reason=SkipReason.STALE_SITE,
        ),
    )
    result = a_fix_result(
        proposal=a_proposal(edits=(an_edit(),), skipped=skipped, diff=FIX_DIFF)
    )

    text = render_fix_text([result])

    assert "Skipped: acme/other.py:3:1  x  DYNAMIC_KWARGS\n" in text
    assert "Skipped: acme/third.py:5:2  y  STALE_SITE\n" in text


# Spec AC4: an opened PR is the URL.
def test_fix_text_renders_an_opened_pr_url():
    text = render_fix_text([a_fix_result(pr=an_opened_pr())])

    assert "PR: https://github.com/example/repo/pull/7\n" in text


# Spec AC4: a refusal names the cause and the detail.
def test_fix_text_renders_a_refused_pr():
    text = render_fix_text([a_fix_result(pr=a_refused_pr())])

    assert "PR refused: DIRTY_CHECKOUT: working tree has uncommitted changes\n" in text


# Spec AC4: a refusal without detail is still one honest line.
def test_fix_text_renders_a_refusal_without_detail():
    result = a_fix_result(pr=a_refused_pr(refusal=PrRefusal.NOT_A_GIT_REPO, detail=""))

    text = render_fix_text([result])

    assert "PR refused: NOT_A_GIT_REPO\n" in text


# Plan edge case: a killed check renders as timed out.
def test_fix_text_renders_a_timeout_as_timed_out():
    proof = a_passed_proof(
        baseline=a_check(returncode=None, timed_out=True),
    )

    text = render_fix_text([a_fix_result(proof=proof)])

    assert "Baseline exit: timed out\n" in text
    assert "After exit: 0\n" in text


# Spec AC7/S2: every configured stage is grouped in runner order with both exits.
def test_fix_text_shows_every_stage_command_and_exits():
    text = render_fix_text([a_fix_result(proof=a_two_stage_proof())])

    build = text.index("BUILD: python -c import acme")
    build_baseline = text.index("Baseline exit: 0", build)
    build_after = text.index("After exit: 0", build_baseline)
    tests = text.index("TESTS: python -m pytest -q")
    tests_baseline = text.index("Baseline exit: 0", tests)
    tests_after = text.index("After exit: 0", tests_baseline)

    assert (
        build
        < build_baseline
        < build_after
        < tests
        < tests_baseline
        < tests_after
    )
    assert text.count("Baseline exit:") == 2
    assert text.count("After exit:") == 2


# Spec AC4/AC7: a red test after a green build shows both exits and the cause.
def test_fix_text_shows_the_green_build_before_a_red_test():
    proof = a_two_stage_proof(test_after=1, cause=ProofCause.TESTS_FAILED_AFTER)
    text = render_fix_text([a_fix_result(proof=proof)])

    assert "Proof: UNVERIFIED\n" in text
    assert "Cause: TESTS_FAILED_AFTER\n" in text
    build = text.index("BUILD: python -c import acme")
    tests = text.index("TESTS: python -m pytest -q")
    assert build < text.index("After exit: 0", build) < tests
    assert text.index("After exit: 1", tests) > tests


# Spec AC4 / S1: the summary counts every result and every PR outcome.
def test_fix_text_summary_counts_results_and_prs():
    results = [
        a_fix_result(pr=an_opened_pr()),
        a_fix_result(pr=a_refused_pr(), proof=an_unverified_proof()),
    ]

    text = render_fix_text(results)

    assert text.endswith(
        "2 changes, 2 proposals, 1 passed, 0 characterized, 0 replayed, "
        "0 build-only, 1 unverified, 1 PR opened, 1 PR refused\n"
    )


# Spec AC7: every level has its own count in the one summary line.
def test_fix_text_summary_counts_every_level():
    results = [
        a_fix_result(proof=a_proof_for(level))
        for level in (
            ProofLevel.TESTS_PASSED,
            ProofLevel.CHARACTERIZED,
            ProofLevel.REPLAYED,
            ProofLevel.TYPES_BUILD_ONLY,
        )
    ] + [a_fix_result(proof=an_unverified_proof())]

    text = render_fix_text(results)

    assert text.endswith(
        "5 changes, 5 proposals, 1 passed, 1 characterized, 1 replayed, "
        "1 build-only, 1 unverified, 0 PRs opened, 0 PRs refused\n"
    )


# Spec AC4: a run without a PR request has no PR line at all.
def test_fix_text_omits_the_pr_line_without_a_request():
    text = render_fix_text([a_fix_result()])

    assert "PR:" not in text
    assert "PR refused" not in text


# Spec AC4: exactly one trailing newline and no colour.
def test_fix_text_has_one_trailing_newline_and_no_colour():
    text = render_fix_text([a_fix_result()])

    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "\x1b[" not in text


# Spec AC4: blocks follow the input order.
def test_fix_text_keeps_the_input_order():
    first = a_fix_result(
        change=an_untouched_change(),
        proof=an_unverified_proof(),
    )
    second = a_fix_result()

    text = render_fix_text([first, second])

    assert text.index("endpoint_removed") < text.index("renamed")


def a_json(**overrides):
    values = {
        "sort_keys": True,
        "ensure_ascii": False,
        "separators": (",", ":"),
    }
    values.update(overrides)
    return json.dumps(**values)


def assert_json_primitives(value):
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            assert_json_primitives(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_json_primitives(item)
        return
    assert value is None or isinstance(value, (str, int, float, bool))


# Spec AC5: the check envelope composes the shipped LocateResult dictionaries.
def test_check_json_is_one_object_with_the_shipped_dicts():
    results = [
        a_locate(certain=(a_site(),)),
        a_locate(change=an_untouched_change(), reason=LocateReason.NO_SITES),
    ]
    expected = (
        a_json(
            obj={
                "command": "check",
                "results": [result.to_dict() for result in results],
                "summary": {"changes": 2, "certain": 1, "ambiguous": 0},
            }
        )
        + "\n"
    )

    assert render_check_json(results) == expected


# Spec AC5: the check envelope has exactly the three stated keys.
def test_check_json_has_the_exact_top_level_keys():
    payload = json.loads(render_check_json([a_locate(reason=LocateReason.NO_SITES)]))

    assert set(payload) == {"command", "results", "summary"}
    assert set(payload["summary"]) == {"changes", "certain", "ambiguous"}


# Spec AC5: the fix envelope composes every shipped result dictionary.
def test_fix_json_is_one_object_with_the_shipped_dicts():
    result = a_fix_result(pr=an_opened_pr())
    expected = (
        a_json(
            obj={
                "command": "fix",
                "results": [
                    {
                        "change": result.change.to_dict(),
                        "locate": result.locate.to_dict(),
                        "proposal": result.proposal.to_dict(),
                        "proof": result.proof.to_dict(),
                        "pr": result.pr.to_dict(),
                    }
                ],
                "summary": {
                    "changes": 1,
                    "proposals": 1,
                    "passed": 1,
                    "characterized": 0,
                    "replayed": 0,
                    "build_only": 0,
                    "unverified": 0,
                    "prs_opened": 1,
                    "prs_refused": 0,
                },
            }
        )
        + "\n"
    )

    assert render_fix_json([result]) == expected


# Spec AC5: a missing PR is null, and a refused PR keeps its shipped dictionary.
def test_fix_json_renders_null_and_refused_prs():
    no_pr = a_fix_result()
    refused = a_fix_result(pr=a_refused_pr(), proof=an_unverified_proof())

    payload = json.loads(render_fix_json([no_pr, refused]))

    assert set(payload) == {"command", "results", "summary"}
    assert payload["results"][0]["pr"] is None
    assert payload["results"][1]["pr"] == refused.pr.to_dict()
    assert set(payload["results"][0]) == {
        "change",
        "locate",
        "proposal",
        "proof",
        "pr",
    }
    assert set(payload["summary"]) == {
        "changes",
        "proposals",
        "passed",
        "characterized",
        "replayed",
        "build_only",
        "unverified",
        "prs_opened",
        "prs_refused",
    }


# Spec AC7: the JSON proof carries every stage check and its level count.
def test_fix_json_carries_every_stage_check_and_level_count():
    result = a_fix_result(proof=a_two_stage_proof())

    payload = json.loads(render_fix_json([result]))

    proof = payload["results"][0]["proof"]
    assert [check["stage"] for check in proof["checks"]] == [
        "BUILD",
        "TESTS",
        "BUILD",
        "TESTS",
    ]
    assert payload["summary"]["passed"] == 1
    assert payload["summary"]["build_only"] == 0


# Spec AC5: zero results produce zero counts, not missing keys.
def test_json_summaries_are_zero_without_results():
    check_payload = json.loads(render_check_json([]))
    fix_payload = json.loads(render_fix_json([]))

    assert check_payload["summary"] == {
        "changes": 0,
        "certain": 0,
        "ambiguous": 0,
    }
    assert fix_payload["summary"] == {
        "changes": 0,
        "proposals": 0,
        "passed": 0,
        "characterized": 0,
        "replayed": 0,
        "build_only": 0,
        "unverified": 0,
        "prs_opened": 0,
        "prs_refused": 0,
    }


# Spec AC5: one line, one trailing newline, only JSON primitives.
def test_json_envelopes_are_one_line_of_primitives():
    check_text = render_check_json([a_locate(certain=(a_site(),))])
    fix_text = render_fix_json([a_fix_result(pr=an_opened_pr())])

    for text in (check_text, fix_text):
        assert text.endswith("\n")
        assert text.count("\n") == 1
        assert_json_primitives(json.loads(text))
        assert "ProofResult(" not in text
        assert "PrResult(" not in text
        assert "LocateResult(" not in text
        assert "ProofLevel." not in text
        assert "PrStatus." not in text


# Spec AC7: the JSON error is one object with the four stated keys.
def test_error_json_is_one_object_with_the_four_keys():
    text = render_error(
        "spec",
        "not a spec",
        code="NOT_A_SPEC",
        pointer="#/components/schemas/Charge",
        json_mode=True,
    )

    assert text == (
        a_json(
            obj={
                "error": {
                    "kind": "spec",
                    "code": "NOT_A_SPEC",
                    "pointer": "#/components/schemas/Charge",
                    "message": "not a spec",
                }
            }
        )
        + "\n"
    )
    assert text.count("\n") == 1


# Spec AC7: an error without a code or pointer still carries both keys as null.
def test_error_json_keeps_code_and_pointer_null():
    payload = json.loads(render_error("usage", "bad input", json_mode=True))

    assert payload == {
        "error": {
            "kind": "usage",
            "code": None,
            "pointer": None,
            "message": "bad input",
        }
    }


# Spec AC7: text mode is one stderr-ready line.
def test_error_text_is_one_line():
    assert render_error("usage", "bad input") == "tenon: usage: bad input\n"


# Spec AC7: the code and pointer are named when present.
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"code": "NOT_A_SPEC"},
            "tenon: spec: NOT_A_SPEC: not a spec\n",
        ),
        (
            {"pointer": "#/components/schemas/Charge"},
            "tenon: spec: at #/components/schemas/Charge: not a spec\n",
        ),
        (
            {"code": "NOT_A_SPEC", "pointer": "#/components/schemas/Charge"},
            "tenon: spec: NOT_A_SPEC at #/components/schemas/Charge: not a spec\n",
        ),
    ],
)
def test_error_text_names_the_code_and_pointer(kwargs, expected):
    assert render_error("spec", "not a spec", **kwargs) == expected


# Spec AC7: neither error mode contains a traceback.
@pytest.mark.parametrize("json_mode", [False, True])
def test_error_output_has_no_traceback(json_mode):
    text = render_error(
        "internal", "boom", code="X", pointer="#/x", json_mode=json_mode
    )

    assert "Traceback" not in text
    assert "File " not in text


# Spec AC6: the same inputs render the same bytes twice.
def test_renderers_are_deterministic_for_the_same_inputs():
    locate = a_locate(certain=(a_site(),))
    fix = a_fix_result(pr=an_opened_pr())

    assert render_check_text([locate]) == render_check_text([locate])
    assert render_fix_text([fix]) == render_fix_text([fix])
    assert render_check_json([locate]) == render_check_json([locate])
    assert render_fix_json([fix]) == render_fix_json([fix])


DETERMINISM_SCRIPT = """
from tenon.cli.report import (
    FixResult,
    render_check_json,
    render_check_text,
    render_fix_json,
    render_fix_text,
)
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateResult, Site, SiteShape
from tenon.propose import Edit, Proposal
from tenon.prove import CheckResult, ProofLevel, ProofResult
from tenon.pr import PrDraft, PrResult, PrStatus

change = Change(
    kind=ChangeKind.RENAMED,
    location=Location(
        pointer="#/components/schemas/Charge/properties",
        method="post",
        path="/v1/checkout/sessions",
    ),
    before={"b": 2, "a": 1},
    after=["z", {"d": 4, "c": 3}],
)
site = Site(
    path="acme/billing.py",
    line=7,
    column=30,
    shape=SiteShape.KEYWORD,
    symbol="amount",
)
locate = LocateResult(change=change, certain=(site,), ambiguous=())
edit = Edit(
    path="acme/billing.py",
    line=7,
    column=30,
    shape=SiteShape.KEYWORD,
    old="amount",
    new="amount_cents",
)
proposal = Proposal(
    change=change,
    edits=(edit,),
    skipped=(),
    diff="--- a/acme/billing.py\\n+++ b/acme/billing.py\\n",
)
check = CheckResult(
    kind="baseline",
    command=("python", "-m", "pytest", "-q"),
    returncode=0,
    timed_out=False,
)
proof = ProofResult(
    level=ProofLevel.TESTS_PASSED,
    baseline=check,
    after=CheckResult(
        kind="after",
        command=("python", "-m", "pytest", "-q"),
        returncode=0,
        timed_out=False,
    ),
    patch_applied=True,
)
draft = PrDraft(
    title="[TESTS_PASSED] tenon: renamed",
    body="body",
    branch="tenon/renamed-1234abcd",
    commit_message="tenon: renamed",
)
pr = PrResult(
    status=PrStatus.OPENED,
    level=ProofLevel.TESTS_PASSED,
    draft=draft,
    url="https://github.com/example/repo/pull/7",
)
result = FixResult(
    change=change,
    locate=locate,
    proposal=proposal,
    proof=proof,
    pr=pr,
)
print(render_check_json([locate]), end="")
print(render_check_text([locate]), end="")
print(render_fix_json([result]), end="")
print(render_fix_text([result]), end="")
"""


def render_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", DETERMINISM_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC6: byte-identical across hash seeds.
def test_reports_are_byte_stable_across_hash_seeds():
    assert render_with_hash_seed("0") == render_with_hash_seed("1")


# Spec AC8: no absolute path, timestamp, dataclass repr or enum repr leaks.
def test_reports_have_no_environment_leaks():
    fixture_root = str(Path(__file__).resolve().parent.parent / "fixtures" / "repos")
    locate = a_locate(certain=(a_site(),), ambiguous=(an_ambiguous_group(),))
    fix = a_fix_result(pr=a_refused_pr())
    texts = (
        render_check_text([locate]),
        render_fix_text([fix]),
        render_check_json([locate]),
        render_fix_json([fix]),
    )

    for text in texts:
        for leak in (
            fixture_root,
            "2026-",
            "ProofResult(",
            "PrResult(",
            "LocateResult(",
            "ProofLevel.",
            "PrStatus.",
            "ChangeKind.",
            "SiteShape.",
            "Proposal(",
        ):
            assert leak not in text


# Plan file 3: the report surface is re-exported from the package.
def test_report_surface_is_exported_from_tenon_cli():
    import tenon.cli as cli

    names = {
        "FixResult",
        "check_exit",
        "fix_exit",
        "render_check_text",
        "render_fix_text",
        "render_check_json",
        "render_fix_json",
        "render_error",
    }

    assert names <= set(cli.__all__)
    for name in names:
        assert getattr(cli, name) is globals()[name]




