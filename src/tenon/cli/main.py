"""The ``tenon`` command: parse, configure, compose the stages, report."""

import argparse
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence

# Spec AC1: the installed package version, with a stable fallback for a source run.
FALLBACK_VERSION = "0.0.0"


class _Usage(Exception):
    """A parsed command whose arguments do not make a usable run."""


def _package_version() -> str:
    try:
        return version("tenonhq")
    except PackageNotFoundError:
        return FALLBACK_VERSION


def _require(value: str) -> str:
    """Only the two shipped proof levels; the rest of the ladder is T7."""
    if value not in ("TESTS_PASSED", "UNVERIFIED"):
        raise argparse.ArgumentTypeError(
            f"--require must be TESTS_PASSED or UNVERIFIED until T7: {value!r}"
        )
    return value


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="repository to analyze")
    parser.add_argument("--old", required=True, help="old OpenAPI document")
    parser.add_argument("--new", required=True, help="new OpenAPI document")
    parser.add_argument("--config", default=None, help="path to tenon.toml")
    parser.add_argument("--sdk-package", default=None, help="dotted SDK package")
    parser.add_argument(
        "--operation",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="map an HTTP operation to a Python call",
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="map a schema field to a Python name",
    )
    parser.add_argument(
        "--breaking-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="analyze only breaking changes",
    )
    parser.add_argument("--json", action="store_true", help="machine output")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tenon",
        description="Keep your code fitted to the APIs it depends on.",
    )
    parser.add_argument(
        "--version", action="version", version=f"tenon {_package_version()}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="report affected call sites")
    _common(check)

    fix = commands.add_parser("fix", help="propose and prove fixes")
    _common(fix)
    fix.add_argument("--check", dest="check", default=None, help="check command")
    fix.add_argument("--require", type=_require, default=None, help="proof level")
    fix.add_argument("--open-pr", action="store_true", help="open a pull request")
    fix.add_argument(
        "--allow-unverified",
        action="store_true",
        help="allow a draft PR without a passed check",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Return the process exit code; never call ``sys.exit``."""
    parser = _parser()
    try:
        parser.parse_args(argv)
    except SystemExit as status:
        return int(status.code or 0)
    return 0
