"""The public C# locate API over temp ``.cs`` repositories."""

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    CSharpLocateConfig,
    LocateReason,
    SiteShape,
    locate_csharp,
)

ROOT = "Stripe"
STRIPE = CSharpLocateConfig(sdk_package=ROOT)
MAPPED = CSharpLocateConfig(
    sdk_package=ROOT,
    operations={"POST /v1/charges": "ChargeService.Create"},
)
CHARGE_PROPERTIES = "#/components/schemas/Charge/properties"
CHARGE_BODY = (
    "#/paths/~1v1~1charges/post/requestBody/content/"
    "application~1json/schema/properties"
)


def a_repo(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def a_component_rename(before="Amount", after="AmountCents"):
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before=before,
        after=after,
        breaking=True,
        confidence="inferred",
    )


def an_operation_rename(before="Amount", after="AmountCents"):
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_BODY, method="post", path="/v1/charges"),
        before=before,
        after=after,
        breaking=True,
        confidence="inferred",
    )


def a_removed_endpoint(
    path="/v1/charges",
    method="post",
    pointer="#/paths/~1v1~1charges",
):
    return Change(
        kind=ChangeKind.ENDPOINT_REMOVED,
        location=Location(pointer=pointer, method=method, path=path),
        breaking=True,
        confidence="certain",
    )


# Spec AC6: a mapped operation resolves the rooted call chain.
def test_an_operation_mapping_resolves_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )
    change = a_removed_endpoint()

    result = locate_csharp(change, repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 8, 9, SiteShape.CALL, "Create")]
    assert result.ambiguous == ()
    assert result.reason is None
    assert result.change is change


# Spec AC6: an operation field rename is certain at the initializer on the call chain.
def test_an_operation_field_rename_is_certain_on_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { Amount = 100 };\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = locate_csharp(an_operation_rename(), repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 7, 49, SiteShape.KEYWORD, "Amount")]
    assert result.certain[0].line_text == (
        "        var options = new ChargeCreateOptions { Amount = 100 };"
    )
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: a component field rename is certain on the type chain.
def test_a_component_field_rename_is_certain_on_the_type_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { Amount = 100 };\n"
            "    }\n"
            "}\n"
        },
    )

    result = locate_csharp(a_component_rename(), repo, STRIPE)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 7, 49, SiteShape.KEYWORD, "Amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: one source location is listed once even when it is evidence on two chains.
def test_a_component_field_passed_to_a_call_is_one_site(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { Amount = 100 };\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = locate_csharp(a_component_rename(), repo, STRIPE)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 7, 49, SiteShape.KEYWORD, "Amount")]


# Spec AC6: a fluent chain is an UNROOTED_RECEIVER candidate.
def test_a_fluent_chain_is_the_unrooted_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        client.Charges.Get(options);\n"
            "    }\n"
            "}\n"
        },
    )
    config = CSharpLocateConfig(
        sdk_package=ROOT, operations={"GET /v1/charges": "Charges.Get"}
    )
    change = a_removed_endpoint(method="get")

    result = locate_csharp(change, repo, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert group.symbol == "Charges.Get"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.cs", 7, 9, SiteShape.CALL, "Get")]


# Spec AC6: a mapped field the repository does not spell is UNMAPPED_SYMBOL.
def test_an_unmapped_symbol_keeps_the_repository_spelling(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { Amount = 100 };\n"
            "    }\n"
            "}\n"
        },
    )
    config = CSharpLocateConfig(
        sdk_package=ROOT, fields={"Charge.Amount": "AmountCents"}
    )

    result = locate_csharp(a_component_rename(), repo, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNMAPPED_SYMBOL
    assert group.symbol == "Amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.cs", 7, 49, SiteShape.KEYWORD, "Amount")]


# Spec AC6: two resolving candidates are one MULTIPLE_CANDIDATES group.
def test_two_rooted_candidates_are_multiple_candidates(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        charges.get(options);\n"
            "        charges.list(options);\n"
            "    }\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(method="get")

    result = locate_csharp(change, repo, STRIPE)

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
        ("main.cs", 7, 9, SiteShape.CALL, "get"),
        ("main.cs", 8, 9, SiteShape.CALL, "list"),
    ]


# Spec AC6: a change with no matching site is NO_SITES.
def test_an_operation_with_no_matching_call_has_no_sites(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        ChargeService.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(
        path="/v1/nonexistent",
        method="get",
        pointer="#/paths/~1v1~1nonexistent",
    )

    result = locate_csharp(change, repo, STRIPE)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC6: a repository without the root using is NO_SDK_IMPORT.
def test_a_repository_without_the_root_using_has_no_sdk_import(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "    }\n"
            "}\n",
        },
    )

    result = locate_csharp(a_component_rename(), repo, STRIPE)

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC3: a mapped receiver chain resolves the operation.
def test_a_mapped_receiver_chain_resolves_the_operation(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var client = new ChargeClient();\n"
            "        client.Charges.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )
    config = CSharpLocateConfig(
        sdk_package=ROOT,
        operations={"POST /v1/charges": "ChargeClient.Charges.Create"},
    )

    result = locate_csharp(a_removed_endpoint(), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 8, 9, SiteShape.CALL, "Create")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC3: a mapped receiver property is certain on a component change.
def test_a_mapped_receiver_property_is_certain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            '        var client = StripeClient.Create("key");\n'
            "        var amount = client.Amount;\n"
            "    }\n"
            "}\n"
        },
    )
    config = CSharpLocateConfig(
        sdk_package=ROOT, receivers={"StripeClient.Create": "Client"}
    )

    result = locate_csharp(a_component_rename(), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.cs", 8, 29, SiteShape.ATTRIBUTE, "Amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC1/M3: the C# config and wrapper are part of the public surface.
def test_the_csharp_api_is_exported():
    import tenon.locate as locate

    assert locate.CSharpLocateConfig is CSharpLocateConfig
    assert locate.locate_csharp is locate_csharp
    assert {"CSharpLocateConfig", "locate_csharp"} <= set(locate.__all__)
    assert locate.LOCATE_TYPES["csharp"] is CSharpLocateConfig
