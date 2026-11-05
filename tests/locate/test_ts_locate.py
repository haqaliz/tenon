"""The public TypeScript locate API over the committed TS fixture repositories."""

from pathlib import Path

from tenon.detect import ChangeKind, diff, parse
from tenon.locate import LocateReason, SiteShape, TsLocateConfig, locate_ts

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
TS_BASIC = FIXTURES / "ts-sdk-basic"
TS_QUOTED = FIXTURES / "ts-quoted"
TS_ATTRIBUTE = FIXTURES / "ts-attribute"

STRIPE = TsLocateConfig(sdk_package="stripe")
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"

COMPONENT_OLD = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
"""
COMPONENT_NEW = COMPONENT_OLD.replace("amount", "amount_cents")

OPERATION_OLD = """\
openapi: 3.1.0
paths:
  /v1/charges:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                amount:
                  type: integer
"""
OPERATION_NEW = OPERATION_OLD.replace("amount", "amount_cents")


def a_rename(old=COMPONENT_OLD, new=COMPONENT_NEW):
    """The same T1 path the Python locator uses: diff two parsed specs."""
    [change] = diff(parse(old, "old"), parse(new, "new")).changes
    return change


# Spec AC2: the component rename is certain exactly at the argument key.
def test_a_component_rename_finds_the_rooted_keyword():
    change = a_rename()

    result = locate_ts(change, TS_BASIC, STRIPE)

    assert change.kind is ChangeKind.RENAMED
    assert change.location.pointer == CHARGE_PROPERTIES
    assert [(site.path, site.line, site.column) for site in result.certain] == [
        ("src/billing.ts", 5, 25)
    ]
    site = result.certain[0]
    assert site.shape is SiteShape.KEYWORD
    assert site.symbol == "amount"
    # line_text can only come from the real scan, so the wiring is not faked.
    assert site.line_text == 'client.charges.create({ amount: 100, currency: "usd" });'
    assert result.ambiguous == ()
    assert result.reason is None
    assert result.change is change


# Spec AC2: a quoted object key is a dict_key at the opening quote.
def test_a_quoted_key_is_a_dict_key():
    change = a_rename()

    result = locate_ts(change, TS_QUOTED, STRIPE)

    assert [(site.path, site.line, site.column, site.shape, site.symbol) for site in result.certain] == [
        ("src/billing.ts", 5, 25, SiteShape.DICT_KEY, "amount")
    ]
    assert result.certain[0].line_text == 'client.charges.create({ "amount": 100 });'
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC2: a member on an SDK class receiver is an attribute.
def test_a_class_attribute_is_certain():
    change = a_rename()

    result = locate_ts(change, TS_ATTRIBUTE, STRIPE)

    assert [(site.path, site.line, site.column, site.shape, site.symbol) for site in result.certain] == [
        ("src/charge.ts", 5, 8, SiteShape.ATTRIBUTE, "amount")
    ]
    assert result.ambiguous == ()
    assert result.reason is None
