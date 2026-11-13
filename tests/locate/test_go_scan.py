"""The tree-sitter Go scanner over temp ``.go`` files."""

from tenon.locate import SiteShape
from tenon.locate.go_scan import scan_go
from tenon.locate.scan import Hit

STRIPE = "github.com/stripe/stripe-go/v76"


def a_repo(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def a_hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


def a_attributes(result):
    return [
        (hit.symbol, hit.rooted)
        for hit in result.hits
        if hit.shape is SiteShape.ATTRIBUTE
    ]


# Spec AC2: the root import's inferred package name roots its calls.
def test_a_root_import_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    stripe.Charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.modules == ("main.go",)
    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
    )
    assert result.dynamics == ()


# Spec AC2: a subpackage import keeps the canonical prefix in the chain.
def test_a_subpackage_import_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}/charge"\n'
            "\n"
            "func main() {\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.modules == ("main.go",)
    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("charge", "New"), True),
    )


# Spec AC2: an explicit alias wins over inference.
def test_an_alias_resolves_the_canonical_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import s "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    s.Charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
    )


# Spec AC2: grouped imports, raw strings and aliases all resolve.
def test_a_grouped_import_resolves_each_name(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            '    "fmt"\n'
            f'    s "{STRIPE}"\n'
            f"    `{STRIPE}/charge`\n"
            ")\n"
            "\n"
            "func main() {\n"
            "    s.Charge.New(params)\n"
            "    charge.New(params)\n"
            '    fmt.Println("x")\n'
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 10, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
        a_hit(repo, "main.go", 11, 5, SiteShape.CALL, "New", ("charge", "New"), True),
        a_hit(repo, "main.go", 12, 5, SiteShape.CALL, "Println", ("Println",), False),
    )


# Spec AC2: `_` and `.` imports root no names but still make the file a module.
def test_blank_and_dot_imports_root_no_names(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "blank.go": "package main\n"
            "\n"
            f'import _ "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    charge.New(params)\n"
            "}\n",
            "dot.go": "package main\n"
            "\n"
            f'import . "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    Charge.New(params)\n"
            "}\n",
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.modules == ("blank.go", "dot.go")
    assert result.hits == (
        a_hit(repo, "blank.go", 6, 5, SiteShape.CALL, "New", ("New",), False),
        a_hit(repo, "dot.go", 6, 5, SiteShape.CALL, "New", ("New",), False),
    )


# Spec AC2: a trailing `vN` yields the segment before it as the package name.
def test_inference_uses_the_segment_before_a_version(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            'import "example.com/sdk/v2"\n'
            "\n"
            "func main() {\n"
            "    sdk.Charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, "example.com/sdk/v2")

    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
    )


# Spec AC2: a trailing `-go` is stripped to infer the package name.
def test_inference_strips_a_trailing_go_suffix(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            'import "example.com/acme/stripe-go"\n'
            "\n"
            "func main() {\n"
            "    stripe.Charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, "example.com/acme/stripe-go")

    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
    )


# Spec AC2: `package_name` overrides the root import's inference.
def test_package_name_overrides_the_root_inference(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    acme.Charge.New(params)\n"
            "    stripe.Charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, package_name="acme")

    assert result.hits == (
        a_hit(repo, "main.go", 6, 5, SiteShape.CALL, "New", ("Charge", "New"), True),
        a_hit(repo, "main.go", 7, 5, SiteShape.CALL, "New", ("Charge", "New"), False),
    )


# Spec AC2: a file that never imports the root is not a module.
def test_a_file_without_the_root_is_not_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            'import "fmt"\n'
            "\n"
            "func main() {\n"
            '    fmt.Println("x")\n'
            "}\n",
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.modules == ()
    assert result.hits == ()


# Spec AC2: a file that only imports the root is still a module.
def test_a_file_that_only_imports_the_root_is_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "a.go": f'package main\n\nimport "{STRIPE}"\n',
            "b.go": 'package main\n\nimport "fmt"\n',
        },
    )

    assert scan_go(repo, STRIPE).modules == ("a.go",)


# Spec AC3: a method chain on a local value is an unrooted call.
def test_a_method_chain_is_an_unrooted_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(
            repo,
            "main.go",
            6,
            5,
            SiteShape.CALL,
            "New",
            ("Charges", "New"),
            False,
        ),
    )


# Spec AC3: a non-SDK package selector is unrooted evidence.
def test_a_non_sdk_selector_is_an_unrooted_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            'import "fmt"\n'
            "\n"
            "func main() {\n"
            '    fmt.Println("x")\n'
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 7, 5, SiteShape.CALL, "Println", ("Println",), False),
    )


