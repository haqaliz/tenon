"""The ``tenon`` command: parse, configure, compose the stages, report."""

import argparse
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from tenon.detect import Change, DiffResult, SpecRefusal, diff, load
from tenon.locate import LocateConfig, locate
from tenon.pr import Remote

from .config import CliConfig, load_cli_config, overrides, resolve_config_path
from .report import (
    check_exit,
    render_check_json,
    render_check_text,
    render_error,
)

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


# Spec AC7: [locate]/[tenon] defaults, then every supplied flag overrides.
def _config(args: argparse.Namespace) -> CliConfig:
    repo = Path(args.repo)
    if not repo.is_dir():
        raise _Usage(f"repository is not a directory: {args.repo}")
    path = resolve_config_path(repo, args.config)
    if path is not None:
        config = load_cli_config(path)
    elif args.sdk_package is not None:
        config = CliConfig(locate=LocateConfig(sdk_package=args.sdk_package))
    else:
        raise _Usage(
            f"{repo / 'tenon.toml'} is missing and --sdk-package was not given"
        )
    return overrides(
        config,
        sdk_package=args.sdk_package,
        operations=args.operation,
        fields=args.field,
        command=getattr(args, "check", None),
        require=getattr(args, "require", None),
        breaking_only=args.breaking_only,
    )


def _diff_and_filter(
    old: str, new: str, config: CliConfig
) -> tuple[DiffResult, tuple[Change, ...]]:
    result = diff(load(old), load(new))
    if config.breaking_only:
        return result, tuple(change for change in result.changes if change.breaking)
    return result, tuple(result.changes)


def _check(args: argparse.Namespace, config: CliConfig) -> int:
    _result, changes = _diff_and_filter(args.old, args.new, config)
    located = tuple(
        locate(change, Path(args.repo), config.locate) for change in changes
    )
    text = render_check_json(located) if args.json else render_check_text(located)
    print(text, end="")
    return check_exit(located)


def _fail(
    kind: str,
    message: str,
    *,
    code: str | None = None,
    pointer: str | None = None,
    json_mode: bool,
) -> int:
    stream = sys.stdout if json_mode else sys.stderr
    print(
        render_error(
            kind, message, code=code, pointer=pointer, json_mode=json_mode
        ),
        end="",
        file=stream,
    )
    return 1 if kind == "internal" else 2


def main(argv: Sequence[str] | None = None, *, remote: Remote | None = None) -> int:
    """Return the process exit code; never call ``sys.exit``."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as status:
        return int(status.code or 0)

    json_mode = bool(args.json)
    try:
        config = _config(args)
        if args.command == "check":
            return _check(args, config)
        raise NotImplementedError("fix lands in the next phase")
    except SpecRefusal as refusal:
        return _fail(
            "spec",
            refusal.message,
            code=refusal.code.value,
            pointer=refusal.pointer,
            json_mode=json_mode,
        )
    except _Usage as error:
        return _fail("usage", str(error), json_mode=json_mode)
    except (ValueError, tomllib.TOMLDecodeError, FileNotFoundError, OSError) as error:
        return _fail("config", str(error), json_mode=json_mode)
    except Exception as error:  # noqa: BLE001 - the CLI never prints a traceback
        return _fail("internal", str(error), json_mode=json_mode)
