"""The public TypeScript locate API over the committed TS fixture repositories."""

import os
import subprocess
import sys
from pathlib import Path

from tenon.detect import ChangeKind, diff, parse
from tenon.locate import (
    AmbiguityReason,
    LocateReason,
    SiteShape,
    TsLocateConfig,
    locate_ts,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
TS_BASIC = FIXTURES / "ts-sdk-basic"
TS_QUOTED = FIXTURES / "ts-quoted"
TS_ATTRIBUTE = FIXTURES / "ts-attribute"
TS_ALIAS = FIXTURES / "ts-alias"
TS_DECOY = FIXTURES / "ts-decoy"
TS_DYNAMIC = FIXTURES / "ts-dynamic"
TS_DYNAMIC_IMPORT = FIXTURES / "ts-dynamic-import"
TS_NO_SDK = FIXTURES / "ts-no-sdk"

STRIPE = TsLocateConfig(sdk_package="stripe")
STRIPE_OPERATIONS = TsLocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/charges": "Stripe.charges.create"},
)
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

TWO_HOP_OLD = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        d:
          type: integer
"""
TWO_HOP_NEW = TWO_HOP_OLD.replace("        d:", "        d_cents:")

ENUM_OLD = """\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        status:
          type: string
          enum: [open, closed]
"""
ENUM_NEW = ENUM_OLD.replace("[open, closed]", "[open]")

EMPTY_SPEC = """\
openapi: 3.1.0
paths: {}
"""

NO_SITES_OLD = """\
openapi: 3.1.0
paths:
  /v1/nonexistent:
    get:
      responses:
        "200":
          description: ok
"""

TRACE_OLD = """\
openapi: 3.1.0
paths:
  /v1/charges:
    trace:
      responses:
        "200":
          description: ok
"""

MULTIPLE_OLD = """\
openapi: 3.1.0
paths:
  /v1/charges/{id}:
    get:
      responses:
        "200":
          description: ok
