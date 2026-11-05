"""The ``tenon`` command: parse, configure, compose the stages, report."""

import argparse
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from tenon.detect import Change, DiffResult, SpecRefusal, diff, load
from tenon.locate import LocateConfig, TsLocateConfig, locate, locate_ts
from tenon.pr import GitGhRemote, Remote, write_pr
from tenon.propose import propose
from tenon.prove import ProofPlan, proof_rank, prove_plan

from .config import (
    CliConfig,
    a_level,
    load_cli_config,
    overrides,
    resolve_config_path,
)
from .report import (
    FixResult,
    check_exit,
    fix_exit,
    render_check_json,
    render_check_text,
    render_error,
    render_fix_json,
    render_fix_text,
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
    """Any ladder level; the config coerces the kept string to a ProofLevel."""
    try:
        return a_level(value, "--require").value
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="repository to analyze")
    parser.add_argument("--old", required=True, help="old OpenAPI document")
    parser.add_argument("--new", required=True, help="new OpenAPI document")
    parser.add_argument("--config", default=None, help="path to tenon.toml")
    parser.add_argument(
        "--language",
        choices=("python", "ts"),
        default=None,
        help="repository language (default: from tenon.toml, else python)",
    )
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
    fix.add_argument("--build", default=None, help="build command")
    fix.add_argument(
        "--characterize", default=None, help="characterization command"
    )
    fix.add_argument("--replay", default=None, help="replay command")
    fix.add_argument("--require", type=_require, default=None, help="proof level")
    fix.add_argument("--open-pr", action="store_true", help="open a pull request")
    fix.add_argument(
        "--allow-below-required",
        "--allow-unverified",
        dest="allow_below_required",
        action="store_true",
        help="allow a draft PR below the required proof level",
    )
    return parser


# Spec AC7: [locate]/[tenon] defaults, then every supplied flag overrides.
def _config(args: argparse.Namespace) -> CliConfig:
    repo = Path(args.repo)
    if not repo.is_dir():
        raise _Usage(f"repository is not a directory: {args.repo}")
    path = resolve_config_path(repo, args.config)
    if path is not None:
        config = load_cli_config(path, args.language)
    elif args.sdk_package is not None:
        language = args.language or "python"
        locate_type = TsLocateConfig if language == "ts" else LocateConfig
        config = CliConfig(
            locate=locate_type(sdk_package=args.sdk_package),
            language=language,
        )
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
        build=getattr(args, "build", None),
        characterize=getattr(args, "characterize", None),
        replay=getattr(args, "replay", None),
        require=getattr(args, "require", None),
        breaking_only=args.breaking_only,
        language=args.language,
    )


def _diff_and_filter(
    old: str, new: str, config: CliConfig
) -> tuple[DiffResult, tuple[Change, ...]]:
    result = diff(load(old), load(new))
    if config.breaking_only:
        return result, tuple(change for change in result.changes if change.breaking)
    return result, tuple(result.changes)


def _locate(change: Change, repo: Path, config: CliConfig):
    """The one dispatch point between the Python and TypeScript locators."""
    locate_change = locate_ts if config.language == "ts" else locate
    return locate_change(change, repo, config.locate)


def _check(args: argparse.Namespace, config: CliConfig) -> int:
    _result, changes = _diff_and_filter(args.old, args.new, config)
    located = tuple(
        _locate(change, Path(args.repo), config) for change in changes
    )
    text = render_check_json(located) if args.json else render_check_text(located)
    print(text, end="")
    return check_exit(located)


# Spec AC4/AC5: locate, propose and prove each change; never write the checkout.
def _fix(
    args: argparse.Namespace, config: CliConfig, remote: Remote | None
) -> int:
    result, changes = _diff_and_filter(args.old, args.new, config)
    repo = Path(args.repo)
    plan = ProofPlan(
        tests=config.command,
        characterize=config.characterize,
        replay=config.replay,
        build=config.build,
    )
    results: list[FixResult] = []
    for change in changes:
        located = _locate(change, repo, config)
        proposal = propose(change, located, repo)
        proof = prove_plan(proposal, repo, plan)
        pr = None
        if args.open_pr:
            below = proof_rank(proof.level) < proof_rank(config.require)
            if not below or args.allow_below_required:
                pr = write_pr(
                    proposal,
                    proof,
                    repo,
                    remote=remote or GitGhRemote(),
                    required=config.require,
                    allow_below_required=args.allow_below_required,
                    unanalyzed=result.unanalyzed,
                )
        results.append(
            FixResult(
                change=change,
                locate=located,
                proposal=proposal,
                proof=proof,
                pr=pr,
            )
        )
    text = render_fix_json(results) if args.json else render_fix_text(results)
    print(text, end="")
    return fix_exit(len(changes), results, config.require)


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
        return _fix(args, config, remote)
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
