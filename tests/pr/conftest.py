"""Shared builders for the PR tests: a real proposal, proofs and a fake remote."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tenon.detect import diff, parse
from tenon.locate import LocateConfig, locate
from tenon.propose import propose
from tenon.prove import CheckResult, ProofCause, ProofLevel, ProofResult, ProofStage

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
PROOF_BASIC = FIXTURES / "proof-basic"
ACME = LocateConfig(sdk_package="acme.client")
CHECK_COMMAND = ("python", "-m", "pytest", "-q")
STAGE_FOR_LEVEL = {
    ProofLevel.TESTS_PASSED: ProofStage.TESTS,
    ProofLevel.CHARACTERIZED: ProofStage.CHARACTERIZE,
    ProofLevel.REPLAYED: ProofStage.REPLAY,
    ProofLevel.TYPES_BUILD_ONLY: ProofStage.BUILD,
}
COMMAND_FOR_LEVEL = {
    ProofLevel.CHARACTERIZED: ("python", "-m", "pytest", "tests/characterization", "-q"),
    ProofLevel.REPLAYED: ("python", "-m", "pytest", "tests/replay", "-q"),
    ProofLevel.TYPES_BUILD_ONLY: ("python", "-m", "compileall", "-q", "."),
}

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
def a_proof_at():
    """A green proof at any level, with the checks the result invariant demands."""

    def build(level, **overrides):
        stage = STAGE_FOR_LEVEL[level]
        command = COMMAND_FOR_LEVEL.get(level, CHECK_COMMAND)

        def check(kind):
            return CheckResult(
                kind=kind,
                stage=stage,
                command=command,
                returncode=0,
                timed_out=False,
            )

        values = {
            "level": level,
            "baseline": check("baseline"),
            "after": check("after"),
            "patch_applied": True,
            "checks": (check("baseline"), check("after")),
        }
        values.update(overrides)
        return ProofResult(**values)

    return build


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


class FakeRemote:
    """The adapter seam, recorded in memory: no process and no network."""

    def __init__(
        self,
        *,
        default: str = "main",
        existing: bool = False,
        url: str = "https://github.com/example/repo/pull/7",
    ) -> None:
        self.default = default
        self.existing = existing
        self.url = url
        self.calls: list[tuple] = []

    def default_branch(self, repo):
        self.calls.append(("default_branch", Path(repo)))
        return self.default

    def branch_exists(self, repo, branch):
        self.calls.append(("branch_exists", Path(repo), branch))
        return self.existing

    def push(self, repo, branch):
        self.calls.append(("push", Path(repo), branch))

    def create_pr(self, repo, *, branch, base, title, body, draft):
        self.calls.append(("create_pr", Path(repo), branch, base, title, body, draft))
        return self.url


@dataclass(frozen=True)
class RemoteRepo:
    """A working checkout and the bare repository it pushes to."""

    work: Path
    bare: Path


def _git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


@pytest.fixture
def repo_with_remote(tmp_path):
    """A clean checkout of proof-basic with origin pointing at a local bare repo."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git("init", "--bare", "--initial-branch=main", str(bare))
    shutil.copytree(PROOF_BASIC, work, ignore=shutil.ignore_patterns("__pycache__"))
    _git("init", "-b", "main", cwd=work)
    _git("config", "user.name", "Tenon Tests", cwd=work)
    _git("config", "user.email", "tenon@example.test", cwd=work)
    _git("add", ".", cwd=work)
    _git("commit", "-m", "fixture", cwd=work)
    _git("remote", "add", "origin", str(bare), cwd=work)
    _git("push", "-u", "origin", "main", cwd=work)
    _git("remote", "set-head", "origin", "main", cwd=work)
    return RemoteRepo(work=work, bare=bare)


@pytest.fixture
def a_fake_remote():
    def build(**kwargs):
        return FakeRemote(**kwargs)

    return build