"""


def a_change(old, new):
    """The same T1 path the Python locator uses: diff two parsed specs."""
    [change] = diff(parse(old, "old"), parse(new, "new")).changes
    return change


def a_removed_endpoint(old):
    [change] = diff(parse(old, "old"), parse(EMPTY_SPEC, "new")).changes
    return change


def a_repo(tmp_path, source):
    (tmp_path / "app.ts").write_text(source, encoding="utf-8")
    return tmp_path


# Spec AC2: the component rename is certain exactly at the argument key.
def test_a_component_rename_finds_the_rooted_keyword():
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

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
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

    result = locate_ts(change, TS_QUOTED, STRIPE)

    assert [(site.path, site.line, site.column, site.shape, site.symbol) for site in result.certain] == [
        ("src/billing.ts", 5, 25, SiteShape.DICT_KEY, "amount")
    ]
    assert result.certain[0].line_text == 'client.charges.create({ "amount": 100 });'
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC2: a member on an SDK class receiver is an attribute.
def test_a_class_attribute_is_certain():
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

    result = locate_ts(change, TS_ATTRIBUTE, STRIPE)

    assert [(site.path, site.line, site.column, site.shape, site.symbol) for site in result.certain] == [
        ("src/charge.ts", 5, 8, SiteShape.ATTRIBUTE, "amount")
    ]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC4: an explicit operation mapping resolves the rooted call chain.
def test_an_operation_mapping_resolves_the_call_chain():
    change = a_change(OPERATION_OLD, OPERATION_NEW)

    result = locate_ts(change, TS_BASIC, STRIPE_OPERATIONS)

    assert [(site.path, site.line, site.column, site.shape, site.symbol) for site in result.certain] == [
        ("src/billing.ts", 5, 25, SiteShape.KEYWORD, "amount")
    ]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: no SDK import is a named non-result, not an exception.
def test_a_repository_without_the_sdk_has_no_import():
    result = locate_ts(a_change(COMPONENT_OLD, COMPONENT_NEW), TS_NO_SDK, STRIPE)

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC6: a change with no matching site is NO_SITES.
def test_a_change_with_no_matching_site_has_no_sites():
    result = locate_ts(a_removed_endpoint(NO_SITES_OLD), TS_BASIC, STRIPE)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC6: an unsupported kind short-circuits before the repository is scanned.
def test_an_unsupported_kind_short_circuits_without_scanning(monkeypatch):
    import tenon.locate.ts_locate as ts_locate_module

    def no_scan(*args, **kwargs):
        raise AssertionError("an unsupported kind must not scan")

    monkeypatch.setattr(ts_locate_module, "scan_ts", no_scan)
    change = a_change(ENUM_OLD, ENUM_NEW)

    result = locate_ts(change, TS_BASIC, STRIPE)

    assert change.kind is ChangeKind.ENUM_NARROWED
    assert result.reason is LocateReason.UNSUPPORTED_CHANGE_KIND
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC4: an operation with no mapping and no inferable candidates is named.
def test_an_unmapped_operation_has_no_mapping():
    result = locate_ts(a_removed_endpoint(TRACE_OLD), TS_BASIC, STRIPE)

    assert result.reason is LocateReason.OPERATION_NOT_MAPPED
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC4: two resolving candidates are one group with the candidate calls.
def test_two_resolving_candidates_are_one_group(tmp_path):
    repo = a_repo(
        tmp_path,
        'import * as stripe from "stripe";\n'
        "\n"
        'stripe.charges.get("ch_1");\n'
        'stripe.charges.list({ limit: 10 });\n',
    )
    result = locate_ts(a_removed_endpoint(MULTIPLE_OLD), repo, STRIPE)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.MULTIPLE_CANDIDATES
    assert group.symbol == "charges.get"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [
        ("app.ts", 3, 16, SiteShape.CALL, "get"),
        ("app.ts", 4, 16, SiteShape.CALL, "list"),
    ]


# Spec AC3: the unreachable decoy is never certain; the reachable non-SDK
# receiver is only an unrooted candidate.
def test_the_decoy_is_never_certain():
    result = locate_ts(a_change(COMPONENT_OLD, COMPONENT_NEW), TS_DECOY, STRIPE)

    assert [(site.path, site.line, site.column, site.shape) for site in result.certain] == [
        ("src/sdk.ts", 7, 25, SiteShape.KEYWORD)
    ]
    assert all(site.path != "src/unrelated.ts" for site in result.certain)
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert group.symbol == "amount"
    assert [
        (site.path, site.line, site.column, site.shape)
        for site in group.candidates
    ] == [("src/sdk.ts", 8, 8, SiteShape.KEYWORD)]
    assert all(site.path != "src/unrelated.ts" for site in group.candidates)


# Spec AC5: an object variable/spread on a resolved call is DYNAMIC_KWARGS.
def test_dynamic_kwargs_keep_the_resolved_call_sites_as_candidates():
    result = locate_ts(
        a_change(OPERATION_OLD, OPERATION_NEW), TS_DYNAMIC, STRIPE_OPERATIONS
    )

    assert [(site.path, site.line, site.column, site.shape) for site in result.certain] == [
        ("src/flows.ts", 9, 25, SiteShape.KEYWORD)
    ]
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_KWARGS
    assert group.symbol == "amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [
        ("src/flows.ts", 6, 16, SiteShape.CALL, "create"),
        ("src/flows.ts", 7, 16, SiteShape.CALL, "create"),
        ("src/flows.ts", 8, 16, SiteShape.CALL, "create"),
        ("src/flows.ts", 9, 16, SiteShape.CALL, "create"),
    ]


# Spec AC5: a string computed member names a DYNAMIC_GETATTR candidate.
def test_a_computed_member_is_dynamic_getattr():
    config = TsLocateConfig(
        sdk_package="stripe",
        operations={"POST /v1/charges": "charges"},
    )

    result = locate_ts(a_change(OPERATION_OLD, OPERATION_NEW), TS_DYNAMIC, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.DYNAMIC_GETATTR
    assert group.symbol == "charges"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("src/flows.ts", 13, 1, SiteShape.ATTRIBUTE, "charges")]


# Spec AC5: a dynamic import roots nothing; its matching call stays unrooted.
def test_a_dynamic_import_is_an_unrooted_candidate():
    result = locate_ts(
        a_change(OPERATION_OLD, OPERATION_NEW), TS_DYNAMIC_IMPORT, STRIPE
    )

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert group.symbol == "amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("src/sdk.ts", 5, 13, SiteShape.CALL, "create")]


# Spec AC5: a one-hop alias is certain; an unrooted call stays a candidate.
def test_a_one_hop_alias_is_certain():
    result = locate_ts(a_change(COMPONENT_OLD, COMPONENT_NEW), TS_ALIAS, STRIPE)

    assert [(site.path, site.line, site.column, site.shape) for site in result.certain] == [
        ("src/aliases.ts", 9, 8, SiteShape.ATTRIBUTE),
        ("src/aliases.ts", 10, 8, SiteShape.ATTRIBUTE),
        ("src/aliases.ts", 11, 18, SiteShape.KEYWORD),
        ("src/aliases.ts", 13, 18, SiteShape.KEYWORD),
    ]
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert [
        (site.path, site.line, site.column, site.shape)
        for site in group.candidates
    ] == [("src/aliases.ts", 22, 23, SiteShape.KEYWORD)]


# Spec AC5: a two-hop alias is ALIAS_CHAIN, never certain.
def test_a_two_hop_alias_is_an_alias_chain():
    result = locate_ts(a_change(TWO_HOP_OLD, TWO_HOP_NEW), TS_ALIAS, STRIPE)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.ALIAS_CHAIN
    assert group.symbol == "d"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("src/aliases.ts", 16, 7, SiteShape.ATTRIBUTE, "d")]


# Spec AC2/M2: a mapped field that the repository does not spell is named.
def test_an_unmapped_symbol_group_keeps_the_repository_spelling():
    config = TsLocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    result = locate_ts(a_change(COMPONENT_OLD, COMPONENT_NEW), TS_BASIC, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNMAPPED_SYMBOL
    assert group.symbol == "amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("src/billing.ts", 5, 25, SiteShape.KEYWORD, "amount")]


# Spec AC3: a mapped receiver chain resolves the operation.
def test_a_mapped_receiver_chain_resolves_the_operation(tmp_path):
    repo = a_repo(
        tmp_path,
        'import { Client } from "stripe";\n'
        "\n"
        'const client = new Client("key");\n'
        'client.charges.create({ amount: 100, currency: "usd" });\n',
    )
    config = TsLocateConfig(
        sdk_package="stripe",
        operations={"POST /v1/charges": "Client.charges.create"},
    )

    result = locate_ts(a_change(OPERATION_OLD, OPERATION_NEW), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("app.ts", 4, 25, SiteShape.KEYWORD, "amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC3: a typed helper resolves a component through locate_ts.
def test_a_typed_helper_resolves_a_component(tmp_path):
    repo = a_repo(
        tmp_path,
        'import { StripeClient } from "stripe";\n'
        "\n"
        "function makeClient(): StripeClient {\n"
        "  return new StripeClient();\n"
        "}\n"
        "\n"
        "const client = makeClient();\n"
        "client.amount;\n",
    )
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

    result = locate_ts(change, repo, TsLocateConfig(sdk_package="stripe"))

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("app.ts", 8, 8, SiteShape.ATTRIBUTE, "amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC3: a configured factory resolves a component through locate_ts.
def test_a_configured_factory_resolves_a_component(tmp_path):
    repo = a_repo(
        tmp_path,
        'import Stripe from "stripe";\n'
        "\n"
        "const client = makeClient();\n"
        "client.amount;\n",
    )
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

    configured = locate_ts(
        change,
        repo,
        TsLocateConfig(
            sdk_package="stripe", receivers={"makeClient": "Client"}
        ),
    )
    unconfigured = locate_ts(change, repo, TsLocateConfig(sdk_package="stripe"))

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in configured.certain
    ] == [("app.ts", 4, 8, SiteShape.ATTRIBUTE, "amount")]
    assert configured.ambiguous == ()
    assert configured.reason is None
    assert unconfigured.certain == ()


# Spec AC3: a typed parameter resolves the operation through locate_ts.
def test_a_typed_parameter_resolves_the_operation(tmp_path):
    repo = a_repo(
        tmp_path,
        'import { Client } from "stripe";\n'
        "\n"
        "function create(client: Client) {\n"
        '  client.charges.create({ amount: 100, currency: "usd" });\n'
        "}\n",
    )
    config = TsLocateConfig(
        sdk_package="stripe",
        operations={"POST /v1/charges": "Client.charges.create"},
    )

    result = locate_ts(a_change(OPERATION_OLD, OPERATION_NEW), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("app.ts", 4, 27, SiteShape.KEYWORD, "amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC7: same inputs, byte-identical JSON.
def test_two_runs_produce_identical_json():
    change = a_change(COMPONENT_OLD, COMPONENT_NEW)

    first = locate_ts(change, TS_BASIC, STRIPE).to_json()
    second = locate_ts(change, TS_BASIC, STRIPE).to_json()

    assert first == second


HASH_SEED_SCRIPT = """
from tenon.detect import diff, parse
from tenon.locate import TsLocateConfig, locate_ts

