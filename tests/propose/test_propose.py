"""Assembly over the committed fixtures: verify, apply, render, explain."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    LocateConfig,
    LocateReason,
    LocateResult,
    Site,
    SiteShape,
    locate,
)
from tenon.propose import ProposalReason, SkipReason, propose

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "sdk-basic"
SDK_DECOY = FIXTURES / "sdk-decoy"
SDK_DYNAMIC = FIXTURES / "sdk-dynamic"
STRIPE = LocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGES_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/application~1json/schema/properties"
)


def a_component_rename():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before="amount",
        after="amount_cents",
    )


def an_operation_rename():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(
            pointer=CHARGES_BODY, method="post", path="/v1/charges"
        ),
        before="amount",
        after="amount_cents",
    )


def copy_basic(tmp_path):
    target = tmp_path / "repo"
    shutil.copytree(SDK_BASIC, target)
    return target


def test_a_rename_on_the_basic_fixture_produces_one_edit_and_a_diff():
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)

    proposal = propose(change, located, SDK_BASIC)

    assert [
        (edit.path, edit.line, edit.column, edit.shape) for edit in proposal.edits
    ] == [("acme/billing.py", 5, 23, SiteShape.KEYWORD)]
    assert proposal.files == ("acme/billing.py",)
    assert proposal.reason is None
    assert proposal.skipped == ()
    assert proposal.diff.startswith(
        "--- a/acme/billing.py\n+++ b/acme/billing.py\n@@ -2,5 +2,5 @@\n"
    )
    assert '-client.charges.create(amount=amount, currency="usd")\n' in proposal.diff
    assert '+client.charges.create(amount_cents=amount, currency="usd")\n' in (
        proposal.diff
    )
    assert "a/acme/reporting.py" not in proposal.diff


def test_a_decoy_only_change_has_no_certain_sites(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(SDK_DECOY, repo)
    source = repo / "acme/mixed.py"
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    lines.remove("client.charges.create(amount=1)\n")
    source.write_text("".join(lines), encoding="utf-8")
    change = a_component_rename()
    located = locate(change, repo, STRIPE)
    assert located.certain == ()
    assert len(located.ambiguous) == 1
    assert located.ambiguous[0].reason is AmbiguityReason.UNROOTED_RECEIVER

    proposal = propose(change, located, repo)

    assert proposal.reason is ProposalReason.NO_CERTAIN_SITES
    assert proposal.edits == ()
    assert proposal.diff == ""
    assert [
        (entry.site.path, entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [
        ("acme/mixed.py", 10, 8, SkipReason.UNROOTED_RECEIVER),
    ]


def test_dynamic_kwargs_are_skipped_and_the_dict_key_is_edited():
    change = an_operation_rename()
    located = locate(change, SDK_DYNAMIC, STRIPE)

    proposal = propose(change, located, SDK_DYNAMIC)

    assert [(edit.line, edit.column, edit.shape) for edit in proposal.edits] == [
        (20, 24, SiteShape.DICT_KEY)
    ]
    assert all(edit.line != 7 for edit in proposal.edits)
    dynamic = [
        entry
        for entry in proposal.skipped
        if entry.reason is SkipReason.DYNAMIC_KWARGS
    ]
    assert {(entry.site.line, entry.site.column) for entry in dynamic} == {
        (7, 27),
        (20, 16),
    }


def test_a_certain_call_site_is_shape_not_editable():
    change = Change(
        kind=ChangeKind.ENDPOINT_REMOVED,
        location=Location(
            pointer="#/paths", method="delete", path="/v1/charges/{id}"
        ),
    )
    located = locate(change, SDK_BASIC, STRIPE)
    assert [(site.line, site.column, site.shape) for site in located.certain] == [
        (6, 16, SiteShape.CALL)
    ]

    proposal = propose(change, located, SDK_BASIC)

    assert proposal.reason is ProposalReason.NO_RULE
    assert proposal.edits == ()
    assert proposal.diff == ""
    assert [
        (entry.site.path, entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [("acme/billing.py", 6, 16, SkipReason.SHAPE_NOT_EDITABLE)]


def test_a_renamed_change_with_only_a_certain_call_site_has_no_editable_sites():
    change = a_component_rename()
    site = Site(
        path="acme/billing.py",
        line=5,
        column=23,
        shape=SiteShape.CALL,
        symbol="amount",
    )
    located = LocateResult(change=change, certain=(site,), ambiguous=())

    proposal = propose(change, located, SDK_BASIC)

    assert proposal.reason is ProposalReason.NO_EDITABLE_SITES
    assert proposal.edits == ()
    assert proposal.diff == ""
    assert [
        (entry.site.path, entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [("acme/billing.py", 5, 23, SkipReason.SHAPE_NOT_EDITABLE)]


def test_a_source_that_moved_after_locate_is_stale(tmp_path):
    repo = copy_basic(tmp_path)
    change = a_component_rename()
    located = locate(change, repo, STRIPE)
    source = repo / "acme/billing.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace("amount", "amount_cents"),
        encoding="utf-8",
    )

    proposal = propose(change, located, repo)

    assert proposal.reason is ProposalReason.STALE_SITE
    assert proposal.edits == ()
    assert proposal.diff == ""
    assert [
        (entry.site.path, entry.site.line, entry.site.column, entry.reason)
        for entry in proposal.skipped
    ] == [("acme/billing.py", 5, 23, SkipReason.STALE_SITE)]


def test_a_file_deleted_after_locate_is_stale(tmp_path):
    repo = copy_basic(tmp_path)
    change = a_component_rename()
    located = locate(change, repo, STRIPE)
    (repo / "acme/billing.py").unlink()

    proposal = propose(change, located, repo)

    assert proposal.reason is ProposalReason.STALE_SITE
    assert proposal.edits == ()
    assert proposal.diff == ""


def test_a_change_without_a_rule_returns_no_rule():
    change = Change(
        kind=ChangeKind.PROPERTY_REMOVED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before="amount",
    )
    located = locate(change, SDK_BASIC, STRIPE)

    proposal = propose(change, located, SDK_BASIC)

    assert proposal.reason is ProposalReason.NO_RULE
    assert proposal.edits == ()
    assert proposal.diff == ""


def test_an_unmechanical_rename_returns_no_rule():
    change = Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer="#/paths", method="get", path="/v2/charges"),
        before="/v1/charges",
        after="/v2/charges",
    )
    located = LocateResult(
        change=change, certain=(), ambiguous=(), reason=LocateReason.NO_SITES
    )

    proposal = propose(change, located, SDK_BASIC)

    assert proposal.reason is ProposalReason.NO_RULE
    assert proposal.edits == ()
    assert proposal.diff == ""


def test_propose_reads_each_touched_file_exactly_once(monkeypatch):
    change = a_component_rename()
    located = locate(change, SDK_BASIC, STRIPE)
    original = Path.read_text
    reads = []

    def counting_read_text(self, *args, **kwargs):
        if self.parent.name == "acme" and self.name == "billing.py":
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    proposal = propose(change, located, SDK_BASIC)

    assert len(reads) == 1
    assert proposal.edits


def test_propose_never_writes_to_the_fixture_repos():
    def digest(root):
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    repos = (SDK_BASIC, SDK_DECOY, SDK_DYNAMIC)
    before = {repo: digest(repo) for repo in repos}
    for change, repo in (
        (a_component_rename(), SDK_BASIC),
        (a_component_rename(), SDK_DECOY),
        (an_operation_rename(), SDK_DYNAMIC),
    ):
        propose(change, locate(change, repo, STRIPE), repo)

    assert {repo: digest(repo) for repo in repos} == before


def test_two_files_are_edited_and_rendered_in_path_order(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(
        "from stripe import Stripe\n\nclient = Stripe()\n"
        "client.charges.create(amount=1)\n",
        encoding="utf-8",
    )
    (repo / "b.py").write_text(
        "from stripe import Stripe\n\nother = Stripe()\n"
        "other.charges.list(amount=1)\n",
        encoding="utf-8",
    )
    change = a_component_rename()
    located = locate(change, repo, STRIPE)

    proposal = propose(change, located, repo)

    assert proposal.files == ("a.py", "b.py")
    assert [edit.path for edit in proposal.edits] == ["a.py", "b.py"]
    assert proposal.diff.index("a/a.py") < proposal.diff.index("a/b.py")


def test_the_diff_applies_to_a_copy_with_git(tmp_path):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    repo = copy_basic(tmp_path)
    for command in (
        [git, "init", "-q"],
        [git, "add", "-A"],
        [
            git,
            "-c",
            "user.name=Tenon",
            "-c",
            "user.email=tenon@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    change = a_component_rename()
    proposal = propose(change, locate(change, repo, STRIPE), repo)
    patch = tmp_path / "proposal.diff"
    patch.write_text(proposal.diff, encoding="utf-8")

    checked = subprocess.run(
        [git, "apply", "--check", str(patch)],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr
    applied = subprocess.run(
        [git, "apply", str(patch)], cwd=repo, capture_output=True, text=True
    )
    assert applied.returncode == 0, applied.stderr
    assert "amount_cents=" in (repo / "acme/billing.py").read_text(encoding="utf-8")


SUBPROCESS_SCRIPT = """
from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, locate
from tenon.propose import propose

change = Change(
    kind=ChangeKind.RENAMED,
    location=Location(pointer="#/components/schemas/Charge/properties"),
    before="amount",
    after="amount_cents",
)
located = locate(change, {repo!r}, LocateConfig(sdk_package="stripe"))
print(propose(change, located, {repo!r}).to_json(), end="")
"""


def propose_with_hash_seed(seed):
    script = SUBPROCESS_SCRIPT.format(repo=str(SDK_BASIC))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_propose_is_identical_across_hash_seeds():
    assert propose_with_hash_seed("0") == propose_with_hash_seed("1")
