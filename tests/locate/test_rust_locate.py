"""The public Rust locate API over temp ``.rs`` repositories."""

from tenon.detect import Change, ChangeKind, Location
from tenon.locate import (
    AmbiguityReason,
    LocateReason,
    RustLocateConfig,
    SiteShape,
    locate_rust,
)

STRIPE = RustLocateConfig(sdk_package="stripe")
MAPPED = RustLocateConfig(
    sdk_package="stripe",
    operations={"POST /v1/charges": "Charge.create"},
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


def a_component_rename(before="amount", after="amount_cents"):
    return Change(
        kind=ChangeKind.RENAMED,
        location=Location(pointer=CHARGE_PROPERTIES),
        before=before,
        after=after,
        breaking=True,
        confidence="inferred",
    )


def an_operation_rename(before="amount", after="amount_cents"):
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
            "main.rs": "use stripe::Charge;\n"
            "\n"
            "fn main() {\n"
            "    Charge::create(&params);\n"
            "}\n"
        },
    )
    change = a_removed_endpoint()

    result = locate_rust(change, repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.rs", 4, 5, SiteShape.CALL, "create")]
    assert result.ambiguous == ()
    assert result.reason is None
    assert result.change is change


# Spec AC6: an operation field rename is certain at the literal on the call chain.
def test_an_operation_field_rename_is_certain_on_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Params};\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "    Charge::create(&params);\n"
            "}\n"
        },
    )

    result = locate_rust(an_operation_rename(), repo, MAPPED)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.rs", 4, 27, SiteShape.KEYWORD, "amount")]
    assert result.certain[0].line_text == "    let params = Params { amount: 100 };"
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: a component field rename is certain on the type chain.
def test_a_component_field_rename_is_certain_on_the_type_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Params;\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "}\n"
        },
    )

    result = locate_rust(a_component_rename(), repo, STRIPE)

    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in result.certain
    ] == [("main.rs", 4, 27, SiteShape.KEYWORD, "amount")]
    assert result.ambiguous == ()
    assert result.reason is None


# Spec AC6: an unrooted non-SDK call is an UNROOTED_RECEIVER candidate.
def test_an_unrooted_call_is_the_unrooted_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Charge;\n"
            "\n"
            "fn main() {\n"
            "    charges::create(&params);\n"
            "}\n"
        },
    )

    result = locate_rust(a_removed_endpoint(), repo, STRIPE)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNROOTED_RECEIVER
    assert group.symbol == "charges.create"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.rs", 4, 5, SiteShape.CALL, "create")]


# Spec AC6: a mapped field the repository does not spell is UNMAPPED_SYMBOL.
def test_an_unmapped_symbol_keeps_the_repository_spelling(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Params;\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "}\n"
        },
    )
    config = RustLocateConfig(
        sdk_package="stripe", fields={"Charge.amount": "amount_cents"}
    )

    result = locate_rust(a_component_rename(), repo, config)

    assert result.certain == ()
    assert result.reason is None
    assert len(result.ambiguous) == 1
    group = result.ambiguous[0]
    assert group.reason is AmbiguityReason.UNMAPPED_SYMBOL
    assert group.symbol == "amount"
    assert [
        (site.path, site.line, site.column, site.shape, site.symbol)
        for site in group.candidates
    ] == [("main.rs", 4, 27, SiteShape.KEYWORD, "amount")]


# Spec AC6: two resolving candidates are one MULTIPLE_CANDIDATES group.
def test_two_rooted_candidates_are_multiple_candidates(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::charges;\n"
            "\n"
            "fn main() {\n"
            "    charges::get();\n"
            "    charges::list();\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(
        path="/v1/charges/{id}",
        method="get",
        pointer="#/paths/~1v1~1charges~1{id}",
    )

    result = locate_rust(change, repo, STRIPE)

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
        ("main.rs", 4, 5, SiteShape.CALL, "get"),
        ("main.rs", 5, 5, SiteShape.CALL, "list"),
    ]


# Spec AC6: a change with no matching site is NO_SITES.
def test_an_operation_with_no_matching_call_has_no_sites(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Charge;\n"
            "\n"
            "fn main() {\n"
            "    Charge::create();\n"
            "}\n"
        },
    )
    change = a_removed_endpoint(
        path="/v1/nonexistent",
        method="get",
        pointer="#/paths/~1v1~1nonexistent",
    )

    result = locate_rust(change, repo, STRIPE)

    assert result.reason is LocateReason.NO_SITES
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC6: a repository without the crate is NO_SDK_IMPORT.
def test_a_repository_without_the_crate_has_no_sdk_import(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n    println!(\"hello\");\n}\n",
        },
    )

    result = locate_rust(a_component_rename(), repo, STRIPE)

    assert result.reason is LocateReason.NO_SDK_IMPORT
    assert result.certain == ()
    assert result.ambiguous == ()


# Spec AC1/M3: the Rust config and wrapper are part of the public surface.
def test_the_rust_api_is_exported():
    import tenon.locate as locate

    assert locate.RustLocateConfig is RustLocateConfig
    assert locate.locate_rust is locate_rust
    assert {"RustLocateConfig", "locate_rust"} <= set(locate.__all__)
