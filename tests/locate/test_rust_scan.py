"""The tree-sitter Rust scanner over temp ``.rs`` files."""

from tenon.locate import SiteShape
from tenon.locate.rust_scan import scan_rust
from tenon.locate.scan import Hit


def a_repo(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def a_hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


# Spec AC2: a simple `use` roots the imported name.
def test_a_simple_import_roots_the_call(tmp_path):
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

    result = scan_rust(repo, "stripe")

    assert result.modules == ("main.rs",)
    assert result.hits == (
        a_hit(repo, "main.rs", 4, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )
    assert result.dynamics == ()


# Spec AC2: a grouped import roots each name.
def test_a_grouped_import_roots_each_name(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Customer};\n"
            "\n"
            "fn main() {\n"
            "    Charge::create();\n"
            "    Customer::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
        a_hit(repo, "main.rs", 5, 5, SiteShape.CALL, "create", ("Customer", "create"), True),
    )


# Spec AC2: a nested group keeps the whole path after the crate root.
def test_a_nested_group_roots_the_whole_path(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{resources::{Charge, Customer as C}};\n"
            "\n"
            "fn main() {\n"
            "    Charge::create();\n"
            "    C::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Charge", "create"),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Customer", "create"),
            True,
        ),
    )


# Spec AC2: `as` aliases resolve to the canonical chain.
def test_an_as_alias_resolves_the_canonical_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::resources::Charge as C;\n"
            "\n"
            "fn main() {\n"
            "    C::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Charge", "create"),
            True,
        ),
    )


# Spec AC2: a crate alias roots the rest of the path.
def test_a_crate_alias_roots_the_rest_of_the_path(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe as s;\n"
            "\n"
            "fn main() {\n"
            "    s::Charge::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC2: `self` binds the prefix alias.
def test_self_binds_the_prefix_name(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::resources::{self, Charge};\n"
            "\n"
            "fn main() {\n"
            "    resources::Charge::create();\n"
            "    Charge::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Charge", "create"),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Charge", "create"),
            True,
        ),
    )


# Spec AC2: a module alias roots the rest of the path.
def test_a_module_alias_roots_the_rest_of_the_path(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::resources as r;\n"
            "\n"
            "fn main() {\n"
            "    r::Charge::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            5,
            SiteShape.CALL,
            "create",
            ("resources", "Charge", "create"),
            True,
        ),
    )


# Spec AC2: a glob roots no individual name; paths through the crate still root.
def test_a_glob_roots_only_paths_through_the_crate(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::*;\n"
            "\n"
            "fn main() {\n"
            "    Charge::create();\n"
            "    stripe::Charge::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.modules == ("main.rs",)
    assert result.hits == (
        a_hit(repo, "main.rs", 4, 5, SiteShape.CALL, "create", ("Charge", "create"), False),
        a_hit(repo, "main.rs", 5, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC2: the extern prelude roots a path whose first segment is the crate.
def test_a_bare_crate_path_roots_without_an_import(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n    stripe::Charge::create();\n}\n",
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.modules == ("main.rs",)
    assert result.hits == (
        a_hit(repo, "main.rs", 2, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC2/AC7: a file that never roots the crate contributes nothing.
def test_a_file_without_the_crate_contributes_nothing(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use other::Thing;\n"
            "\n"
            "fn main() {\n"
            "    Thing::create();\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.modules == ()
    assert result.hits == ()


# Spec AC3: a method call is unseen, never a hit.
def test_a_method_call_is_not_a_hit(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Charge;\n"
            "\n"
            "fn main() {\n"
            "    client.create(&params);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == ()


# Spec AC3: a non-SDK path is unrooted evidence.
def test_a_non_sdk_path_is_an_unrooted_call(tmp_path):
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

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            5,
            SiteShape.CALL,
            "create",
            ("charges", "create"),
            False,
        ),
    )


# Spec AC2: a file that only imports the crate is still a module.
def test_a_file_that_only_imports_the_crate_is_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "a.rs": "use stripe::Charge;\n",
            "b.rs": "use other::Thing;\n",
        },
    )

    assert scan_rust(repo, "stripe").modules == ("a.rs",)


# Spec AC2: a crate-rooted path alone is a module, no import needed.
def test_a_crate_rooted_path_alone_is_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "c.rs": "fn main() {\n    stripe::Charge::create();\n}\n",
        },
    )

    assert scan_rust(repo, "stripe").modules == ("c.rs",)


# Spec AC7: target, vendor, .git and hidden directories are skipped.
def test_skips_target_vendor_and_hidden_directories(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "target/bad.rs": "use stripe::Charge;\n",
            "vendor/bad.rs": "use stripe::Charge;\n",
            ".git/bad.rs": "use stripe::Charge;\n",
            ".hidden/bad.rs": "use stripe::Charge;\n",
            "pkg/good.rs": "use stripe::Charge;\n",
        },
    )

    assert scan_rust(repo, "stripe").modules == ("pkg/good.rs",)


