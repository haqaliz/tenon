"""Render a deterministic PR draft: summary, title, commit, branch and body."""

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tenon.detect import (
    Change,
    ChangeKind,
    Location,
    Unanalyzed,
    UnanalyzedReason,
)
from tenon.locate import Site, SiteShape
from tenon.pr import render_pr
from tenon.pr.render import (
    CHARACTERIZED_PROOF,
    CHARACTERIZED_SENTENCE,
    REPLAYED_PROOF,
    REPLAYED_SENTENCE,
    TESTS_PASSED_PROOF,
    TESTS_PASSED_SENTENCE,
    TYPES_BUILD_ONLY_PROOF,
    TYPES_BUILD_ONLY_SENTENCE,
    _branch,
    _commit_message,
    _slug,
    _summary,
    _title,
)
from tenon.propose import SkipReason, Skipped
from tenon.prove import CheckResult, ProofCause, ProofLevel

CHARGE_POINTER = "#/components/schemas/Charge/properties"
PROOF_BASIC = Path(__file__).parent.parent / "fixtures" / "repos" / "proof-basic"
COMMAND = ("python", "-m", "pytest", "-q")


def a_check(**overrides):
    values = {
        "kind": "baseline",
        "command": COMMAND,
        "returncode": 0,
        "timed_out": False,
    }
    values.update(overrides)
    return CheckResult(**values)


def a_change(**overrides):
    values = {
        "kind": ChangeKind.RENAMED,
        "location": Location(
            pointer=CHARGE_POINTER,
            method="post",
            path="/v1/checkout/sessions",
        ),
        "before": "payment_method_types",
        "after": "allowed_payment_method_types",
    }
    values.update(overrides)
    return Change(**values)


