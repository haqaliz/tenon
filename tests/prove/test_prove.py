"""Prove one proposal: preconditions, baseline-first ordering and cause mapping."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location, diff, parse
from tenon.locate import LocateConfig, locate
from tenon.propose import Edit, Proposal, ProposalReason, propose
from tenon.propose.render import render
from tenon.prove import CopyError, ProofCause, ProofLevel, prove

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
PROOF_BASIC = FIXTURES / "proof-basic"
ACME = LocateConfig(sdk_package="acme.client")
COMMAND = (sys.executable, "-c", "import acme.billing")

OLD_SPEC = """
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
"""
NEW_SPEC = OLD_SPEC.replace("amount:", "amount_cents:")


def tree_hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(root).rglob("*"))
        if path.is_file()
    }


# Spec AC10 / PRD M9: every case leaves the source tree and the temp dir untouched.
@pytest.fixture(autouse=True)
def source_unchanged_and_copies_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    before = tree_hashes(PROOF_BASIC)

    yield

    assert tree_hashes(PROOF_BASIC) == before
    assert list(tmp_path.glob("tenon-prove-*")) == []


def a_rename_proposal(root=PROOF_BASIC, proposer=None):
    """T1 diff -> T2 locate -> T3 propose over the fixture."""
    change = diff(parse(OLD_SPEC, "old"), parse(NEW_SPEC, "new")).changes[0]
    located = locate(change, root, ACME)
    if proposer is None:
        return propose(change, located, root)
    return propose(change, located, root, proposer)


class BrokenProposer:
    """Renames the keyword to something that makes the import a SyntaxError."""

    def propose(self, change, located, root):
        return tuple(
            Edit(
                path=site.path,
                line=site.line,
                column=site.column,
                shape=site.shape,
                old=site.symbol,
                new="1bad",
            )
            for site in located.certain
            if site.symbol == change.before
        )


def an_empty_proposal(reason):
    return Proposal(
        change=Change(
            kind=ChangeKind.RENAMED,
            location=Location(pointer="#/components/schemas/Charge/properties"),
            before="amount",
            after="amount_cents",
        ),
        edits=(),
        skipped=(),
        diff="",
        reason=reason,
    )


# Spec AC5: no command means nothing can run, and no copy is made.
@pytest.mark.parametrize("command", [[], None])
def test_an_empty_command_is_no_tests_found_without_copying(command, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("an empty command must not copy")

    monkeypatch.setattr("tenon.prove.copy.copy_tree", unexpected)

    result = prove(a_rename_proposal(), PROOF_BASIC, command)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.NO_TESTS_FOUND
    assert result.baseline is None
    assert result.after is None
    assert result.patch_applied is False


# Spec AC6: a string would need a shell; it is rejected.
def test_a_string_command_raises_value_error():
    with pytest.raises(ValueError):
        prove(a_rename_proposal(), PROOF_BASIC, "python -m pytest")


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_raises_value_error(timeout):
    with pytest.raises(ValueError):
        prove(a_rename_proposal(), PROOF_BASIC, COMMAND, timeout=timeout)


# Spec AC8 / PRD M6: a stale site is a patch that could not be applied.
def test_a_stale_empty_proposal_is_patch_did_not_apply():
    result = prove(
        an_empty_proposal(ProposalReason.STALE_SITE), PROOF_BASIC, COMMAND
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.PATCH_DID_NOT_APPLY
    assert result.baseline is None
    assert result.after is None


# Spec AC8 / PRD M6: any other empty proposal never proposed a patch.
def test_a_rule_less_empty_proposal_is_no_patch_proposed():
    result = prove(an_empty_proposal(ProposalReason.NO_RULE), PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.NO_PATCH_PROPOSED
    assert result.baseline is None
    assert result.after is None


# Spec AC1 / PRD M3-M5: the full path is the only place TESTS_PASSED appears.
def test_a_rename_proposal_passes_the_check_end_to_end():
    result = prove(a_rename_proposal(), PROOF_BASIC, list(COMMAND))

    assert result.level is ProofLevel.TESTS_PASSED
    assert result.cause is None
    assert result.patch_applied is True
    assert result.baseline.returncode == 0
    assert result.after.returncode == 0
    assert result.baseline.timed_out is False
    assert result.after.timed_out is False
    assert result.baseline.command == COMMAND
    assert result.after.command == COMMAND


# Spec AC2 / PRD M3: a red baseline never applies the patch.
def test_a_red_baseline_is_tests_failed_before_and_never_applies_the_patch(
    monkeypatch,
):
    def unexpected(*args, **kwargs):
        raise AssertionError("a red baseline must not apply the patch")

    monkeypatch.setattr("tenon.prove.run.apply_diff", unexpected)

    result = prove(
        a_rename_proposal(),
        PROOF_BASIC,
        [sys.executable, "-c", "raise SystemExit(1)"],
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.TESTS_FAILED_BEFORE
    assert result.baseline.returncode == 1
    assert result.after is None
    assert result.patch_applied is False


# Spec AC3 / PRD M5: a green baseline and a red patched check is the patch's fault.
def test_a_patch_that_breaks_the_import_is_tests_failed_after():
    result = prove(a_rename_proposal(proposer=BrokenProposer()), PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.TESTS_FAILED_AFTER
    assert result.baseline.returncode == 0
    assert result.after.returncode != 0
    assert result.after.timed_out is False
    assert result.patch_applied is True


# Spec AC4 / PRD M4: a diff that git refuses is a named failure with no after check.
def test_a_garbage_diff_is_patch_did_not_apply():
    proposal = a_rename_proposal()
    garbage = Proposal(
        change=proposal.change,
        edits=proposal.edits,
        skipped=proposal.skipped,
        diff="this is not a diff\n",
    )

    result = prove(garbage, PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.PATCH_DID_NOT_APPLY
    assert result.baseline.returncode == 0
    assert result.after is None
    assert result.patch_applied is False


# Spec AC9: a missing executable is a failed baseline, not NO_TESTS_FOUND.
def test_a_missing_executable_is_tests_failed_before_with_127():
    result = prove(
        a_rename_proposal(), PROOF_BASIC, ["tenon-no-such-command-xyz"]
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.TESTS_FAILED_BEFORE
    assert result.baseline.returncode == 127
    assert "tenon-no-such-command-xyz" in result.baseline.stderr_tail
    assert result.after is None
    assert result.patch_applied is False


# Spec AC7 / plan edge case: a baseline timeout is a timeout, not a red baseline.
def test_a_baseline_timeout_is_check_timed_out():
    result = prove(
        a_rename_proposal(),
        PROOF_BASIC,
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=0.2,
    )

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.CHECK_TIMED_OUT
    assert result.baseline.timed_out is True
    assert result.baseline.returncode is None
    assert result.after is None
    assert result.patch_applied is False


# Plan edge case: a timeout after the patch still says the patch did apply.
def test_an_after_timeout_keeps_patch_applied_true():
    proposal = a_rename_proposal()
    old = (PROOF_BASIC / "acme/billing.py").read_text(encoding="utf-8")
    new = old.replace(
        "def create_charge", "while True:\n    pass\n\n\ndef create_charge"
    )
    hanging = Proposal(
        change=proposal.change,
        edits=proposal.edits,
        skipped=proposal.skipped,
        diff=render({"acme/billing.py": (old, new)}),
    )

    result = prove(hanging, PROOF_BASIC, COMMAND, timeout=0.5)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.CHECK_TIMED_OUT
    assert result.baseline.returncode == 0
    assert result.after.timed_out is True
    assert result.after.returncode is None
    assert result.patch_applied is True


# Spec AC12: a root that vanished is COPY_FAILED, never a traceback.
def test_a_missing_root_is_copy_failed(tmp_path):
    result = prove(a_rename_proposal(), tmp_path / "missing", COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.COPY_FAILED
    assert result.baseline is None
    assert result.after is None
    assert result.patch_applied is False


# Spec AC12: a CopyError while copying is COPY_FAILED.
def test_a_copy_error_while_copying_is_copy_failed(monkeypatch):
    def failing(*args, **kwargs):
        raise CopyError(ProofCause.COPY_FAILED, "disk full")

    monkeypatch.setattr("tenon.prove.copy.copy_tree", failing)

    result = prove(a_rename_proposal(), PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.COPY_FAILED
    assert result.baseline is None
    assert result.after is None


# Fix: creating the temp directory is part of the copy step.
def test_a_temp_directory_failure_is_copy_failed(monkeypatch):
    def failing(*args, **kwargs):
        raise OSError("no temp space")

    monkeypatch.setattr(tempfile, "mkdtemp", failing)

    result = prove(a_rename_proposal(), PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.COPY_FAILED
    assert result.baseline is None
    assert result.after is None


# Fix: an OSError from the checked body is not a copy failure and must escape.
def test_an_oserror_from_the_body_propagates_instead_of_copy_failed(monkeypatch):
    def exploding(*args, **kwargs):
        raise OSError("body exploded")

    monkeypatch.setattr("tenon.prove.run._run", exploding)

    with pytest.raises(OSError, match="body exploded"):
        prove(a_rename_proposal(), PROOF_BASIC, COMMAND)


# Aspect-3 task: a git that hangs while applying is a diff that did not apply.
def test_a_timeout_while_applying_the_diff_is_patch_did_not_apply(monkeypatch):
    def timing_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("git apply", 60)

    monkeypatch.setattr("tenon.prove.run.apply_diff", timing_out)

    result = prove(a_rename_proposal(), PROOF_BASIC, COMMAND)

    assert result.level is ProofLevel.UNVERIFIED
    assert result.cause is ProofCause.PATCH_DID_NOT_APPLY
    assert result.baseline.returncode == 0
    assert result.after is None
    assert result.patch_applied is False


PROVE_SCRIPT = """
import sys
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, locate
from tenon.propose import propose
from tenon.prove import prove

root = sys.argv[1]
change = Change(
    kind=ChangeKind.RENAMED,
    location=Location(pointer="#/components/schemas/Charge/properties"),
    before="amount",
    after="amount_cents",
)
located = locate(change, root, LocateConfig(sdk_package="acme.client"))
proposal = propose(change, located, root)
print(prove(proposal, root, [sys.executable, "-c", "import acme.billing"]).to_json(), end="")
"""


def prove_json_with_hash_seed(seed):
    completed = subprocess.run(
        [sys.executable, "-c", PROVE_SCRIPT, str(PROOF_BASIC)],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


# Spec AC11 / PRD M8: the same run serialises byte-identically across hash seeds.
def test_the_result_serialises_identically_across_hash_seeds():
    first = prove_json_with_hash_seed("0")

    assert json.loads(first)["level"] == "TESTS_PASSED"
    assert first == prove_json_with_hash_seed("1")
