"""The real Stripe template at a pinned commit: T1 -> T2 -> T3, offline.

The two source files are byte-identical to `yezz123/stripe-template` at the SHA in
`PROVENANCE.md`. The vendor documents are not committed; the minimal spec pair below carries the
same rename, so the test stays small and offline.
"""

from pathlib import Path

from tenon.detect import ChangeKind, diff, parse
from tenon.locate import LocateConfig, SiteShape, locate
from tenon.propose import propose

FIXTURE = Path(__file__).parent.parent / "fixtures" / "repos" / "real-stripe-template"
CONFIG = LocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
)

SPEC = """\
openapi: 3.1.0
paths:
  /v1/checkout/sessions:
    post:
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              properties:
                payment_method_types:
                  type: array
                  items:
                    type: string
"""
NEW_SPEC = SPEC.replace("payment_method_types", "allowed_payment_method_types")


def a_rename():
    result = diff(parse(SPEC, "v2500"), parse(NEW_SPEC, "v2596"))
    [change] = result.changes
    return change


def test_the_pinned_rename_is_inferred_from_the_spec():
    change = a_rename()

    assert change.kind is ChangeKind.RENAMED
    assert (change.before, change.after) == (
        "payment_method_types",
        "allowed_payment_method_types",
    )
    assert change.confidence == "inferred"
    assert (change.location.method, change.location.path) == (
        "post",
        "/v1/checkout/sessions",
    )


def test_the_pinned_template_yields_two_certain_sites():
    located = locate(a_rename(), FIXTURE, CONFIG)

    assert [(site.path, site.line, site.symbol, site.shape) for site in located.certain] == [
        ("app/router/v1/payment.py", 41, "payment_method_types", SiteShape.KEYWORD),
        ("tests/test_payment.py", 49, "payment_method_types", SiteShape.KEYWORD),
    ]
    assert located.ambiguous == ()
    assert located.reason is None


def test_the_pinned_template_diff_is_two_hunks():
    change = a_rename()
    proposal = propose(change, locate(change, FIXTURE, CONFIG), FIXTURE)

    assert len(proposal.edits) == 2
    assert sum(line.startswith("@@") for line in proposal.diff.splitlines()) == 2
    assert "-        payment_method_types=setting.PAYMENT_METHOD_TYPES" in proposal.diff
    assert "+        allowed_payment_method_types=setting.PAYMENT_METHOD_TYPES" in proposal.diff
    assert "-        payment_method_types=config.PAYMENT_METHOD_TYPES" in proposal.diff
    assert "+        allowed_payment_method_types=config.PAYMENT_METHOD_TYPES" in proposal.diff
    assert proposal.files == ("app/router/v1/payment.py", "tests/test_payment.py")


def test_the_pinned_template_diff_is_byte_stable():
    change = a_rename()
    located = locate(change, FIXTURE, CONFIG)

    first = propose(change, located, FIXTURE)
    second = propose(change, located, FIXTURE)

    assert first.diff == second.diff
    assert first.to_json() == second.to_json()