# Spec AC7: vendor, testdata, .git and hidden directories are skipped.
def test_skips_vendor_testdata_and_hidden_directories(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "vendor/bad.go": f'package main\n\nimport "{STRIPE}"\n',
            "testdata/bad.go": f'package main\n\nimport "{STRIPE}"\n',
            ".git/bad.go": f'package main\n\nimport "{STRIPE}"\n',
            ".hidden/bad.go": f'package main\n\nimport "{STRIPE}"\n',
            "pkg/good.go": f'package main\n\nimport "{STRIPE}"\n',
        },
    )

    assert scan_go(repo, STRIPE).modules == ("pkg/good.go",)


# Spec AC7: the file order is deterministic.
def test_files_are_sorted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "b.go": f'package main\n\nimport "{STRIPE}"\n',
            "a.go": f'package main\n\nimport "{STRIPE}"\n',
            "nested/c.go": f'package main\n\nimport "{STRIPE}"\n',
        },
    )

    assert scan_go(repo, STRIPE).modules == ("a.go", "b.go", "nested/c.go")


def test_a_parse_error_file_is_skipped(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "bad.go": f'package main\n\nimport "{STRIPE}"\n\nfunc main( {{\n',
            "good.go": f'package main\n\nimport "{STRIPE}"\n',
        },
    )

    assert scan_go(repo, STRIPE).modules == ("good.go",)


# Spec AC3: the hit carries the exact 1-based location and line text.
def test_a_call_hit_carries_the_exact_location_and_line_text(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    stripe.Charge.New(params)\n"
            "}\n"
        },
    )

    [hit] = scan_go(repo, STRIPE).hits

    assert (hit.path, hit.line, hit.column) == ("main.go", 6, 5)
    assert hit.line_text == "    stripe.Charge.New(params)"


def test_scan_go_is_deterministic(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    stripe.Charge.New(params)\n"
            "}\n"
        },
    )

    assert scan_go(repo, STRIPE) == scan_go(repo, STRIPE)


# Spec AC4: a standalone rooted literal emits its keys on the type chain.
def test_a_standalone_literal_emits_its_keys(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            '    params := &stripe.ChargeParams{Amount: stripe.Int64(100), Currency: "usd"}\n'
            "    other := charge.Params{Amount: 5}\n"
            "    _, _ = params, other\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 9, 44, SiteShape.CALL, "Int64", ("Int64",), True),
        a_hit(repo, "main.go", 9, 63, SiteShape.KEYWORD, "Currency", ("ChargeParams",), True),
        a_hit(repo, "main.go", 10, 28, SiteShape.KEYWORD, "Amount", ("charge", "Params"), True),
    )


# Spec AC4: an inline literal in a rooted call carries the call chain too.
def test_an_inline_literal_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    charge.New(stripe.ChargeParams{Amount: 100})\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 5, SiteShape.CALL, "New", ("charge", "New"), True),
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("charge", "New"), True),
    )


# Spec AC4: a bound literal passed to a rooted call carries the call chain.
def test_a_bound_literal_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("charge", "New"), True),
        a_hit(repo, "main.go", 10, 5, SiteShape.CALL, "New", ("charge", "New"), True),
    )


# Spec AC4: a `var` with only a rooted type binds the name for field access.
def test_a_type_only_var_binds_for_field_access(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var params stripe.ChargeParams\n"
            "    amount := params.Amount\n"
            "    _ = amount\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(
            repo,
            "main.go",
            7,
            22,
            SiteShape.ATTRIBUTE,
            "Amount",
            ("ChargeParams", "Amount"),
            True,
        ),
    )


# Spec AC4: a rebinding replaces the name and does not inherit the old type.
def test_a_rebinding_does_not_inherit_the_old_type(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    params = other.Thing{Amount: 5}\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 11, 5, SiteShape.CALL, "New", ("charge", "New"), True),
    )


# Spec AC5: a field access argument carries the type chain and the call chain.
def test_a_field_access_argument_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    charge.New(params.Amount)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 10, 5, SiteShape.CALL, "New", ("charge", "New"), True),
        a_hit(
            repo,
            "main.go",
            10,
            23,
            SiteShape.ATTRIBUTE,
            "Amount",
            ("ChargeParams",),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            10,
            23,
            SiteShape.ATTRIBUTE,
            "Amount",
            ("charge", "New"),
            True,
        ),
    )