# Spec AC1: the summary names the method and path when both are present.
def test_summary_uses_the_method_and_path():
    assert _summary(a_change()) == (
        "renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec AC1: the title is the level, the prefix, and that one summary.
def test_title_is_the_level_and_the_tenon_prefix(a_passed_proof):
    assert _title(a_passed_proof, _summary(a_change())) == (
        "[TESTS_PASSED] tenon: renamed POST /v1/checkout/sessions: "
        "payment_method_types -> allowed_payment_method_types"
    )


# Spec AC1: the commit subject is the same summary, with no level.
def test_commit_message_is_the_summary_without_the_level():
    assert _commit_message(_summary(a_change())) == (
        "tenon: renamed POST /v1/checkout/sessions: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec: without a method and path the location is the pointer.
def test_summary_falls_back_to_the_pointer():
    change = a_change(location=Location(pointer=CHARGE_POINTER))

    assert _summary(change) == (
        f"renamed {CHARGE_POINTER}: payment_method_types -> "
        "allowed_payment_method_types"
    )


# Spec: a before or after value is the only reason to add the arrow.
def test_summary_omits_the_arrow_when_both_values_are_none():
    assert _summary(a_change(before=None, after=None)) == (
        "renamed POST /v1/checkout/sessions"
    )


# Spec AC2: scalars render readably and containers render as compact canonical JSON.
@pytest.mark.parametrize(
    ("before", "after", "rendered"),
    [
        ("old", "new", "old -> new"),
        (3, 4, "3 -> 4"),
        (1.5, 2.0, "1.5 -> 2.0"),
        (False, True, "False -> True"),
        (None, "value", "None -> value"),
        (
            {"b": 2, "a": 1},
            [2, {"z": 1, "a": 0}],
            '{"a":1,"b":2} -> [2,{"a":0,"z":1}]',
        ),
    ],
)
def test_summary_renders_values_readably(before, after, rendered):
    assert _summary(a_change(before=before, after=after)) == (
        f"renamed POST /v1/checkout/sessions: {rendered}"
    )


BRANCH = re.compile(r"tenon/[a-z0-9-]+-[0-9a-f]{8}")


# Spec AC3: the branch shape is fixed.
def test_branch_matches_the_contract():
    assert BRANCH.fullmatch(_branch(a_change(), "diff")) is not None


# Spec AC3: the same change and diff always give the same branch.
def test_branch_is_stable_for_the_same_change_and_diff():
    change = a_change()

    assert _branch(change, "diff") == _branch(change, "diff")


# Spec AC3: one changed diff byte changes the suffix.
def test_branch_changes_when_one_diff_byte_changes():
    change = a_change()

    assert _branch(change, "diff") != _branch(change, "difF")


# Spec AC3: punctuation and unicode still produce a valid, readable slug.
def test_branch_sanitises_punctuation_and_unicode():
    branch = _branch(a_change(before="café/über", after="naïve — value"), "")

    assert BRANCH.fullmatch(branch) is not None
    assert "--" not in branch


# Spec AC3: an all-punctuation summary falls back to the word change.
def test_slug_falls_back_to_change_when_empty():
    assert _slug("!!! ???") == "change"


# Spec: lower-case, every run of non-alphanumerics collapsed to one dash, trimmed.
def test_slug_lowercases_and_collapses_runs():
    assert _slug("Renamed  POST /v1//Checkout: A -> B") == (
        "renamed-post-v1-checkout-a-b"
    )


# Spec AC3: the readable part stops at 48 characters.
def test_slug_truncates_to_48_characters():
    assert _slug("a" * 200) == "a" * 48


# Spec AC3: the suffix is sha256(change_json + NUL + diff), first eight hex.
def test_branch_suffix_hashes_the_canonical_change_and_diff():
    change = a_change()
    payload = (
        json.dumps(
            change.to_dict(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\0"
        + b"diff"
    )
    expected = hashlib.sha256(payload).hexdigest()[:8]

    assert _branch(change, "diff") == f"tenon/{_slug(_summary(change))}-{expected}"



PASSED_BODY = """\
## Tenon proof: TESTS_PASSED

The command returned 0 before and after the patch in an isolated copy.

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `python -m pytest -q`
- Baseline exit: `0`
- After exit: `0`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

The check ran green before and after the patch, so the change did not break the command Tenon ran. It does not prove the change is correct.

Opened by Tenon. No merge was performed.
"""


# Spec AC4: the happy path body is one pinned deterministic text.
def test_passed_body_is_the_golden_text(a_rename_proposal, a_passed_proof):
    assert render_pr(a_rename_proposal, a_passed_proof).body == PASSED_BODY


# Spec AC1: render_pr wires the same summary into the title and the commit.
def test_render_pr_reuses_the_summary_in_the_title_and_commit(
    a_rename_proposal, a_passed_proof
):
    draft = render_pr(a_rename_proposal, a_passed_proof)
    summary = _summary(a_rename_proposal.change)

    assert draft.title == f"[TESTS_PASSED] tenon: {summary}"
    assert draft.commit_message == f"tenon: {summary}"


# Spec AC4: the sections keep the fixed order.
def test_passed_body_sections_are_in_the_fixed_order(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body
    headings = [
        "## Tenon proof: TESTS_PASSED",
        "### Change",
        "### Check",
        "### Files",
        "### Skipped sites",
        "### What this proves",
    ]

    assert [body.index(heading) for heading in headings] == sorted(
        body.index(heading) for heading in headings
    )


# Spec AC4: the command and both exit codes appear.
def test_passed_body_records_the_command_and_both_exits(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "- Command: `python -m pytest -q`" in body
    assert "- Baseline exit: `0`" in body
    assert "- After exit: `0`" in body


# Spec AC4: every touched file is listed.
def test_passed_body_lists_every_file(a_rename_proposal, a_passed_proof):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    for path in a_rename_proposal.files:
        assert f"- `{path}`" in body


# Spec AC4: every skipped site keeps its path, line, symbol and reason.
def test_passed_body_lists_every_skipped_site(a_rename_proposal, a_passed_proof):
    proposal = replace(
        a_rename_proposal,
        skipped=(
            Skipped(
                site=Site(
                    path="acme/billing.py",
                    line=7,
                    column=30,
                    shape=SiteShape.KEYWORD,
                    symbol="amount",
                ),
                reason=SkipReason.DYNAMIC_KWARGS,
            ),
            Skipped(
                site=Site(
                    path="acme/client.py",
                    line=2,
                    column=9,
                    shape=SiteShape.DICT_KEY,
                    symbol="amount",
                ),
                reason=SkipReason.STALE_SITE,
            ),
        ),
    )

    body = render_pr(proposal, a_passed_proof).body

    assert "- `acme/billing.py:7` `amount`: DYNAMIC_KWARGS" in body
    assert "- `acme/client.py:2` `amount`: STALE_SITE" in body


# Spec AC4: an empty skipped list says so explicitly.
def test_passed_body_says_none_for_no_skipped_sites(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "### Skipped sites\n\nNone." in body


# Spec AC4: the full unified diff is never copied into the body.
def test_passed_body_contains_no_diff(a_rename_proposal, a_passed_proof):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert "--- a/" not in body
    assert a_rename_proposal.diff not in body


# Spec: one footer, last, and exactly one trailing newline.
def test_passed_body_ends_with_the_footer_and_one_newline(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(a_rename_proposal, a_passed_proof).body

    assert body.endswith("Opened by Tenon. No merge was performed.\n")
    assert body.count("Opened by Tenon. No merge was performed.") == 1
    assert not body.endswith("\n\n")


UNVERIFIED_BODY = """\
## Tenon proof: UNVERIFIED

Nothing proved the patch.
Cause: NO_TESTS_FOUND

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `not run`
- Baseline exit: `not run`
- After exit: `not run`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

Nothing was proven. This is a flagged suggestion: review the change and run the check before merging.

Opened by Tenon. No merge was performed.
"""


# Spec AC5: a flagged suggestion names the level, the exact cause and the refusal.
def test_unverified_body_is_the_golden_text(
    a_rename_proposal, an_unverified_proof
):
    body = render_pr(
        a_rename_proposal, an_unverified_proof()
    ).body

    assert body == UNVERIFIED_BODY


# Spec AC5: the body never claims the patch passed.
def test_unverified_body_never_claims_a_pass(a_rename_proposal, an_unverified_proof):
    body = render_pr(a_rename_proposal, an_unverified_proof()).body

    assert TESTS_PASSED_SENTENCE not in body
    assert TESTS_PASSED_PROOF not in body
    assert "ran green" not in body


# Spec AC6: a missing baseline and a missing after check render as not run.
def test_unverified_body_renders_missing_checks_as_not_run(
    a_rename_proposal, an_unverified_proof
):
    body = render_pr(a_rename_proposal, an_unverified_proof()).body

    assert "- Command: `not run`" in body
    assert "- Baseline exit: `not run`" in body
    assert "- After exit: `not run`" in body


# Spec AC6: a killed check renders as timed out, not as an exit code.
def test_unverified_body_renders_a_timeout_as_timed_out(
    a_rename_proposal, an_unverified_proof
):
    proof = an_unverified_proof(
        cause=ProofCause.CHECK_TIMED_OUT,
        baseline=a_check(returncode=None, timed_out=True),
    )

    body = render_pr(a_rename_proposal, proof).body

    assert "- Baseline exit: `timed out`" in body
    assert "- After exit: `not run`" in body


# Spec AC6: a non-empty failure tail is fenced.
def test_unverified_body_fences_the_failure_tail(
    a_rename_proposal, an_unverified_proof
):
    proof = an_unverified_proof(
        cause=ProofCause.TESTS_FAILED_AFTER,
        baseline=a_check(kind="baseline"),
        after=a_check(
            kind="after",
            returncode=1,
            stdout_tail="1 failed\nassert 0",
        ),
        patch_applied=True,
    )

    body = render_pr(a_rename_proposal, proof).body

    assert "After output:" in body
    assert "```\n1 failed\nassert 0\n```" in body


# Spec AC6: the tail is capped like T4 before it is fenced.
def test_unverified_body_caps_the_failure_tail(
    a_rename_proposal, an_unverified_proof
):
    tail = "\n".join(f"line {number}" for number in range(1, 26))
    proof = an_unverified_proof(
        cause=ProofCause.TESTS_FAILED_AFTER,
        after=a_check(kind="after", returncode=1, stdout_tail=tail),
        patch_applied=True,
    )

    body = render_pr(a_rename_proposal, proof).body

    assert "line 1\n" not in body
    assert "line 6\n" in body
    assert "line 25\n" in body


# Spec AC6: the text excludes any word that would overstate a build-only result.
TYPES_BUILD_ONLY_BODY = """\
## Tenon proof: TYPES_BUILD_ONLY

The build or type-check command returned 0 before and after the patch; no tests ran.

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `python -m compileall -q .`
- Baseline exit: `0`
- After exit: `0`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

The build or type-check ran green before and after the patch, so the change did not break it. No tests ran: this is weak proof, and it does not prove the change is correct.

Opened by Tenon. No merge was performed.
"""


# Spec AC6: the build-only body is one pinned, honest text.
def test_types_build_only_body_is_the_golden_text(a_rename_proposal, a_proof_at):
    draft = render_pr(
        a_rename_proposal, a_proof_at(ProofLevel.TYPES_BUILD_ONLY)
    )

    assert draft.title.startswith("[TYPES_BUILD_ONLY] tenon: ")
    assert draft.body == TYPES_BUILD_ONLY_BODY


CHARACTERIZED_BODY = """\
## Tenon proof: CHARACTERIZED

The user-supplied characterization command returned 0 before and after the patch.

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `python -m pytest tests/characterization -q`
- Baseline exit: `0`
- After exit: `0`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

The characterization command ran green before and after the patch. It checks current behavior, not the vendor's new API; Tenon did not generate it. It does not prove the change is correct.

Opened by Tenon. No merge was performed.
"""


# Spec AC6: the characterized body is one pinned, honest text.
def test_characterized_body_is_the_golden_text(a_rename_proposal, a_proof_at):
    draft = render_pr(a_rename_proposal, a_proof_at(ProofLevel.CHARACTERIZED))

    assert draft.title.startswith("[CHARACTERIZED] tenon: ")
    assert draft.body == CHARACTERIZED_BODY


REPLAYED_BODY = """\
## Tenon proof: REPLAYED

The user-supplied recorded-call replay returned 0 before and after the patch.

### Change

- Kind: `renamed`
- Location: `#/components/schemas/Charge/properties`
- Before: `amount`
- After: `amount_cents`
- Breaking: `True`
- Confidence: `inferred`

### Check

- Command: `python -m pytest tests/replay -q`
- Baseline exit: `0`
- After exit: `0`

### Files

- `acme/billing.py`

### Skipped sites

None.

### What this proves

The recorded-call replay ran green before and after the patch. The recording was supplied, not made by Tenon, so it only proves the replayed calls behaved as recorded. It does not prove the change is correct.

Opened by Tenon. No merge was performed.
"""


# Spec AC6: the replayed body is one pinned, honest text.
def test_replayed_body_is_the_golden_text(a_rename_proposal, a_proof_at):
    draft = render_pr(a_rename_proposal, a_proof_at(ProofLevel.REPLAYED))

    assert draft.title.startswith("[REPLAYED] tenon: ")
    assert draft.body == REPLAYED_BODY


@pytest.mark.parametrize(
    ("level", "sentence", "paragraph", "command"),
    [
        (
            ProofLevel.TYPES_BUILD_ONLY,
            TYPES_BUILD_ONLY_SENTENCE,
            TYPES_BUILD_ONLY_PROOF,
            "python -m compileall -q .",
        ),
        (
            ProofLevel.CHARACTERIZED,
            CHARACTERIZED_SENTENCE,
            CHARACTERIZED_PROOF,
            "python -m pytest tests/characterization -q",
        ),
        (
            ProofLevel.REPLAYED,
            REPLAYED_SENTENCE,
            REPLAYED_PROOF,
            "python -m pytest tests/replay -q",
        ),
    ],
)
# Spec AC6: every weak level names its command and what it does not prove.
def test_weak_level_body_states_what_actually_ran(
    level, sentence, paragraph, command, a_rename_proposal, a_proof_at
):
    draft = render_pr(a_rename_proposal, a_proof_at(level))

    assert f"[{level.value}]" in draft.title
    assert sentence in draft.body
    assert f"- Command: `{command}`" in draft.body
    assert f"### What this proves\n\n{paragraph}" in draft.body
    assert "verified" not in draft.body.lower()
    assert TESTS_PASSED_SENTENCE not in draft.body
    assert TESTS_PASSED_PROOF not in draft.body


# Spec AC7: every supplied unanalyzed subtree keeps its pointer and reason.
def test_unanalyzed_subtrees_are_listed(a_rename_proposal, a_passed_proof):
    entries = (
        Unanalyzed(
            pointer="#/components/schemas/Order",
            reason=UnanalyzedReason.UNRESOLVED_REF,
        ),
        Unanalyzed(
            pointer="#/components/schemas/Charge",
            reason=UnanalyzedReason.CYCLIC_REF,
        ),
    )

    body = render_pr(
        a_rename_proposal, a_passed_proof, unanalyzed=entries
    ).body

    assert "### Not analyzed" in body
    assert "- `#/components/schemas/Charge`: CYCLIC_REF" in body
    assert "- `#/components/schemas/Order`: UNRESOLVED_REF" in body
    assert body.index("### Skipped sites") < body.index("### Not analyzed")
    assert body.index("### Not analyzed") < body.index("### What this proves")


# Spec AC7: no supplied entries means no section at all.
def test_unanalyzed_section_is_omitted_when_empty(
    a_rename_proposal, a_passed_proof
):
    body = render_pr(
        a_rename_proposal, a_passed_proof, unanalyzed=()
    ).body

    assert "### Not analyzed" not in body


# Spec AC8: a backtick or newline cannot break out of an inline code span.
def test_inline_spans_escape_backticks_and_newlines(
    a_rename_proposal, a_passed_proof
):
    proposal = replace(
        a_rename_proposal,
        change=replace(a_rename_proposal.change, before="a`b\nc"),
        skipped=(
            Skipped(
                site=Site(
                    path="acme/weird`path.py",
                    line=3,
                    column=1,
                    shape=SiteShape.KEYWORD,
                    symbol="x`y\nz",
                ),
                reason=SkipReason.DYNAMIC_KWARGS,
            ),
        ),
    )

    body = render_pr(proposal, a_passed_proof).body

    assert "`a'b c`" in body
    assert "`x'y z`" in body
    assert "`acme/weird'path.py:3`" in body
    assert "a`b" not in body
    assert "x`y" not in body


# Spec AC8/M11: the same inputs render the same bytes twice.
def test_render_pr_is_deterministic_for_the_same_inputs(
    a_rename_proposal, a_passed_proof
):
    first = render_pr(a_rename_proposal, a_passed_proof)
    second = render_pr(a_rename_proposal, a_passed_proof)

    assert first.to_json() == second.to_json()


DETERMINISM_SCRIPT = """
from tenon.detect import (
    Change,
    ChangeKind,
    Location,
    Unanalyzed,
    UnanalyzedReason,
)
from tenon.locate import Site, SiteShape
from tenon.pr import render_pr
from tenon.propose import Edit, Proposal, SkipReason, Skipped
from tenon.prove import CheckResult, ProofCause, ProofLevel, ProofResult

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
    skipped=(
        Skipped(
            site=Site(
                path="acme/billing.py",
                line=7,
                column=30,
                shape=SiteShape.KEYWORD,
                symbol="amount",
            ),
            reason=SkipReason.DYNAMIC_KWARGS,
        ),
    ),
    diff="--- a/acme/billing.py\\n+++ b/acme/billing.py\\n",
)
proof = ProofResult(
    level=ProofLevel.UNVERIFIED,
    cause=ProofCause.NO_TESTS_FOUND,
    baseline=None,
    after=None,
    patch_applied=False,
)
unanalyzed = (
    Unanalyzed(
        pointer="#/components/schemas/Charge",
        reason=UnanalyzedReason.CYCLIC_REF,
    ),
)
print(render_pr(proposal, proof, unanalyzed=unanalyzed).to_json(), end="")
"""


def render_json_with_hash_seed(seed):
    result = subprocess.run(
        [sys.executable, "-c", DETERMINISM_SCRIPT],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Spec AC8/M11: byte-identical across hash seeds.
def test_draft_json_is_byte_stable_across_hash_seeds():
    assert render_json_with_hash_seed("0") == render_json_with_hash_seed("1")


# Spec AC9: no absolute path, timestamp, dataclass repr or enum repr leaks.
def test_draft_has_no_environment_leaks(a_rename_proposal, a_passed_proof):
    draft = render_pr(a_rename_proposal, a_passed_proof)

    for leak in (
        str(PROOF_BASIC),
        "2026-",
        "ProofResult(",
        "ProofLevel.",
        "ProofCause.",
        "ChangeKind.",
        "--- a/",
        a_rename_proposal.diff,
    ):
        assert leak not in draft.body
    assert "ChangeKind." not in draft.title


# Spec AC9: an unverified draft names no passing sentence.
def test_unverified_draft_has_no_environment_leaks(
    a_rename_proposal, an_unverified_proof
):
    draft = render_pr(a_rename_proposal, an_unverified_proof())

    for leak in (str(PROOF_BASIC), "2026-", "ProofResult(", "ProofLevel."):
        assert leak not in draft.body