# Spec AC7: the file order is deterministic.
def test_files_are_sorted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "b.rs": "use stripe::Charge;\n",
            "a.rs": "use stripe::Charge;\n",
            "nested/c.rs": "use stripe::Charge;\n",
        },
    )

    assert scan_rust(repo, "stripe").modules == ("a.rs", "b.rs", "nested/c.rs")


def test_a_parse_error_file_is_skipped(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "bad.rs": "use stripe::Charge\nfn main( {\n",
            "good.rs": "use stripe::Charge;\n",
        },
    )

    assert scan_rust(repo, "stripe").modules == ("good.rs",)


# Spec AC3: the hit carries the exact 1-based location and line text.
def test_a_call_hit_carries_the_exact_location_and_line_text(tmp_path):
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

    [hit] = scan_rust(repo, "stripe").hits

    assert (hit.path, hit.line, hit.column) == ("main.rs", 4, 5)
    assert hit.line_text == "    Charge::create();"


def test_scan_rust_is_deterministic(tmp_path):
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

    assert scan_rust(repo, "stripe") == scan_rust(repo, "stripe")


# Spec AC4: a standalone rooted literal keeps the type chain.
def test_a_standalone_struct_literal_emits_its_fields(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Params;\n"
            "\n"
            "fn main() {\n"
            '    let params = Params { amount: 100, currency: "usd" };\n'
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 4, 40, SiteShape.KEYWORD, "currency", ("Params",), True),
    )


# Spec AC4: an inline literal in a rooted call also carries the call chain.
def test_an_inline_struct_literal_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Params};\n"
            "\n"
            "fn main() {\n"
            "    Charge::create(Params { amount: 100 });\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
        a_hit(
            repo,
            "main.rs",
            4,
            29,
            SiteShape.KEYWORD,
            "amount",
            ("Charge", "create"),
            True,
        ),
        a_hit(repo, "main.rs", 4, 29, SiteShape.KEYWORD, "amount", ("Params",), True),
    )


# Spec AC4: a let-bound literal passed to a rooted call carries the call chain.
def test_a_bound_struct_literal_carries_the_call_chain(tmp_path):
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

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            27,
            SiteShape.KEYWORD,
            "amount",
            ("Charge", "create"),
            True,
        ),
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 5, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC4: a rebinding replaces the name and does not inherit the old struct.
def test_a_rebinding_does_not_inherit_the_old_struct(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Params};\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "    let params = Other { amount: 5 };\n"
            "    Charge::create(&params);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 6, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC5: a field access through a binding is an attribute on the type chain.
def test_a_field_access_through_a_binding_is_an_attribute(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Params;\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "    let amount = params.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 5, 25, SiteShape.ATTRIBUTE, "amount", ("Params",), True),
    )


# Spec AC5: a field access passed to a rooted call also carries the call chain.
def test_a_field_access_argument_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Params};\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100 };\n"
            "    Charge::create(&params.amount);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 5, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
        a_hit(
            repo,
            "main.rs",
            5,
            28,
            SiteShape.ATTRIBUTE,
            "amount",
            ("Charge", "create"),
            True,
        ),
        a_hit(repo, "main.rs", 5, 28, SiteShape.ATTRIBUTE, "amount", ("Params",), True),
    )


# Spec AC4: bindings are per enclosing function.
def test_bindings_are_not_shared_between_functions(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Charge, Params};\n"
            "\n"
            "fn first() {\n"
            "    let params = Params { amount: 100 };\n"
            "}\n"
            "\n"
            "fn second() {\n"
            "    Charge::create(&params);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(repo, "main.rs", 8, 5, SiteShape.CALL, "create", ("Charge", "create"), True),
    )


# Spec AC4: a scoped rooted type keeps the whole path.
def test_a_scoped_struct_literal_keeps_the_type_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::resources::Charge;\n"
            "\n"
            "fn main() {\n"
            "    let charge = Charge { amount: 1 };\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            4,
            27,
            SiteShape.KEYWORD,
            "amount",
            ("resources", "Charge"),
            True,
        ),
    )


# Spec AC4: `..Default::default()` is not a field, but its call is evidence.
def test_a_base_field_initializer_is_not_a_field(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Params;\n"
            "\n"
            "fn main() {\n"
            "    let params = Params { amount: 100, ..Default::default() };\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 27, SiteShape.KEYWORD, "amount", ("Params",), True),
        a_hit(
            repo,
            "main.rs",
            4,
            42,
            SiteShape.CALL,
            "default",
            ("Default", "default"),
            False,
        ),
    )