SPEC = '''\\
openapi: 3.1.0
components:
  schemas:
    Charge:
      type: object
      properties:
        amount:
          type: integer
'''
change, = diff(parse(SPEC, "old"), parse(SPEC.replace("amount", "amount_cents"), "new")).changes
print(locate_ts(change, {repo!r}, TsLocateConfig(sdk_package="stripe")).to_json(), end="")
"""


def locate_ts_with_hash_seed(seed):
    script = HASH_SEED_SCRIPT.format(repo=str(TS_BASIC))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_locate_ts_is_identical_across_hash_seeds():
    assert locate_ts_with_hash_seed("0") == locate_ts_with_hash_seed("1")


# Spec AC8: the shipped vocabulary is closed; a TS change adds no enum value.
def test_the_shipped_vocabulary_is_unchanged():
    assert [shape.value for shape in SiteShape] == [
        "call",
        "keyword",
        "dict_key",
        "attribute",
    ]
    assert [reason.value for reason in LocateReason] == [
        "UNSUPPORTED_CHANGE_KIND",
        "NO_SDK_IMPORT",
        "OPERATION_NOT_MAPPED",
        "NO_SITES",
    ]
    assert [reason.value for reason in AmbiguityReason] == [
        "DYNAMIC_KWARGS",
        "DYNAMIC_GETATTR",
        "ALIAS_CHAIN",
        "UNROOTED_RECEIVER",
        "MULTIPLE_CANDIDATES",
        "UNMAPPED_SYMBOL",
    ]
