"""The public Go locate API over temp ``.go`` repositories."""

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    GoLocateConfig,
    LocateReason,
    SiteShape,
    locate_go,
)

ROOT = "github.com/stripe/stripe-go/v76"
STRIPE = GoLocateConfig(sdk_package=ROOT, package_name="stripe")
MAPPED = GoLocateConfig(
    sdk_package=ROOT,
    package_name="stripe",
    operations={"POST /v1/charges": "charge.New"},
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
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}/charge"\n'
            "\n"
            "func main() {\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )
    change = a_removed_endpoint()

    result = locate_go(change, repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 6, 5, SiteShape.CALL, "New")]
    assert result.ambiguous == ()
    assert result.reason is None
    assert result.change is change


# Spec AC6: an operation field rename is certain at the literal on the call chain.
def test_an_operation_field_rename_is_certain_on_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{ROOT}"\n'
            f'    "{ROOT}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = locate_go(an_operation_rename(), repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 9, 36, SiteShape.KEYWORD, "Amount")]
    assert result.certain[0].line_text == "    params := &stripe.ChargeParams{Amount: 100}"
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: a component field rename is certain on the type chain.
def test_a_component_field_rename_is_certain_on_the_type_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}"\n'
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "}\n"
        },
    )

    result = locate_go(a_component_rename(), repo, STRIPE)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 6, 36, SiteShape.KEYWORD, "Amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: one source location is listed once even when it is evidence on two chains.
def test_a_component_field_passed_to_a_call_is_one_site(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{ROOT}"\n'
            f'    "{ROOT}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = locate_go(a_component_rename(), repo, STRIPE)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 9, 36, SiteShape.KEYWORD, "Amount")]


# Spec AC6: a method chain is an UNROOTED_RECEIVER candidate.
def test_a_method_chain_is_the_unrooted_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}"\n'
            "\n"
            "func main() {\n"
            "    client.Charges.Get(params)\n"
            "}\n"
        },
    )
    config = GoLocateConfig(
        sdk_package=ROOT, operations={"GET /v1/charges": "Charges.Get"}
    )
    change = a_removed_endpoint(method="get")

    result = locate_go(change, repo, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert group.symbol == "Charges.Get"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.go", 6, 5, SiteShape.CALL, "Get")]


# Spec AC6: a mapped field the repository does not spell is UNMAPPED_SYMBOL.
def test_an_unmapped_symbol_keeps_the_repository_spelling(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}"\n'
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "}\n"
        },
    )
    config = GoLocateConfig(
        sdk_package=ROOT, fields={"Charge.Amount": "AmountCents"}
    )

    result = locate_go(a_component_rename(), repo, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNMAPPED_SYMBOL
    assert group.symbol == "Amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.go", 6, 36, SiteShape.KEYWORD, "Amount")]


# Spec AC6: two resolving candidates are one MULTIPLE_CANDIDATES group.
def test_two_rooted_candidates_are_multiple_candidates(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}/charges"\n'
            "\n"
            "func main() {\n"
            "    charges.get()\n"
            "    charges.list()\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(method="get")

    result = locate_go(change, repo, STRIPE)

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
        ("main.go", 6, 5, SiteShape.CALL, "get"),
        ("main.go", 7, 5, SiteShape.CALL, "list"),
    ]


# Spec AC6: a change with no matching site is NO_SITES.
def test_an_operation_with_no_matching_call_has_no_sites(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}/charge"\n'
            "\n"
            "func main() {\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(
        path="/v1/nonexistent",
        method="get",
        pointer="#/paths/~1v1~1nonexistent",
    )

    result = locate_go(change, repo, STRIPE)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC6: a repository without the root import is NO_SDK_IMPORT.
def test_a_repository_without_the_root_import_has_no_sdk_import(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n\nfunc main() {}\n",
        },
    )

    result = locate_go(a_component_rename(), repo, STRIPE)

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC1/M3: the Go config and wrapper are part of the public surface.
def test_the_go_api_is_exported():
    import tenon.locate as locate

    assert locate.GoLocateConfig is GoLocateConfig
    assert locate.locate_go is locate_go
    assert {"GoLocateConfig", "locate_go"} <= set(locate.__all__)
    assert locate.LOCATE_TYPES["go"] is GoLocateConfig


# Spec AC4: a mapped receiver chain resolves the operation.
def test_a_mapped_receiver_chain_resolves_the_operation(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )
    config = GoLocateConfig(
        sdk_package=ROOT,
        package_name="stripe",
        operations={"POST /v1/charges": "Client.Charges.New"},
        receivers={"NewClient": "Client"},
    )

    result = locate_go(a_removed_endpoint(), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 7, 5, SiteShape.CALL, "New")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC4: a mapped receiver field is certain on the component change.
def test_a_mapped_receiver_field_is_certain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{ROOT}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    amount := client.Amount\n"
            "    _ = amount\n"
            "}\n"
        },
    )
    config = GoLocateConfig(
        sdk_package=ROOT,
        package_name="stripe",
        receivers={"NewClient": "Client"},
    )

    result = locate_go(a_component_rename(), repo, config)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.go", 7, 22, SiteShape.ATTRIBUTE, "Amount")]
    assert result.ambiguous == ()
    assert result.reason is None