# Spec AC4: bindings are per enclosing function.
def test_bindings_are_not_shared_between_functions(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func first() {\n"
            "    params := &stripe.ChargeParams{Amount: 100}\n"
            "    _ = params\n"
            "}\n"
            "\n"
            "func second() {\n"
            "    amount := params.Amount\n"
            "    _ = amount\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 36, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
    )


# Spec AC4: `&` and parentheses are unwrapped for a binding and an argument.
def test_parentheses_and_address_of_are_unwrapped(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    params := (&stripe.ChargeParams{Amount: 100})\n"
            "    charge.New((&params))\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 37, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 9, 37, SiteShape.KEYWORD, "Amount", ("charge", "New"), True),
        a_hit(repo, "main.go", 10, 5, SiteShape.CALL, "New", ("charge", "New"), True),
    )


# Spec AC4: a `var` with a rooted literal binds the name.
def test_a_var_with_a_rooted_literal_binds_the_name(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            "import (\n"
            f'    "{STRIPE}"\n'
            f'    "{STRIPE}/charge"\n'
            ")\n"
            "\n"
            "func main() {\n"
            "    var params = stripe.ChargeParams{Amount: 100}\n"
            "    charge.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(repo, "main.go", 9, 38, SiteShape.KEYWORD, "Amount", ("ChargeParams",), True),
        a_hit(repo, "main.go", 9, 38, SiteShape.KEYWORD, "Amount", ("charge", "New"), True),
        a_hit(repo, "main.go", 10, 5, SiteShape.CALL, "New", ("charge", "New"), True),
    )


# Spec AC1: a pointer annotation binds the receiver type.
def test_a_pointer_annotation_binds_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var client *stripe.Client\n"
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC1: a value annotation binds the receiver type.
def test_a_value_annotation_binds_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var client stripe.Client\n"
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC2: an address-of composite binds the receiver type.
def test_an_address_of_composite_binds_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := &stripe.Client{ID: "x"}\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC2: a value composite binds the receiver type.
def test_a_value_composite_binds_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    client := stripe.Client{}\n"
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC3: a source dotted factory key binds the mapped type.
def test_a_source_dotted_factory_key_binds_the_mapped_type(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"stripe.NewClient": "Client"})

    assert a_attributes(result) == [("Charges", True)]


# Spec AC3: a canonical factory key drops the package prefix.
def test_a_canonical_factory_key_binds_the_mapped_type(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}/charge"\n'
            "\n"
            "func main() {\n"
            '    client := charge.NewClient("k")\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert a_attributes(result) == [("Charges", True)]


# Spec AC3: a subpackage key matches the source chain.
def test_a_subpackage_factory_key_matches_the_source_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}/charge"\n'
            "\n"
            "func main() {\n"
            '    client := charge.New("k")\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"charge.New": "Client"})

    assert a_attributes(result) == [("Charges", True)]


# Spec AC3: an unmapped factory is not evidence.
def test_an_unmapped_factory_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.Unknown("k")\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert a_attributes(result) == []


# Spec AC5: a rebinding without evidence clears the receiver.
def test_a_rebinding_without_evidence_clears_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client = other.Thing\n"
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert a_attributes(result) == []


# Spec AC5: a rebinding with new evidence replaces the receiver.
def test_a_rebinding_with_new_evidence_replaces_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var client *stripe.Old\n"
            '    client = stripe.NewClient("k")\n'
            "    client.Charges\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert a_attributes(result) == [("Charges", True)]


# Spec AC4: a mapped receiver's call chain is rooted, with its intermediate selector.
def test_a_receiver_call_chain_is_rooted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "New",
            ("Client", "Charges", "New"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            7,
            12,
            SiteShape.ATTRIBUTE,
            "Charges",
            ("Client", "Charges"),
            True,
        ),
    )


# Spec AC4: an intermediate receiver call emits its prefix too.
def test_an_intermediate_receiver_call_emits_its_prefix(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client.Charges().New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "Charges",
            ("Client", "Charges"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "New",
            ("Client", "Charges", "New"),
            True,
        ),
    )


# Spec AC4: a field access on a bound receiver is a rooted attribute chain.
def test_a_receiver_field_access_is_rooted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    id := client.ID\n"
            "    _ = id\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            7,
            18,
            SiteShape.ATTRIBUTE,
            "ID",
            ("Client", "ID"),
            True,
        ),
    )


# Spec AC4: an untracked receiver chain keeps the unrooted call behavior.
def test_an_untracked_receiver_chain_stays_unrooted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.Unknown("k")\n'
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "Unknown", ("Unknown",), True),
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "New",
            ("Charges", "New"),
            False,
        ),
    )


