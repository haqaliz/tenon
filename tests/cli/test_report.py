"""Exit codes, text reports and JSON envelopes for the CLI report surface."""

import pytest

from tenon.cli.report import FixResult, check_exit, fix_exit, render_check_text
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
from tenon.prove import CheckResult, ProofCause, ProofLevel, ProofResult
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
        "1 changes, 0 certain sites, 1 ambiguity groups\n"
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
        "1 changes, 0 certain sites, 0 ambiguity groups\n"
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
