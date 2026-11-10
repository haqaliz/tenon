"""The tree-sitter C# scanner over temp ``.cs`` files."""

from tenon.locate import SiteShape
from tenon.locate.csharp_scan import scan_csharp
from tenon.locate.scan import Hit

ROOT = "Stripe"


def a_repo(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def a_hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


# Spec AC2: a root using roots a simple type's static call.
def test_a_root_using_roots_the_call(tmp_path):
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

    result = scan_csharp(repo, ROOT)

    assert result.modules == ("main.cs",)
    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )
    assert result.dynamics == ()


# Spec AC2: a subnamespace using drops the subnamespace from the chain.
def test_a_subnamespace_using_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe.Services;\n"
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

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC2: `global using` behaves like a root using.
def test_a_global_using_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "global using Stripe;\n"
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

    result = scan_csharp(repo, ROOT)

    assert result.modules == ("main.cs",)
    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC2: an alias maps to the simple type name.
def test_an_alias_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Charge = Stripe.Charge;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        Charge.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("Charge", "Create"),
            True,
        ),
    )


# Spec AC2: a fully qualified root type roots without a using and is a module.
def test_a_qualified_root_type_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        Stripe.Services.ChargeService.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.modules == ("main.cs",)
    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            5,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC2: a dotted sdk package matches the whole namespace prefix.
def test_a_dotted_root_matches_the_whole_prefix(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        Stripe.Services.ChargeService.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, "Stripe.Services")

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            5,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC2: `using static` roots no type names but still marks the file.
def test_a_static_using_roots_no_type_names(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using static Stripe.ChargeHelpers;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        ChargeHelpers.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.modules == ("main.cs",)
    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("Create",),
            False,
        ),
    )


# Spec AC3: a tracked `new` binding roots the instance call.
def test_a_tracked_new_binding_roots_the_call(tmp_path):
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

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            8,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC3: a tracked `new` binding with a qualified type roots the call.
def test_a_tracked_qualified_new_binding_roots_the_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var service = new Stripe.Services.ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            6,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC3: a fluent chain stays unrooted with the chain after the base.
def test_a_fluent_chain_is_an_unrooted_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        client.Charges.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("Charges", "Create"),
            False,
        ),
    )


# Spec AC3: a member access on a non-SDK value is unrooted.
def test_a_non_sdk_member_access_is_an_unrooted_call(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run(Client client)\n"
            "    {\n"
            "        Stripe.ChargeService.Create(options);\n"
            "        client.Send(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            5,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            6,
            9,
            SiteShape.CALL,
            "Send",
            ("Send",),
            False,
        ),
    )


# Spec AC2: a file without a root using and a rooted type is not a module.
def test_a_file_without_the_root_is_not_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            '        Console.WriteLine("x");\n'
            "    }\n"
            "}\n",
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.modules == ()
    assert result.hits == ()


# Spec AC2: a file that only has the root using is still a module.
def test_a_file_that_only_has_the_root_using_is_a_module(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "a.cs": "using Stripe;\n",
            "b.cs": "using System;\n",
        },
    )

    assert scan_csharp(repo, ROOT).modules == ("a.cs",)


# Spec AC7: bin, obj, .git and hidden directories are skipped.
def test_skips_bin_obj_git_and_hidden_directories(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "bin/bad.cs": "using Stripe;\n",
            "obj/bad.cs": "using Stripe;\n",
            ".git/bad.cs": "using Stripe;\n",
            ".hidden/bad.cs": "using Stripe;\n",
            "src/good.cs": "using Stripe;\n",
        },
    )

    assert scan_csharp(repo, ROOT).modules == ("src/good.cs",)


# Spec AC7: the file order is deterministic.
def test_files_are_sorted(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "b.cs": "using Stripe;\n",
            "a.cs": "using Stripe;\n",
            "nested/c.cs": "using Stripe;\n",
        },
    )

    assert scan_csharp(repo, ROOT).modules == ("a.cs", "b.cs", "nested/c.cs")


# Spec AC3: the hit carries the exact 1-based location and line text.
def test_a_call_hit_carries_the_exact_location_and_line_text(tmp_path):
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

    [hit] = scan_csharp(repo, ROOT).hits

    assert (hit.path, hit.line, hit.column) == ("main.cs", 7, 9)
    assert hit.line_text == "        ChargeService.Create(options);"


