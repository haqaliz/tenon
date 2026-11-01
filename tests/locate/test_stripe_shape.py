"""The real Stripe rename, pinned end to end: reasons, one site, one diff."""

from pathlib import Path

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import LocateConfig, LocateReason, SiteShape, locate
from tenon.propose import propose

ROOT = Path(__file__).parent.parent / "fixtures" / "repos" / "sdk-stripe-checkout"

CHECKOUT_BODY = (
    "#/paths/~1v1~1checkout~1sessions/post/requestBody/content/"
    "application~1x-www-form-urlencoded/schema/properties"
)

PLAIN = LocateConfig(sdk_package="stripe")
MAPPED = LocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/checkout/sessions": "checkout.Session.create"},
)

EXPECTED_DIFF = """\
--- a/shop/checkout.py
+++ b/shop/checkout.py
@@ -4,6 +4,6 @@
 def create_checkout(customer):
     return stripe.checkout.Session.create(
         customer=customer,
-        payment_method_types=["card"],
+        allowed_payment_method_types=["card"],
         mode="payment",
     )
"""


def real_change():
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(
            pointer=CHECKOUT_BODY, method="post", path="/v1/checkout/sessions"
        ),
        before="payment_method_types",
        after="allowed_payment_method_types",
        breaking=True,
        confidence="inferred",
    )


def test_without_the_mapping_the_stripe_chain_is_not_found():
    result = locate(real_change(), ROOT, PLAIN)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


def test_with_the_mapping_the_keyword_is_one_certain_site():
    result = locate(real_change(), ROOT, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("shop/checkout.py", 7, 9, SiteShape.KEYWORD, "payment_method_types")]
    assert result.ambiguous == ()
    assert result.reason is None


def test_propose_renames_only_the_keyword():
    located = locate(real_change(), ROOT, MAPPED)

    proposal = propose(real_change(), located, ROOT)

    assert len(proposal.edits) == 1
    assert proposal.skipped == ()
    assert proposal.reason is None
    assert proposal.diff == EXPECTED_DIFF
