"""Write one proven proposal as a branch and PR, without touching the user's tree."""

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence

from tenon.detect import Unanalyzed
from tenon.propose import Proposal
from tenon.prove import ProofLevel, ProofResult, tail

from .remote import Remote
from .render import render_pr
from .result import PrDraft, PrRefusal, PrResult, PrStatus

TIMEOUT = 60


class _GitError(Exception):
    """A git command could not run at all; the caller names the operation."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _detail(completed: subprocess.CompletedProcess) -> str:
    return "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )


def _git(argv, *, cwd, input=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [str(part) for part in argv],
            cwd=str(cwd),
            input=input,
            capture_output=True,
            text=True,
            shell=False,
            timeout=TIMEOUT,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired as exc:
        raise _GitError(f"timed out after {TIMEOUT}s: {exc}") from exc
    except OSError as exc:
        raise _GitError(str(exc)) from exc


def _refused(
    proof: ProofResult,
    draft: PrDraft,
    refusal: PrRefusal,
    detail: str = "",
) -> PrResult:
    return PrResult(
        status=PrStatus.REFUSED,
        level=proof.level,
        draft=draft,
        refusal=refusal,
        detail=tail(detail),
    )


def _safe_path(path: str) -> None:
    """Reject a path that could escape the clone, like T3 rejects one."""
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
        raise ValueError(f"unsafe repository path: {path!r}")


@contextmanager
def _clone(root: Path, origin_url: str) -> Iterator[Path]:
    """Clone ``root`` into a temp dir and point the clone at the real remote.

    A local clone's ``origin`` is the source path; leaving it there would push
    the branch into the user's checkout instead of their host.
    """
    try:
        tmp = tempfile.mkdtemp(prefix="tenon-pr-")
    except OSError as exc:
        raise _GitError(f"could not create a temporary directory: {exc}") from exc
    try:
        cloned = _git(
            ["git", "clone", "--no-hardlinks", "--", root, tmp], cwd=root
        )
        if cloned.returncode != 0:
            raise _GitError(_detail(cloned))
        pointed = _git(["git", "remote", "set-url", "origin", origin_url], cwd=tmp)
        if pointed.returncode != 0:
            raise _GitError(_detail(pointed))
        yield Path(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_pr(
    proposal: Proposal,
    proof: ProofResult,
    repo: str | Path,
    *,
    remote: Remote,
    base: str | None = None,
    allow_unverified: bool = False,
    unanalyzed: Sequence[Unanalyzed] = (),
) -> PrResult:
    """Ship ``proposal.diff`` from an isolated clone as one branch and PR.

    Every refusal is named, ordered and side-effect free until the clone step.
    """
    draft = render_pr(proposal, proof, unanalyzed=unanalyzed)

    try:
        root_result = _git(["git", "rev-parse", "--show-toplevel"], cwd=repo)
    except _GitError as exc:
        return _refused(proof, draft, PrRefusal.NOT_A_GIT_REPO, exc.detail)
    if root_result.returncode != 0:
        return _refused(
            proof, draft, PrRefusal.NOT_A_GIT_REPO, _detail(root_result)
        )
    root = Path(root_result.stdout.strip())

    if not proposal.edits or not proposal.diff:
        return _refused(proof, draft, PrRefusal.NO_PATCH)

    try:
        status = _git(["git", "status", "--porcelain"], cwd=root)
    except _GitError as exc:
        return _refused(proof, draft, PrRefusal.DIRTY_CHECKOUT, exc.detail)
    if status.returncode != 0 or status.stdout.strip():
        return _refused(
            proof, draft, PrRefusal.DIRTY_CHECKOUT, _detail(status)
        )

    try:
        origin = _git(["git", "remote", "get-url", "origin"], cwd=root)
    except _GitError as exc:
        return _refused(proof, draft, PrRefusal.NO_REMOTE, exc.detail)
    if origin.returncode != 0:
        return _refused(proof, draft, PrRefusal.NO_REMOTE, _detail(origin))

    if proof.level is ProofLevel.UNVERIFIED and not allow_unverified:
        return _refused(proof, draft, PrRefusal.UNVERIFIED_NOT_ALLOWED)

    if not base:
        base = remote.default_branch(root)
        if not base:
            return _refused(proof, draft, PrRefusal.UNKNOWN_DEFAULT_BRANCH)

    if draft.branch == base:
        return _refused(proof, draft, PrRefusal.DEFAULT_BRANCH)

    if remote.branch_exists(root, draft.branch):
        return _refused(proof, draft, PrRefusal.BRANCH_EXISTS)

    for path in proposal.files:
        _safe_path(path)

    try:
        with _clone(root, origin.stdout.strip()) as copy:
            try:
                applied = _git(
                    ["git", "apply", "-p1", "-"], cwd=copy, input=proposal.diff
                )
            except _GitError as exc:
                return _refused(
                    proof, draft, PrRefusal.PATCH_DID_NOT_APPLY, exc.detail
                )
            if applied.returncode != 0:
                return _refused(
                    proof, draft, PrRefusal.PATCH_DID_NOT_APPLY, _detail(applied)
                )

            try:
                added = _git(["git", "add", "--", *proposal.files], cwd=copy)
                committed = (
                    added
                    if added.returncode != 0
                    else _git(
                        ["git", "commit", "-m", draft.commit_message], cwd=copy
                    )
                )
            except _GitError as exc:
                return _refused(proof, draft, PrRefusal.COMMIT_FAILED, exc.detail)
            if committed.returncode != 0:
                return _refused(
                    proof, draft, PrRefusal.COMMIT_FAILED, _detail(committed)
                )

            remote.push(copy, draft.branch)
            url = remote.create_pr(
                copy,
                branch=draft.branch,
                base=base,
                title=draft.title,
                body=draft.body,
                draft=proof.level is ProofLevel.UNVERIFIED,
            )
            return PrResult(
                status=PrStatus.OPENED, level=proof.level, draft=draft, url=url
            )
    except _GitError as exc:
        return _refused(proof, draft, PrRefusal.COPY_FAILED, exc.detail)