def test_scan_csharp_is_deterministic(tmp_path):
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

    assert scan_csharp(repo, ROOT) == scan_csharp(repo, ROOT)


# Spec AC4: a standalone rooted initializer emits its properties on the type chain.
def test_a_standalone_initializer_emits_its_properties(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            '        var options = new ChargeCreateOptions { AmountCents = 100, Currency = "usd" };\n'
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            7,
            68,
            SiteShape.KEYWORD,
            "Currency",
            ("ChargeCreateOptions",),
            True,
        ),
    )


# Spec AC4: an inline initializer in a rooted call carries the type and call chains.
def test_an_inline_initializer_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        ChargeService.Create(new ChargeCreateOptions { AmountCents = 100 });\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            7,
            56,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            7,
            56,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: a bound initializer passed to a rooted call carries the call chain.
def test_a_bound_initializer_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { AmountCents = 100 };\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            9,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: a rebinding replaces the name and does not inherit the old type.
def test_a_rebinding_does_not_inherit_the_old_type(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { AmountCents = 100 };\n"
            "        options = new Acme.OtherThing { AmountCents = 5 };\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            10,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: a rebound rooted initializer carries its new properties.
def test_a_rebinding_to_a_rooted_initializer_replaces_the_properties(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { AmountCents = 100 };\n"
            '        options = new ChargeCreateOptions { Currency = "usd" };\n'
            "        var service = new ChargeService();\n"
            "        service.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            8,
            45,
            SiteShape.KEYWORD,
            "Currency",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            8,
            45,
            SiteShape.KEYWORD,
            "Currency",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            10,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC5: a tracked binding's property access is an ATTRIBUTE hit on the type chain.
def test_a_property_access_is_an_attribute_on_the_type_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions();\n"
            "        var amount = options.AmountCents;\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            8,
            30,
            SiteShape.ATTRIBUTE,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
    )


# Spec AC5: a property access argument carries the type chain and the call chain.
def test_a_property_access_argument_carries_the_call_chain(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions();\n"
            "        var service = new ChargeService();\n"
            "        service.Create(options.AmountCents);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            9,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            9,
            32,
            SiteShape.ATTRIBUTE,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            9,
            32,
            SiteShape.ATTRIBUTE,
            "AmountCents",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: bindings are per member scope.
def test_bindings_are_not_shared_between_methods(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void First()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { AmountCents = 100 };\n"
            "    }\n"
            "\n"
            "    void Second()\n"
            "    {\n"
            "        ChargeService.Create(options);\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            12,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: parentheses around an argument and an initializer are unwrapped.
def test_parentheses_are_unwrapped(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var options = new ChargeCreateOptions { AmountCents = 100 };\n"
            "        var service = new ChargeService();\n"
            "        service.Create((options));\n"
            '        ChargeService.Create((new ChargeCreateOptions { Currency = "usd" }));\n'
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.hits == (
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            7,
            49,
            SiteShape.KEYWORD,
            "AmountCents",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            9,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            10,
            9,
            SiteShape.CALL,
            "Create",
            ("ChargeService", "Create"),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            10,
            57,
            SiteShape.KEYWORD,
            "Currency",
            ("ChargeCreateOptions",),
            True,
        ),
        a_hit(
            repo,
            "main.cs",
            10,
            57,
            SiteShape.KEYWORD,
            "Currency",
            ("ChargeService", "Create"),
            True,
        ),
    )


# Spec AC4: an initializer on a type outside the root emits nothing.
def test_an_initializer_on_a_non_rooted_type_emits_nothing(tmp_path):
    repo = a_repo(
        tmp_path,
        {
            "main.cs": "using Stripe;\n"
            "\n"
            "class ChargeRunner\n"
            "{\n"
            "    void Run()\n"
            "    {\n"
            "        var other = new Acme.OtherThing { AmountCents = 5 };\n"
            "    }\n"
            "}\n"
        },
    )

    result = scan_csharp(repo, ROOT)

    assert result.modules == ("main.cs",)
    assert result.hits == ()