# Spec AC4: a local receiver binding wins over a package alias with the same name.
def test_a_receiver_binding_wins_over_the_package_alias(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var stripe *stripe.Client\n"
            "    stripe.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "New",
            ("Client", "Charges", "New"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            7,
            12,
            SiteShape.ATTRIBUTE,
            "Charges",
            ("Client", "Charges"),
            True,
        ),
    )


# Spec AC3/AC4: a mapped multi-part type chain prefixes every receiver hit.
def test_a_mapped_multi_part_type_chain_prefixes_the_hits(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client.Session"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            7,
            5,
            SiteShape.CALL,
            "New",
            ("Client", "Session", "Charges", "New"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            7,
            12,
            SiteShape.ATTRIBUTE,
            "Charges",
            ("Client", "Session", "Charges"),
            True,
        ),
    )


# Spec AC5: a rebinding with new evidence replaces the receiver chain.
def test_a_rebinding_chain_uses_the_new_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    var client *stripe.Old\n"
            '    client = stripe.NewClient("k")\n'
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Customer"})

    assert result.hits == (
        a_hit(repo, "main.go", 7, 14, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            8,
            5,
            SiteShape.CALL,
            "New",
            ("Customer", "Charges", "New"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            8,
            12,
            SiteShape.ATTRIBUTE,
            "Charges",
            ("Customer", "Charges"),
            True,
        ),
    )


# Spec AC5: a rebinding without evidence clears the receiver chain.
def test_a_cleared_receiver_chain_stays_unrooted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            '    client := stripe.NewClient("k")\n'
            "    client = other.Thing\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE, receivers={"NewClient": "Client"})

    assert result.hits == (
        a_hit(repo, "main.go", 6, 15, SiteShape.CALL, "NewClient", ("NewClient",), True),
        a_hit(
            repo,
            "main.go",
            8,
            5,
            SiteShape.CALL,
            "New",
            ("Charges", "New"),
            False,
        ),
    )


# Spec AC2: a same-file helper's annotated pointer result roots the receiver.
def test_a_typed_helper_result_roots_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() *stripe.Client {\n"
            "    return nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert result.hits == (
        a_hit(
            repo,
            "main.go",
            11,
            5,
            SiteShape.CALL,
            "New",
            ("Client", "Charges", "New"),
            True,
        ),
        a_hit(
            repo,
            "main.go",
            11,
            12,
            SiteShape.ATTRIBUTE,
            "Charges",
            ("Client", "Charges"),
            True,
        ),
    )


# Spec AC2: a same-file helper's value result roots the receiver through `var`.
def test_a_value_helper_result_roots_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() stripe.Client {\n"
            "    return stripe.Client{}\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    var client = newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC2: the first type of a result list roots the receiver.
def test_a_result_list_first_type_roots_the_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() (stripe.Client, error) {\n"
            "    return stripe.Client{}, nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client, err := newClient()\n"
            "    _ = err\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == [("Charges", True)]


# Spec AC2: a helper without a result type is no evidence.
def test_an_unannotated_helper_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() {}\n"
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []


# Spec AC2: a non-SDK result type is no evidence.
def test_a_non_sdk_helper_result_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() *other.Client {\n"
            "    return nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []


# Spec AC2: a named result is no evidence.
def test_a_named_result_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() (client *stripe.Client) {\n"
            "    return nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []


# Spec AC2: an `error` first result is no evidence.
def test_an_error_first_result_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() (error, *stripe.Client) {\n"
            "    return nil, nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client, _ := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []


# Spec AC2: a helper defined in another file is no evidence.
def test_a_cross_file_helper_is_not_evidence(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "helper.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() *stripe.Client {\n"
            "    return nil\n"
            "}\n",
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client.Charges.New(params)\n"
            "}\n",
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []


# Spec AC2: a rebinding without evidence clears the inferred receiver.
def test_a_rebinding_without_evidence_clears_the_inferred_receiver(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.go": "package main\n"
            "\n"
            f'import "{STRIPE}"\n'
            "\n"
            "func newClient() *stripe.Client {\n"
            "    return nil\n"
            "}\n"
            "\n"
            "func main() {\n"
            "    client := newClient()\n"
            "    client = other.Thing\n"
            "    client.Charges.New(params)\n"
            "}\n"
        },
    )

    result = scan_go(repo, STRIPE)

    assert a_attributes(result) == []
