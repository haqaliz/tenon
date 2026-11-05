"""The tree-sitter TS/JS scanner over committed fixture repositories."""

from pathlib import Path

from tenon.locate import SiteShape
from tenon.locate.scan import Dynamic, DynamicKind, Hit, _Source
from tenon.locate.ts_scan import (
    _aliases,
    _bindings,
    _grammar,
    _parser,
    _resolve_relative,
    scan_ts,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "repos"
SDK_BASIC = FIXTURES / "ts-sdk-basic"
SDK_CJS = FIXTURES / "ts-cjs"
SDK_JS = FIXTURES / "ts-js"
SDK_TSX = FIXTURES / "ts-tsx"
SDK_DECOY = FIXTURES / "ts-decoy"
SDK_NO_SDK = FIXTURES / "ts-no-sdk"

IGNORED_DIRECTORIES = (
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "out",
    "coverage",
    ".turbo",
    "__pycache__",
)
EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


def parse_ts(text, suffix=".ts"):
    return _parser(_grammar(suffix)).parse(text.encode("utf-8"))


def bindings(text, sdk_package="stripe"):
    return _bindings(parse_ts(text), sdk_package)


def rooted(text, sdk_package="stripe"):
    tree = parse_ts(text)
    roots, classes = _bindings(tree, sdk_package)
    source = _Source("m.ts", tuple(text.split("\n")))
    return _aliases(tree, roots, classes, sdk_package, source)


# Phase 1: discovery, grammar selection and skipped files.
def test_scan_ts_discovers_modules_that_import_the_sdk():
    result = scan_ts(SDK_BASIC, "stripe")

    assert "src/billing.ts" in result.modules
    assert "src/unrelated.ts" not in result.modules


def test_scan_ts_parses_every_extension(tmp_path):
    for extension in EXTENSIONS:
        (tmp_path / f"file{extension}").write_text(
            'import Stripe from "stripe";\nconst client = new Stripe();\n',
            encoding="utf-8",
        )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == tuple(sorted(f"file{extension}" for extension in EXTENSIONS))


def test_scan_ts_skips_ignored_directories(tmp_path):
    for ignored in IGNORED_DIRECTORIES + (".hidden",):
        (tmp_path / ignored).mkdir()
        (tmp_path / ignored / "bad.ts").write_text(
            'import Stripe from "stripe";\n', encoding="utf-8"
        )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "good.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("pkg/good.ts",)


def test_scan_ts_skips_a_parse_error_file():
    result = scan_ts(SDK_BASIC, "stripe")

    assert "src/broken.ts" not in result.modules
    assert "src/billing.ts" in result.modules


def test_scan_ts_skips_an_undecodable_file(tmp_path):
    (tmp_path / "bad.ts").write_bytes(b'\xff\xfeimport Stripe from "stripe";\n')
    (tmp_path / "good.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("good.ts",)


# Phase 2: import bindings and reachability.
def test_default_import_binds_the_constructor():
    roots, classes = bindings('import Stripe from "stripe";\n')

    assert roots == {"Stripe": ("stripe", "Stripe")}
    assert classes == {"Stripe"}


def test_named_imports_bind_their_names_and_aliases():
    roots, classes = bindings('import { Stripe, charges as api } from "stripe";\n')

    assert roots == {"Stripe": ("stripe", "Stripe"), "api": ("stripe", "charges")}
    assert classes == {"Stripe", "api"}


def test_namespace_import_binds_the_module():
    roots, classes = bindings('import * as stripe from "stripe";\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_import_equals_binds_the_module():
    roots, classes = bindings('import stripe = require("stripe");\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_required_module_binds_the_module():
    roots, classes = bindings('const stripe = require("stripe");\n')

    assert roots == {"stripe": ("stripe",)}
    assert classes == set()


def test_required_object_destructuring_binds_its_members():
    roots, classes = bindings(
        'const { Stripe, charges: c } = require("stripe");\n'
    )

    assert roots == {"Stripe": ("stripe", "Stripe"), "c": ("stripe", "charges")}
    assert classes == {"Stripe", "c"}


def test_subpath_import_keeps_the_relative_chain():
    roots, classes = bindings('import { create } from "stripe/charges";\n')

    assert roots == {"create": ("stripe", "charges", "create")}
    assert classes == {"create"}


def test_scoped_package_and_its_subpath_match():
    roots, _ = bindings(
        'import { X } from "@acme/sdk/sub";\n', sdk_package="@acme/sdk"
    )

    assert roots == {"X": ("@acme", "sdk", "sub", "X")}


def test_type_only_imports_bind_nothing():
    roots, _ = bindings(
        'import type { Stripe } from "stripe";\n'
        'import type Stripe from "stripe";\n'
        'import { type Charge, Session } from "stripe";\n'
    )

    assert roots == {"Session": ("stripe", "Session")}


def test_bare_import_binds_nothing():
    assert bindings('import "stripe";\n') == ({}, set())


def test_bare_require_call_binds_nothing():
    assert bindings('require("stripe");\n') == ({}, set())


def test_non_sdk_and_relative_imports_bind_nothing():
    assert bindings(
        'import x from "other";\nimport y from "./local";\n'
        'const z = require(name);\n'
    ) == ({}, set())


def test_scan_ts_reaches_transitive_importers():
    result = scan_ts(SDK_BASIC, "stripe")

    assert result.modules == ("src/billing.ts", "src/reporting.ts")


def test_resolve_relative_prefers_exact_then_extension_then_index():
    files = {"src/exact.ts", "src/a.ts", "src/b.tsx", "src/dir/index.js"}

    assert _resolve_relative("src/app.ts", "./exact.ts", files) == "src/exact.ts"
    assert _resolve_relative("src/app.ts", "./a", files) == "src/a.ts"
    assert _resolve_relative("src/app.ts", "./b", files) == "src/b.tsx"
    assert _resolve_relative("src/app.ts", "./dir", files) == "src/dir/index.js"
    assert _resolve_relative("src/app.ts", "./missing", files) is None


def test_scan_ts_reaches_a_module_that_imports_the_sdk_importer(tmp_path):
    (tmp_path / "hub.ts").write_text(
        'import Stripe from "stripe";\n', encoding="utf-8"
    )
    (tmp_path / "app.ts").write_text('import { x } from "./hub";\n', encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "report.mts").write_text(
        'import { x } from "../hub";\n', encoding="utf-8"
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.modules == ("app.ts", "hub.ts", "lib/report.mts")


def test_scan_ts_ignores_an_unresolvable_relative_import(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\nimport "./missing";\n', encoding="utf-8"
    )

    assert scan_ts(tmp_path, "stripe").modules == ("app.ts",)


def test_scan_ts_has_no_modules_without_an_sdk_import():
    assert scan_ts(SDK_NO_SDK, "stripe").modules == ()


def test_scan_ts_ignores_type_only_imports_for_reachability(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import type { Stripe } from "stripe";\ntype Client = Stripe;\n',
        encoding="utf-8",
    )

    assert scan_ts(tmp_path, "stripe").modules == ()


def test_scan_ts_reaches_modules_imported_by_require():
    result = scan_ts(SDK_CJS, "stripe")

    assert result.modules == (
        "app.cjs",
        "lib/client.cjs",
        "lib/import-equals.cts",
        "lib/named.cjs",
    )


def test_scan_ts_finds_js_and_tsx_modules():
    assert scan_ts(SDK_JS, "stripe").modules == (
        "app.mjs",
        "component.jsx",
        "lib/util.js",
    )
    assert scan_ts(SDK_TSX, "stripe").modules == ("src/app.tsx",)


def test_scan_ts_reaches_the_sdk_importer_but_not_an_unrelated_module():
    result = scan_ts(SDK_DECOY, "stripe")

    assert result.modules == ("src/sdk.ts",)
    assert "src/unrelated.ts" not in result.modules
    assert "src/format.ts" not in result.modules


# Phase 3: one-hop aliases.
def test_alias_from_a_new_expression_is_rooted():
    aliases, class_aliases, dynamics = rooted(
        'import Stripe from "stripe";\nconst client = new Stripe("sk");\n'
    )

    assert aliases == {"client": ("stripe",)}
    assert class_aliases == {"client"}
    assert dynamics == []


def test_alias_from_a_constructor_call_is_rooted():
    aliases, class_aliases, _ = rooted(
        'import Stripe from "stripe";\nconst client = Stripe();\n'
    )

    assert aliases == {"client": ("stripe",)}
    assert class_aliases == {"client"}


def test_alias_of_the_namespace_is_rooted():
    aliases, class_aliases, _ = rooted(
        'import * as stripe from "stripe";\nconst s = stripe;\n'
    )

    assert aliases == {"s": ("stripe",)}
    assert class_aliases == set()


def test_alias_of_a_rooted_member_is_rooted():
    aliases, class_aliases, _ = rooted(
        'import * as stripe from "stripe";\nconst charges = stripe.charges;\n'
    )

    assert aliases == {"charges": ("stripe", "charges")}
    assert class_aliases == set()


def test_object_destructuring_binds_shorthand_and_renamed_members():
    aliases, class_aliases, _ = rooted(
        'import * as stripe from "stripe";\n'
        "const { balance, charges: c } = stripe;\n"
    )

    assert aliases == {
        "balance": ("stripe", "balance"),
        "c": ("stripe", "charges"),
    }
    assert class_aliases == set()


def test_alias_value_unwraps_parentheses_as_satisfies_and_non_null():
    aliases, _, _ = rooted(
        'import * as stripe from "stripe";\n'
        "const a = (stripe);\n"
        "const b = stripe as any;\n"
        "const c = stripe!;\n"
        "const d = stripe satisfies X;\n"
    )

    assert aliases == {
        "a": ("stripe",),
        "b": ("stripe",),
        "c": ("stripe",),
        "d": ("stripe",),
    }


def test_alias_of_a_class_import_keeps_class_certainty():
    aliases, class_aliases, _ = rooted(
        'import { Stripe } from "stripe";\nconst direct = Stripe;\n'
    )

    assert aliases == {"direct": ("stripe", "Stripe")}
    assert class_aliases == {"direct"}


def test_alias_inside_a_function_is_rooted():
    aliases, _, _ = rooted(
        'import Stripe from "stripe";\n'
        "export function build() {\n"
        "  const client = new Stripe();\n"
        "  return client;\n"
        "}\n"
    )

    assert aliases == {"client": ("stripe",)}


def test_assignment_of_a_rooted_member_creates_an_alias():
    aliases, _, _ = rooted(
        'import * as stripe from "stripe";\nlet s;\ns = stripe.charges;\n'
    )

    assert aliases == {"s": ("stripe", "charges")}


def test_redeclaration_drops_the_alias():
    aliases, class_aliases, _ = rooted(
        'import Stripe from "stripe";\n'
        "let client = new Stripe();\n"
        "client = other;\n"
    )

    assert aliases == {}
    assert class_aliases == set()


def test_one_hop_alias_of_an_alias_is_rooted():
    aliases, class_aliases, dynamics = rooted(
        'import Stripe from "stripe";\n'
        "const client = new Stripe();\n"
        "const c = client;\n"
    )

    assert aliases == {"client": ("stripe",), "c": ("stripe",)}
    assert class_aliases == {"client", "c"}
    assert dynamics == []


def test_second_hop_alias_is_a_dynamic():
    aliases, class_aliases, dynamics = rooted(
        'import Stripe from "stripe";\n'
        "const client = new Stripe();\n"
        "const c = client;\n"
        "const d = c;\n"
    )

    assert set(aliases) == {"client", "c"}
    assert class_aliases == {"client", "c"}
    assert dynamics == [Dynamic("m.ts", 4, 7, DynamicKind.ALIAS_CHAIN, "d")]


def test_nested_destructuring_is_an_alias_chain():
    aliases, _, dynamics = rooted(
        'import * as stripe from "stripe";\n'
        "const { charges: { create } } = stripe;\n"
    )

    assert aliases == {}
    assert dynamics == [Dynamic("m.ts", 2, 20, DynamicKind.ALIAS_CHAIN, "create")]


def test_alias_cycle_is_an_alias_chain():
    aliases, _, dynamics = rooted(
        'import * as stripe from "stripe";\nconst a = b;\nconst b = a;\n'
    )

    assert aliases == {}
    assert dynamics == [Dynamic("m.ts", 3, 7, DynamicKind.ALIAS_CHAIN, "b")]


def test_unrooted_call_and_member_are_not_aliases():
    aliases, class_aliases, dynamics = rooted(
        "const a = other();\nconst b = other.thing;\n"
    )

    assert aliases == {}
    assert class_aliases == set()
    assert dynamics == []


# Phase 4: calls, object keys and attributes.
def test_basic_fixture_emits_the_exact_hit_tuples():
    result = scan_ts(SDK_BASIC, "stripe")

    assert result.hits == (
        hit(SDK_BASIC, "src/billing.ts", 3, 27, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(SDK_BASIC, "src/billing.ts", 5, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(SDK_BASIC, "src/billing.ts", 5, 25, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
        hit(SDK_BASIC, "src/billing.ts", 5, 38, SiteShape.KEYWORD, "currency", ("charges", "create"), True),
        hit(SDK_BASIC, "src/billing.ts", 6, 16, SiteShape.CALL, "delete", ("charges", "delete"), True),
        hit(SDK_BASIC, "src/reporting.ts", 3, 16, SiteShape.CALL, "list", ("charges", "list"), False),
        hit(SDK_BASIC, "src/reporting.ts", 3, 23, SiteShape.KEYWORD, "limit", (), False),
    )


def test_dict_key_is_reported_at_the_opening_quote(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        'const client = new Stripe();\n'
        'client.charges.create({ "amount": 1 });\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(tmp_path, "app.ts", 4, 25, SiteShape.DICT_KEY, "amount", ("charges", "create"), True),
    )


def test_shorthand_object_key_is_a_keyword(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "const amount = 1;\n"
        "client.charges.create({ amount });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    [keyword] = [item for item in result.hits if item.shape is SiteShape.KEYWORD]
    assert keyword == hit(
        tmp_path, "app.ts", 5, 25, SiteShape.KEYWORD, "amount", ("charges", "create"), True
    )


def test_attribute_is_rooted_only_for_a_class_receiver(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Stripe } from "stripe";\n'
        "\n"
        "const charge = new Stripe();\n"
        "charge.amount;\n"
        "Stripe.amount;\n"
        "response.amount;\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "amount", ("amount",), True),
        hit(tmp_path, "app.ts", 5, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True),
        hit(tmp_path, "app.ts", 6, 10, SiteShape.ATTRIBUTE, "amount", (), False),
    )


def test_objects_inside_a_direct_array_argument_are_walked(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        'client.charges.create([{ amount: 1 }, { "currency": "usd" }]);\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(tmp_path, "app.ts", 4, 26, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
        hit(tmp_path, "app.ts", 4, 41, SiteShape.DICT_KEY, "currency", ("charges", "create"), True),
    )


def test_an_unrooted_call_reports_unrooted_hits(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "api.record({ amount: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        hit(tmp_path, "app.ts", 3, 5, SiteShape.CALL, "record", ("record",), False),
        hit(tmp_path, "app.ts", 3, 14, SiteShape.KEYWORD, "amount", (), False),
    )


def test_a_bare_subpath_call_is_rooted(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { create } from "stripe/charges";\n'
        "\n"
        "create({ amount: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        hit(tmp_path, "app.ts", 3, 1, SiteShape.CALL, "create", ("charges", "create"), True),
        hit(tmp_path, "app.ts", 3, 10, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
    )


def test_calls_in_tsx_and_jsx_are_found():
    tsx = scan_ts(SDK_TSX, "stripe")
    jsx = scan_ts(SDK_JS, "stripe")

    assert [
        (item.symbol, item.shape, item.rooted) for item in tsx.hits
    ] == [
        ("Stripe", SiteShape.CALL, True),
        ("create", SiteShape.CALL, True),
        ("amount", SiteShape.KEYWORD, True),
    ]
    assert ("list", SiteShape.CALL, True) in [
        (item.symbol, item.shape, item.rooted) for item in jsx.hits
    ]
