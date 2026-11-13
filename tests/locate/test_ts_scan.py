"""The tree-sitter TS/JS scanner over committed fixture repositories."""

from pathlib import Path

from tenon.locate import SiteShape
from tenon.locate.scan import Dynamic, DynamicKind, Hit, _Source
from tenon.locate.ts_scan import (
    _Visitor,
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
SDK_ALIAS = FIXTURES / "ts-alias"
SDK_DECOY = FIXTURES / "ts-decoy"
SDK_DYNAMIC = FIXTURES / "ts-dynamic"
SDK_NO_SDK = FIXTURES / "ts-no-sdk"
SDK_UNICODE = FIXTURES / "ts-unicode"

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


def a_hit(repo, path, line, column, shape, symbol, chain=(), rooted=False):
    line_text = (repo / path).read_text(encoding="utf-8").split("\n")[line - 1]
    return Hit(path, line, column, shape, symbol, chain, rooted, line_text)


def a_dynamic(path, line, column, kind, symbol=None, chain=()):
    return Dynamic(path, line, column, kind, symbol, chain)


def parse_ts(text, suffix=".ts"):
    return _parser(_grammar(suffix)).parse(text.encode("utf-8"))


def bindings(text, sdk_package="stripe"):
    return _bindings(parse_ts(text), sdk_package)


def rooted(text, sdk_package="stripe"):
    tree = parse_ts(text)
    roots, classes = _bindings(tree, sdk_package)
    source = _Source("m.ts", tuple(text.split("\n")))
    return _aliases(tree, roots, classes, sdk_package, source)


def a_visitor(text, receivers=None, sdk_package="stripe"):
    tree = parse_ts(text)
    roots, classes = _bindings(tree, sdk_package)
    source = _Source("m.ts", tuple(text.split("\n")))
    alias_roots, class_aliases, _ = _aliases(
        tree, roots, classes, sdk_package, source
    )
    visitor = _Visitor(
        source,
        sdk_package,
        {**roots, **alias_roots},
        classes | class_aliases,
        receivers,
    )
    visitor.visit(tree.root_node)
    return visitor


# Phase 1: discovery, grammar selection and skipped files.
# Spec AC1: all eight extensions parse; ignored directories and broken files skip.
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
# Spec AC2/AC3: every import form roots; only SDK importers and their importers scan.
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
# Spec AC4: new/call/name/member/destructuring are one hop; a second hop is dynamic.
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
# Spec AC5: exact 1-based line, column, shape, symbol and chain for each shape.
def test_basic_fixture_emits_the_exact_hit_tuples():
    result = scan_ts(SDK_BASIC, "stripe")

    assert result.hits == (
        a_hit(SDK_BASIC, "src/billing.ts", 3, 27, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(SDK_BASIC, "src/billing.ts", 5, 8, SiteShape.ATTRIBUTE, "charges", ("Stripe", "charges"), True),
        a_hit(SDK_BASIC, "src/billing.ts", 5, 16, SiteShape.CALL, "create", ("Stripe", "charges", "create"), True),
        a_hit(SDK_BASIC, "src/billing.ts", 5, 25, SiteShape.KEYWORD, "amount", ("Stripe", "charges", "create"), True),
        a_hit(SDK_BASIC, "src/billing.ts", 5, 38, SiteShape.KEYWORD, "currency", ("Stripe", "charges", "create"), True),
        a_hit(SDK_BASIC, "src/billing.ts", 6, 8, SiteShape.ATTRIBUTE, "charges", ("Stripe", "charges"), True),
        a_hit(SDK_BASIC, "src/billing.ts", 6, 16, SiteShape.CALL, "delete", ("Stripe", "charges", "delete"), True),
        a_hit(SDK_BASIC, "src/reporting.ts", 3, 16, SiteShape.CALL, "list", ("charges", "list"), False),
        a_hit(SDK_BASIC, "src/reporting.ts", 3, 23, SiteShape.KEYWORD, "limit", (), False),
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
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Stripe", "charges"), True),
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("Stripe", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 25, SiteShape.DICT_KEY, "amount", ("Stripe", "charges", "create"), True),
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
    assert keyword == a_hit(
        tmp_path,
        "app.ts",
        5,
        25,
        SiteShape.KEYWORD,
        "amount",
        ("Stripe", "charges", "create"),
        True,
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
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True),
        a_hit(tmp_path, "app.ts", 5, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True),
        a_hit(tmp_path, "app.ts", 6, 10, SiteShape.ATTRIBUTE, "amount", (), False),
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
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Stripe", "charges"), True),
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("Stripe", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 26, SiteShape.KEYWORD, "amount", ("Stripe", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 41, SiteShape.DICT_KEY, "currency", ("Stripe", "charges", "create"), True),
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
        a_hit(tmp_path, "app.ts", 3, 5, SiteShape.CALL, "record", ("record",), False),
        a_hit(tmp_path, "app.ts", 3, 14, SiteShape.KEYWORD, "amount", (), False),
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
        a_hit(tmp_path, "app.ts", 3, 1, SiteShape.CALL, "create", ("charges", "create"), True),
        a_hit(tmp_path, "app.ts", 3, 10, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
    )


def test_calls_in_tsx_and_jsx_are_found():
    tsx = scan_ts(SDK_TSX, "stripe")
    jsx = scan_ts(SDK_JS, "stripe")

    assert [
        (item.symbol, item.shape, item.rooted) for item in tsx.hits
    ] == [
        ("Stripe", SiteShape.CALL, True),
        ("charges", SiteShape.ATTRIBUTE, True),
        ("create", SiteShape.CALL, True),
        ("amount", SiteShape.KEYWORD, True),
    ]
    assert ("list", SiteShape.CALL, True) in [
        (item.symbol, item.shape, item.rooted) for item in jsx.hits
    ]


# Phase 5: dynamics and the decoy.
# Spec AC6: spread, object variable, computed key/member, dynamic import and alias chains.
def test_object_spread_is_star_kwargs(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "const payload = { amount: 1 };\n"
        "client.charges.create({ ...payload });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 5, 25, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
    )


def test_object_variable_argument_is_star_kwargs(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "client.charges.create(payload);\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 4, 23, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
    )


def test_computed_object_key_is_star_kwargs(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "client.charges.create({ [key]: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 4, 25, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
    )
    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Stripe", "charges"), True),
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("Stripe", "charges", "create"), True),
    )


def test_spread_argument_is_star_args(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "client.charges.create(...rows);\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 4, 23, DynamicKind.STAR_ARGS, chain=("Stripe", "charges", "create")),
    )


def test_a_primitive_literal_argument_is_not_dynamic(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        'client.charges.retrieve("ch_1");\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == ()
    assert [(item.shape, item.symbol) for item in result.hits] == [
        (SiteShape.CALL, "Stripe"),
        (SiteShape.ATTRIBUTE, "charges"),
        (SiteShape.CALL, "retrieve"),
    ]


def test_computed_member_is_getattr(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "const value = client[key];\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 4, 15, DynamicKind.GETATTR, chain=("Stripe",)),
    )
    assert all(item.shape is not SiteShape.ATTRIBUTE for item in result.hits)


def test_computed_callee_chain_is_getattr_and_the_call_is_unrooted(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        'client["charges"].create({ amount: 1 });\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 4, 1, DynamicKind.GETATTR, "charges", ("Stripe",)),
    )
    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(tmp_path, "app.ts", 4, 19, SiteShape.CALL, "create", ("create",), False),
        a_hit(tmp_path, "app.ts", 4, 28, SiteShape.KEYWORD, "amount", (), False),
    )


def test_a_second_hop_alias_is_reported_by_the_scan(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = new Stripe();\n"
        "const c = client;\n"
        "const d = c;\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == (
        a_dynamic("app.ts", 5, 7, DynamicKind.ALIAS_CHAIN, "d"),
    )


def test_dynamic_import_roots_nothing(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        'const sdk = await import("stripe");\n'
        "sdk.charges.create({ amount: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.dynamics == ()
    assert [
        (item.shape, item.symbol, item.chain, item.rooted) for item in result.hits
    ] == [
        (SiteShape.CALL, "create", ("charges", "create"), False),
        (SiteShape.KEYWORD, "amount", (), False),
    ]


def test_ts_dynamic_fixture_reports_every_dynamic_kind():
    result = scan_ts(SDK_DYNAMIC, "stripe")

    assert result.dynamics == (
        a_dynamic("src/flows.ts", 6, 25, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
        a_dynamic("src/flows.ts", 7, 23, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
        a_dynamic("src/flows.ts", 8, 25, DynamicKind.STAR_KWARGS, chain=("Stripe", "charges", "create")),
        a_dynamic("src/flows.ts", 11, 15, DynamicKind.GETATTR, chain=("Stripe",)),
        a_dynamic("src/flows.ts", 12, 1, DynamicKind.GETATTR, chain=("Stripe",)),
        a_dynamic("src/flows.ts", 13, 1, DynamicKind.GETATTR, "charges", ("Stripe",)),
        a_dynamic("src/flows.ts", 16, 7, DynamicKind.ALIAS_CHAIN, "d"),
    )


def test_ts_dynamic_fixture_roots_only_the_static_call():
    result = scan_ts(SDK_DYNAMIC, "stripe")

    assert [
        (item.line, item.rooted) for item in result.hits if item.symbol == "amount"
    ] == [(9, True), (12, False), (13, False)]


def test_the_decoy_has_no_certain_evidence_and_no_unreachable_hits():
    result = scan_ts(SDK_DECOY, "stripe")

    assert result.modules == ("src/sdk.ts",)
    assert [
        (item.path, item.line, item.rooted)
        for item in result.hits
        if item.symbol == "amount"
    ] == [
        ("src/sdk.ts", 7, True),
        ("src/sdk.ts", 8, False),
    ]
    assert result.dynamics == ()


# Phase 6: determinism, no writes and UTF-8 columns.
# Spec AC7/AC8: a human character column and byte-stable, read-only scans.
def test_scan_ts_is_deterministic():
    first = scan_ts(SDK_BASIC, "stripe")
    second = scan_ts(SDK_BASIC, "stripe")

    assert first == second
    assert (first.modules, first.hits, first.dynamics) == (
        second.modules,
        second.hits,
        second.dynamics,
    )


def test_scan_ts_never_modifies_the_scanned_tree():
    def snapshot():
        return {
            path.relative_to(SDK_BASIC).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in SDK_BASIC.rglob("*")
            if path.is_file()
        }

    before = snapshot()

    scan_ts(SDK_BASIC, "stripe")

    assert snapshot() == before


def test_column_counts_characters_not_utf8_bytes():
    line = (SDK_UNICODE / "src/app.ts").read_text(encoding="utf-8").split("\n")[3]
    character_column = line.index("amount") + 1
    byte_column = line.encode("utf-8").index(b"amount") + 1

    result = scan_ts(SDK_UNICODE, "stripe")

    [keyword] = [item for item in result.hits if item.shape is SiteShape.KEYWORD]
    assert character_column != byte_column
    assert keyword == a_hit(
        SDK_UNICODE,
        "src/app.ts",
        4,
        character_column,
        SiteShape.KEYWORD,
        "amount",
        ("Stripe", "charges", "create"),
        True,
    )


def test_computed_destructuring_key_is_an_alias_chain():
    aliases, _, dynamics = rooted(
        'import * as stripe from "stripe";\n'
        "const { [key]: value } = stripe;\n"
    )

    assert aliases == {}
    assert dynamics == [a_dynamic("m.ts", 2, 16, DynamicKind.ALIAS_CHAIN, "value")]


def test_required_computed_destructuring_binds_nothing():
    assert bindings('const { [key]: value } = require("stripe");\n') == ({}, set())


def test_alias_fixture_has_the_exact_rooted_and_unrooted_evidence():
    result = scan_ts(SDK_ALIAS, "stripe")

    assert result.hits == (
        a_hit(SDK_ALIAS, "src/aliases.ts", 4, 20, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 6, 24, SiteShape.ATTRIBUTE, "charges", (), False),
        a_hit(SDK_ALIAS, "src/aliases.ts", 9, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 10, 8, SiteShape.ATTRIBUTE, "amount", ("Stripe", "amount"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 11, 9, SiteShape.CALL, "create", ("charges", "create"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 11, 18, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 12, 9, SiteShape.CALL, "retrieve", ("balance", "retrieve"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 13, 9, SiteShape.CALL, "create", ("charges", "create"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 13, 18, SiteShape.KEYWORD, "amount", ("charges", "create"), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 20, 16, SiteShape.CALL, "Stripe", ("Stripe",), True),
        a_hit(SDK_ALIAS, "src/aliases.ts", 22, 14, SiteShape.CALL, "create", ("charges", "create"), False),
        a_hit(SDK_ALIAS, "src/aliases.ts", 22, 23, SiteShape.KEYWORD, "amount", (), False),
    )
    assert result.dynamics == (
        a_dynamic("src/aliases.ts", 16, 7, DynamicKind.ALIAS_CHAIN, "d"),
        a_dynamic("src/aliases.ts", 18, 20, DynamicKind.ALIAS_CHAIN, "id"),
    )


# Phase 7: receiver evidence.
# Spec AC1: a rooted `new` expression binds its canonical type chain.
def test_a_new_expression_is_evidence():
    visitor = a_visitor(
        'import Stripe from "stripe";\n'
        'import { Client } from "stripe";\n'
        'const client = new Stripe("a");\n'
        'const other = new Client("b");\n'
    )

    assert visitor._bindings == {"client": ("Stripe",), "other": ("Client",)}


# Spec AC1: a qualified constructor resolves through the namespace root.
def test_a_qualified_new_expression_is_evidence():
    visitor = a_visitor(
        'import * as stripe from "stripe";\n'
        'const client = new stripe.Client("a");\n'
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: a constructor outside the SDK is not evidence.
def test_an_unrooted_new_expression_is_not_evidence():
    visitor = a_visitor(
        'import Stripe from "stripe";\nconst client = new Date();\n'
    )

    assert visitor._bindings == {}


# Spec AC1: an annotation binds, with or without a value.
def test_an_annotation_is_evidence():
    visitor = a_visitor(
        'import { Client, StripeClient } from "stripe";\n'
        "const client: Client = build();\n"
        'const other: StripeClient = new StripeClient("b");\n'
        "let bare: Client;\n"
    )

    assert visitor._bindings == {
        "client": ("Client",),
        "other": ("StripeClient",),
        "bare": ("Client",),
    }


# Spec AC1: an annotation resolves an imported type alias.
def test_a_renamed_annotation_is_evidence():
    visitor = a_visitor(
        'import { Client as C } from "stripe";\n'
        "const client: C = build();\n"
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: a qualified annotation resolves through the namespace root.
def test_a_qualified_annotation_is_evidence():
    visitor = a_visitor(
        'import * as stripe from "stripe";\n'
        "const client: stripe.Client = build();\n"
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: the annotation is the evidence when both sides name a type.
def test_an_annotation_wins_over_the_value():
    visitor = a_visitor(
        'import { Client, StripeClient } from "stripe";\n'
        "const client: Client = new StripeClient();\n"
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: a source-key factory binds the mapped type chain.
def test_a_source_factory_key_is_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "const client = StripeClient.create({});\n",
        receivers={"StripeClient.create": "Client"},
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: a canonical-key factory matches the SDK-rooted dotted chain.
def test_a_canonical_factory_key_is_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "const client = StripeClient.create({});\n",
        receivers={"stripe.StripeClient.create": "Resources.Client"},
    )

    assert visitor._bindings == {"client": ("Resources", "Client")}


# Spec AC1: a bare factory key matches its source spelling.
def test_a_bare_factory_key_is_evidence():
    visitor = a_visitor(
        'import { makeClient } from "stripe";\n'
        "const client = makeClient();\n",
        receivers={"makeClient": "Client"},
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: a canonical bare factory key matches the imported chain.
def test_a_canonical_bare_factory_key_is_evidence():
    visitor = a_visitor(
        'import { makeClient } from "stripe";\n'
        "const client = makeClient();\n",
        receivers={"stripe.makeClient": "Client"},
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC1: an unmapped factory is not evidence.
def test_an_unmapped_factory_is_not_evidence():
    visitor = a_visitor(
        'import Stripe from "stripe";\n'
        "const client = makeClient();\n"
        "const other = build();\n"
    )

    assert visitor._bindings == {}


# Spec AC1: a rebinding replaces the receiver type.
def test_a_rebinding_replaces_the_receiver():
    visitor = a_visitor(
        'import { Client, CustomerClient } from "stripe";\n'
        'let client = new Client("a");\n'
        'client = new CustomerClient("b");\n'
    )

    assert visitor._bindings == {"client": ("CustomerClient",)}


# Spec AC1: a rebinding without evidence clears the receiver.
def test_a_rebinding_without_evidence_clears_the_receiver():
    visitor = a_visitor(
        'import Stripe from "stripe";\n'
        'let client = new Stripe("a");\n'
        "client = build();\n"
    )

    assert visitor._bindings == {}


# Spec AC1: a function-local binding does not leak into the module.
def test_a_function_local_binding_does_not_leak():
    visitor = a_visitor(
        'import Stripe from "stripe";\n'
        "const client = new Stripe();\n"
        "function rebuild() {\n"
        '  const client = new Stripe("b");\n'
        "}\n"
    )

    assert visitor._bindings == {"client": ("Stripe",)}


# Phase 8: receiver chains.
# Spec AC2: a tracked call chain emits its full and intermediate chains, and
# its object keys carry the call chain.
def test_a_receiver_call_chain_is_rooted(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Client } from "stripe";\n'
        "\n"
        'const client = new Client("key");\n'
        'client.charges.create({ amount: 1, currency: "usd" });\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Client", ("Client",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Client", "charges"), True),
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("Client", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 25, SiteShape.KEYWORD, "amount", ("Client", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 36, SiteShape.KEYWORD, "currency", ("Client", "charges", "create"), True),
    )


# Spec AC2: a bare attribute on a tracked receiver emits the prefix.
def test_a_receiver_attribute_emits_the_prefix(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Client } from "stripe";\n'
        "\n"
        'const client = new Client("key");\n'
        "client.charges\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Client", ("Client",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Client", "charges"), True),
    )


# Spec AC2: a one-segment call has no intermediate attribute to emit.
def test_a_single_member_receiver_call_has_no_intermediate(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Client } from "stripe";\n'
        "\n"
        'const client = new Client("key");\n'
        "client.create({ amount: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Client", ("Client",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.CALL, "create", ("Client", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 17, SiteShape.KEYWORD, "amount", ("Client", "create"), True),
    )


# Spec AC1/AC2: a configured factory roots the receiver chain.
def test_a_configured_factory_roots_its_chain(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { makeClient } from "stripe";\n'
        "\n"
        "const client = makeClient();\n"
        'client.charges.create({ amount: 1 });\n',
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe", receivers={"makeClient": "Client"})

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 16, SiteShape.CALL, "makeClient", ("makeClient",), True),
        a_hit(tmp_path, "app.ts", 4, 8, SiteShape.ATTRIBUTE, "charges", ("Client", "charges"), True),
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("Client", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 4, 25, SiteShape.KEYWORD, "amount", ("Client", "charges", "create"), True),
    )


# Spec AC2: a chain on an untracked receiver keeps the unrooted behavior.
def test_an_untracked_receiver_chain_is_unchanged(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import Stripe from "stripe";\n'
        "\n"
        "const client = makeClient();\n"
        "client.charges.create({ amount: 1 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("charges", "create"), False),
        a_hit(tmp_path, "app.ts", 4, 25, SiteShape.KEYWORD, "amount", (), False),
    )


# Spec AC1/AC2: evidence is per function: a parameter shadows, a local rebind
# stays local, and the module receiver is restored afterwards.
def test_receiver_chains_respect_function_scopes(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Client } from "stripe";\n'
        "\n"
        'const client = new Client("a");\n'
        "\n"
        "function shadow(client) {\n"
        "  client.charges;\n"
        "}\n"
        "\n"
        "function rebuild() {\n"
        "  const client = makeClient();\n"
        "  client.charges;\n"
        "}\n"
        "\n"
        "client.charges;\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 3, 20, SiteShape.CALL, "Client", ("Client",), True),
        a_hit(tmp_path, "app.ts", 6, 10, SiteShape.ATTRIBUTE, "charges", (), False),
        a_hit(tmp_path, "app.ts", 11, 10, SiteShape.ATTRIBUTE, "charges", (), False),
        a_hit(tmp_path, "app.ts", 14, 8, SiteShape.ATTRIBUTE, "charges", ("Client", "charges"), True),
    )


# Phase 9: return-type inference.
# Spec AC2: a same-file function with an SDK return annotation is evidence.
def test_a_typed_helper_is_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "function makeClient(): StripeClient {\n"
        "  return new StripeClient();\n"
        "}\n"
        "const client = makeClient();\n"
    )

    assert visitor._bindings == {"client": ("StripeClient",)}


# Spec AC2: a method's SDK return annotation is in the same map.
def test_a_typed_method_is_evidence():
    visitor = a_visitor(
        'import { Client } from "stripe";\n'
        "class Factory {\n"
        "  makeClient(): Client {\n"
        "    return new Client();\n"
        "  }\n"
        "}\n"
        "const client = makeClient();\n"
    )

    assert visitor._bindings == {"client": ("Client",)}


# Spec AC2: an arrow function's SDK return annotation is evidence.
def test_a_typed_arrow_helper_is_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "const makeClient = (): StripeClient => new StripeClient();\n"
        "const client = makeClient();\n"
    )

    assert visitor._bindings == {"client": ("StripeClient",)}


# Spec AC2: a missing return annotation is not evidence.
def test_an_unannotated_helper_is_not_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "function makeClient() {\n"
        "  return new StripeClient();\n"
        "}\n"
        "const client = makeClient();\n"
    )

    assert visitor._bindings == {}


# Spec AC2: any, generic and non-SDK return types are not evidence.
def test_a_wrong_return_annotation_is_not_evidence():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "class Local {}\n"
        "function anyReturn(): any {\n"
        "  return new StripeClient();\n"
        "}\n"
        "function genericReturn(): Promise<StripeClient> {\n"
        "  return null;\n"
        "}\n"
        "function localReturn(): Local {\n"
        "  return new Local();\n"
        "}\n"
        "const a = anyReturn();\n"
        "const b = genericReturn();\n"
        "const c = localReturn();\n"
    )

    assert visitor._bindings == {}


# Spec AC2: a rebinding through another typed helper replaces the chain.
def test_a_typed_helper_rebinding_replaces_the_receiver():
    visitor = a_visitor(
        'import { Client, CustomerClient } from "stripe";\n'
        "function makeClient(): Client {\n"
        "  return new Client();\n"
        "}\n"
        "function makeCustomer(): CustomerClient {\n"
        "  return new CustomerClient();\n"
        "}\n"
        "let client = makeClient();\n"
        "client = makeCustomer();\n"
    )

    assert visitor._bindings == {"client": ("CustomerClient",)}


# Spec AC2: a rebinding without evidence clears the inferred receiver.
def test_a_typed_helper_rebinding_without_evidence_clears():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "function makeClient(): StripeClient {\n"
        "  return new StripeClient();\n"
        "}\n"
        "let client = makeClient();\n"
        "client = build();\n"
    )

    assert visitor._bindings == {}


# Spec AC2: the configured receivers mapping still overrides the annotation.
def test_a_configured_receiver_overrides_the_annotation():
    visitor = a_visitor(
        'import { StripeClient } from "stripe";\n'
        "function makeClient(): StripeClient {\n"
        "  return new StripeClient();\n"
        "}\n"
        "const client = makeClient();\n",
        receivers={"makeClient": "CustomerClient"},
    )

    assert visitor._bindings == {"client": ("CustomerClient",)}


# Spec AC2: a typed helper roots the receiver call chain end-to-end.
def test_a_typed_helper_roots_the_receiver_chain(tmp_path):
    (tmp_path / "app.ts").write_text(
        'import { Client, StripeClient } from "stripe";\n'
        "\n"
        "function makeClient(): StripeClient {\n"
        "  return new Client();\n"
        "}\n"
        "\n"
        "const client = makeClient();\n"
        "client.charges.create({ amount: 100 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 4, 14, SiteShape.CALL, "Client", ("Client",), True),
        a_hit(tmp_path, "app.ts", 8, 8, SiteShape.ATTRIBUTE, "charges", ("StripeClient", "charges"), True),
        a_hit(tmp_path, "app.ts", 8, 16, SiteShape.CALL, "create", ("StripeClient", "charges", "create"), True),
        a_hit(tmp_path, "app.ts", 8, 25, SiteShape.KEYWORD, "amount", ("StripeClient", "charges", "create"), True),
    )


# Spec AC2: a helper defined in another file is not evidence.
def test_a_cross_file_helper_is_not_evidence(tmp_path):
    (tmp_path / "helpers.ts").write_text(
        'import { Client, StripeClient } from "stripe";\n'
        "\n"
        "export function makeClient(): StripeClient {\n"
        "  return new Client();\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "app.ts").write_text(
        'import { makeClient } from "./helpers";\n'
        "\n"
        "const client = makeClient();\n"
        "client.charges.create({ amount: 100 });\n",
        encoding="utf-8",
    )

    result = scan_ts(tmp_path, "stripe")

    assert result.hits == (
        a_hit(tmp_path, "app.ts", 4, 16, SiteShape.CALL, "create", ("charges", "create"), False),
        a_hit(tmp_path, "app.ts", 4, 25, SiteShape.KEYWORD, "amount", (), False),
        a_hit(tmp_path, "helpers.ts", 4, 14, SiteShape.CALL, "Client", ("Client",), True),
    )
