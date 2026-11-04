"""Shared builders for the PR render tests: a real proposal and hand-built proofs."""

from pathlib import Path

import pytest

from tenon.detect import diff, parse
from tenon.locate import LocateConfig, locate
from tenon.propose import propose
from tenon.prove import CheckResult, ProofCause, ProofLevel, ProofResult

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
PROOF_BASIC = FIXTURES / "proof-basic"
ACME = LocateConfig(sdk_package="acme.client")
CHECK_COMMAND = ("python", "-m", "pytest", "-q")

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


@pytest.fixture
def a_rename_proposal():
    """T1 diff -> T2 locate -> T3 propose over the proof-basic fixture."""
    change = diff(parse(OLD_SPEC, "old"), parse(NEW_SPEC, "new")).changes[0]
    located = locate(change, PROOF_BASIC, ACME)
    return propose(change, located, PROOF_BASIC)


@pytest.fixture
def a_passed_proof():
    def check(kind):
        return CheckResult(
            kind=kind,
            command=CHECK_COMMAND,
            returncode=0,
            timed_out=False,
        )

    return ProofResult(
        level=ProofLevel.TESTS_PASSED,
        baseline=check("baseline"),
        after=check("after"),
        patch_applied=True,
    )


@pytest.fixture
def an_unverified_proof():
    def build(cause=ProofCause.NO_TESTS_FOUND, **overrides):
        values = {
            "level": ProofLevel.UNVERIFIED,
            "cause": cause,
            "baseline": None,
            "after": None,
            "patch_applied": False,
        }
        values.update(overrides)
        return ProofResult(**values)

    return build