# Spec AC1: `Type::new` binds the type for a later member access.
def test_a_constructed_receiver_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(
            repo, "main.rs", 5, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC1: a crate-qualified `new` binds the type.
def test_a_crate_qualified_construction_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n"
            '    let client = stripe::Client::new("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 2, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(
            repo, "main.rs", 3, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC1: `default` is the other implicit constructor.
def test_a_default_constructed_receiver_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            "    let client = Client::default();\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "default", ("Client", "default"), True),
        a_hit(
            repo, "main.rs", 5, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC2: an annotated simple type binds the name.
def test_an_annotated_receiver_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            "    let client: Client = build();\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo, "main.rs", 5, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC2: a crate-qualified annotation binds the name.
def test_a_crate_qualified_annotation_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n"
            "    let client: stripe::Client = build();\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo, "main.rs", 3, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC2: an alias in the annotation resolves to the canonical type.
def test_an_aliased_annotation_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client as C;\n"
            "\n"
            "fn main() {\n"
            "    let client: C = build();\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(
            repo, "main.rs", 5, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC3: a mapped factory binds the mapped type.
def test_a_mapped_factory_receiver_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n"
            '    let client = make_client("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe", {"make_client": "Client"})

    assert result.hits == (
        a_hit(
            repo, "main.rs", 3, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC3: a crate-qualified factory matches the canonical key.
def test_a_crate_qualified_factory_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n"
            '    let client = stripe::make_client("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe", {"make_client": "Client"})

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            2,
            18,
            SiteShape.CALL,
            "make_client",
            ("make_client",),
            True,
        ),
        a_hit(
            repo, "main.rs", 3, 25, SiteShape.ATTRIBUTE, "amount", ("Client", "amount"), True
        ),
    )


# Spec AC3: the source dotted key also matches, with a multi-part mapped chain.
def test_a_source_dotted_factory_key_is_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "fn main() {\n"
            '    let client = stripe::make_client("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(
        repo, "stripe", {"stripe::make_client": "resources::Client"}
    )

    assert result.hits == (
        a_hit(
            repo,
            "main.rs",
            2,
            18,
            SiteShape.CALL,
            "make_client",
            ("make_client",),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            3,
            25,
            SiteShape.ATTRIBUTE,
            "amount",
            ("resources", "Client", "amount"),
            True,
        ),
    )


# Spec AC3: a factory with no mapping is not evidence.
def test_an_unmapped_factory_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = make_client("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == ()


# Spec AC5: a rebinding replaces the receiver type.
def test_a_rebinding_replaces_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::{Client, Customer};\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            '    let client = Customer::new("key");\n'
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(repo, "main.rs", 5, 18, SiteShape.CALL, "new", ("Customer", "new"), True),
        a_hit(repo, "main.rs", 6, 25, SiteShape.ATTRIBUTE, "amount", ("Customer", "amount"), True),
    )


# Spec AC5: a let without evidence clears the previous binding.
def test_a_let_without_evidence_clears_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            "    let client = build();\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
    )


# Spec AC4: a method chain emits the intermediate call and the full chain.
def test_a_method_chain_emits_the_intermediate_and_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            "    client.charges().create(&params);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "charges",
            ("Client", "charges"),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "create",
            ("Client", "charges", "create"),
            True,
        ),
    )


# Spec AC4: a field chain emits every prefix on a bound receiver.
def test_a_field_chain_emits_every_prefix(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            "    let id = client.charge.id;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(
            repo,
            "main.rs",
            5,
            21,
            SiteShape.ATTRIBUTE,
            "charge",
            ("Client", "charge"),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            5,
            28,
            SiteShape.ATTRIBUTE,
            "id",
            ("Client", "charge", "id"),
            True,
        ),
    )


# Spec AC4: a chain on an untracked receiver stays invisible.
def test_an_untracked_receiver_chain_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            "    let client = build();\n"
            "    client.charges().create(&params);\n"
            "    let amount = client.amount;\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == ()


# Spec AC4: parentheses around a bound receiver unwrap.
def test_a_parenthesized_receiver_chain_is_rooted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.rs": "use stripe::Client;\n"
            "\n"
            "fn main() {\n"
            '    let client = Client::new("key");\n'
            "    (client).charges().create(&params);\n"
            "}\n"
        },
    )

    result = scan_rust(repo, "stripe")

    assert result.hits == (
        a_hit(repo, "main.rs", 4, 18, SiteShape.CALL, "new", ("Client", "new"), True),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "charges",
            ("Client", "charges"),
            True,
        ),
        a_hit(
            repo,
            "main.rs",
            5,
            5,
            SiteShape.CALL,
            "create",
            ("Client", "charges", "create"),
            True,
        ),
    )
