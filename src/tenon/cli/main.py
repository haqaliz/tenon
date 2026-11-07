"""The ``tenon`` command: parse, configure, compose the stages, report."""

import argparse
import json
import os
import shlex
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

from tenon.corpus import (
    CorpusError,
    CorpusRecord,
    Outcome,
    append_records,
    benchmark,
    load_corpus,
    record_id,
    update_outcome,
)
from tenon.detect import (
    Change,
    DiffResult,
    SpecRefusal,
    diff,
    diff_mcp,
    load,
    load_mcp,
)
from tenon.locate import (
    LocateConfig,
    McpLocateConfig,
    TsLocateConfig,
    locate,
    locate_mcp,
    locate_ts,
)
from tenon.pr import (
    GitGhRemote,
    GitHubAppRemote,
    GitHubAppToken,
    Remote,
    write_pr,
)
from tenon.probe import AgentError, ProbeError, load_tasks, probe
from tenon.propose import propose
from tenon.prove import ProofPlan, proof_rank, prove_plan, tail
from tenon.provider import MigrationBundle, load_bundle

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
    render_provider_json,
    render_provider_text,
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
    parser.add_argument("--old", required=True, help="old API document")
    parser.add_argument("--new", required=True, help="new API document")
    parser.add_argument("--config", default=None, help="path to tenon.toml")
    parser.add_argument(
        "--language",
        choices=("python", "ts"),
        default=None,
        help="repository language (default: from tenon.toml, else python)",
    )
    parser.add_argument(
        "--source",
        choices=("openapi", "mcp"),
        default=None,
        help="input documents (default: from tenon.toml, else openapi)",
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
        "--remote",
        choices=("gh", "app"),
        default=None,
        help="GitHub remote (default: gh)",
    )
    fix.add_argument("--app-id", default=None, help="GitHub App id")
    fix.add_argument(
        "--app-installation-id", default=None, help="GitHub App installation id"
    )
    fix.add_argument(
        "--app-private-key",
        default=None,
        metavar="PATH",
        help="GitHub App private key PEM path",
    )
    fix.add_argument("--api-url", default=None, help="GitHub API base URL")
    fix.add_argument(
        "--allow-below-required",
        "--allow-unverified",
        dest="allow_below_required",
        action="store_true",
        help="allow a draft PR below the required proof level",
    )

    # Spec AC1/AC2: one provider bundle runs against one repository.
    provider = commands.add_parser(
        "provider", help="run a provider migration bundle"
    )
    provider_commands = provider.add_subparsers(
        dest="provider_command", required=True
    )
    migrate = provider_commands.add_parser(
        "migrate", help="migrate one repository"
    )
    migrate.add_argument("repo", help="repository to migrate")
    migrate.add_argument("--bundle", required=True, help="migration bundle JSON")
    migrate.add_argument("--check", dest="check", default=None, help="check command")
    migrate.add_argument("--require", default=None, help="proof level")
    migrate.add_argument("--json", action="store_true", help="machine output")

    # Spec AC1: the third subcommand, with no repo/--old/--new.
    probe_command = commands.add_parser("probe", help="probe an MCP server with an agent")
    probe_command.add_argument(
        "--server-cmd", required=True, help="MCP server command, shlex-split"
    )
    probe_command.add_argument("--tasks", required=True, help="probe tasks JSON file")
    probe_command.add_argument(
        "--agent", required=True, help="agent command, shlex-split"
    )
    probe_command.add_argument(
        "--timeout", type=float, default=30, help="seconds per request (default: 30)"
    )
    probe_command.add_argument("--json", action="store_true", help="machine output")

    # Spec AC1: the corpus subcommand takes a file, not a repo/spec pair.
    corpus = commands.add_parser("corpus", help="record and report benchmark runs")
    corpus_commands = corpus.add_subparsers(
        dest="corpus_command", required=True
    )
    corpus_record = corpus_commands.add_parser("record", help="record a fix run")
    corpus_record.add_argument(
        "--from",
        dest="fix_json",
        required=True,
        metavar="FIX_JSON",
        help="a tenon fix --json file",
    )
    corpus_record.add_argument("--repo", required=True, help="repository URL")
    corpus_record.add_argument("--commit", required=True, help="pinned commit SHA")
    corpus_record.add_argument(
        "--outcome",
        required=True,
        help="pending, merged, rejected, closed, incident, local_only",
    )
    corpus_record.add_argument(
        "--date", required=True, help="recorded date, YYYY-MM-DD"
    )
    corpus_record.add_argument("--corpus", required=True, help="corpus JSONL path")
    corpus_record.add_argument("--outcome-url", default=None, help="PR/issue URL")
    corpus_record.add_argument("--notes", default="", help="human context")
    corpus_record.add_argument("--evidence", default="", help="evidence path or URL")
    corpus_record.add_argument("--json", action="store_true", help="machine output")

    corpus_outcome = corpus_commands.add_parser(
        "outcome", help="update one record's outcome"
    )
    corpus_outcome.add_argument("--corpus", required=True, help="corpus JSONL path")
    corpus_outcome.add_argument("--id", required=True, help="record id")
    corpus_outcome.add_argument(
        "--outcome",
        required=True,
        help="pending, merged, rejected, closed, incident, local_only",
    )
    corpus_outcome.add_argument("--outcome-url", default=None, help="PR/issue URL")
    corpus_outcome.add_argument("--notes", default=None, help="human context")
    corpus_outcome.add_argument("--json", action="store_true", help="machine output")

    corpus_report = corpus_commands.add_parser(
        "report", help="aggregate the corpus by proof level and outcome"
    )
    corpus_report.add_argument("--corpus", required=True, help="corpus JSONL path")
    corpus_report.add_argument("--json", action="store_true", help="machine output")
    return parser


# Spec AC7: [locate]/[tenon] defaults, then every supplied flag overrides.
def _config(args: argparse.Namespace) -> CliConfig:
    repo = Path(args.repo)
    if not repo.is_dir():
        raise _Usage(f"repository is not a directory: {args.repo}")
    path = resolve_config_path(repo, args.config)
    if path is not None:
        config = load_cli_config(path, args.language, args.source)
    elif args.source == "mcp" or args.sdk_package is not None:
        if args.source == "mcp":
            # Spec AC5: a missing config still has the default MCP package.
            config = CliConfig(locate=McpLocateConfig(), source="mcp")
        else:
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
        source=args.source,
    )


def _diff_and_filter(
    old: str, new: str, config: CliConfig
) -> tuple[DiffResult, tuple[Change, ...]]:
    # Spec AC3: the source chooses the loader and differ, nothing downstream.
    result = (
        diff_mcp(load_mcp(old), load_mcp(new))
        if config.source == "mcp"
        else diff(load(old), load(new))
    )
    if config.breaking_only:
        return result, tuple(change for change in result.changes if change.breaking)
    return result, tuple(result.changes)


def _locate(change: Change, repo: Path, config: CliConfig):
    """The one dispatch point between the MCP, Python and TypeScript locators."""
    if config.source == "mcp":
        return locate_mcp(change, repo, config.locate)
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


# Spec AC1/AC2/AC3: the gh default, or the app remote from flags/env.
def _remote(args: argparse.Namespace) -> Remote:
    if args.remote != "app":
        return GitGhRemote()
    app_id = args.app_id or os.environ.get("TENON_GITHUB_APP_ID")
    installation_id = args.app_installation_id or os.environ.get(
        "TENON_GITHUB_APP_INSTALLATION_ID"
    )
    key_path = args.app_private_key or os.environ.get(
        "TENON_GITHUB_APP_PRIVATE_KEY"
    )
    api_url = (
        args.api_url
        or os.environ.get("TENON_GITHUB_API_URL")
        or "https://api.github.com"
    )
    if not app_id:
        raise _Usage(
            "--app-id or TENON_GITHUB_APP_ID is required for --remote app"
        )
    if not installation_id:
        raise _Usage(
            "--app-installation-id or TENON_GITHUB_APP_INSTALLATION_ID "
            "is required for --remote app"
        )
    if not key_path:
        raise _Usage(
            "--app-private-key or TENON_GITHUB_APP_PRIVATE_KEY "
            "is required for --remote app"
        )
    try:
        pem = Path(key_path).read_text(encoding="utf-8")
    except OSError as error:
        raise _Usage(
            f"cannot read the app private key {key_path}: {error}"
        ) from None
    # The token and the REST client share the stdlib default transport.
    return GitHubAppRemote(
        GitHubAppToken(
            app_id,
            installation_id,
            pem,
            api_url=api_url,
        ),
        api_url=api_url,
    )


# Spec AC4/AC5: locate, propose and prove each change; never write the checkout.
def _fix_results(
    repo: Path,
    old: str,
    new: str,
    config: CliConfig,
    remote: Remote | None,
    *,
    open_pr: bool,
    allow_below: bool,
) -> tuple[tuple[Change, ...], list[FixResult]]:
    """The shared fix pipeline: detect, locate, propose, prove, optional PR."""
    result, changes = _diff_and_filter(old, new, config)
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
        if open_pr:
            below = proof_rank(proof.level) < proof_rank(config.require)
            if not below or allow_below:
                pr = write_pr(
                    proposal,
                    proof,
                    repo,
                    remote=remote,
                    required=config.require,
                    allow_below_required=allow_below,
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
    return changes, results


def _fix(
    args: argparse.Namespace, config: CliConfig, remote: Remote | None
) -> int:
    target = remote
    if args.open_pr and target is None:
        target = _remote(args)
    changes, results = _fix_results(
        Path(args.repo),
        args.old,
        args.new,
        config,
        target,
        open_pr=args.open_pr,
        allow_below=args.allow_below_required,
    )
    text = render_fix_json(results) if args.json else render_fix_text(results)
    print(text, end="")
    return fix_exit(len(changes), results, config.require)


# Spec AC2: the bundle is a serialized provider-side CliConfig.
def _bundle_config(bundle: MigrationBundle, args: argparse.Namespace) -> CliConfig:
    config = CliConfig(
        locate=bundle.locate,
        command=bundle.command,
        build=bundle.build,
        characterize=bundle.characterize,
        replay=bundle.replay,
        require=bundle.require,
        breaking_only=bundle.breaking_only,
        language=bundle.language,
        source=bundle.source,
    )
    return overrides(config, command=args.check, require=args.require)


# Spec AC1/AC2: one bundle, one repo, the shipped fix pipeline.
def _provider(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    if not repo.is_dir():
        raise _Usage(f"repository is not a directory: {args.repo}")
    bundle = load_bundle(args.bundle)
    config = _bundle_config(bundle, args)
    changes, results = _fix_results(
        repo,
        str(bundle.old),
        str(bundle.new),
        config,
        None,
        open_pr=False,
        allow_below=False,
    )
    text = (
        render_provider_json(
            bundle.provider, bundle.migration, args.repo, results
        )
        if args.json
        else render_provider_text(bundle.provider, bundle.migration, results)
    )
    print(text, end="")
    return fix_exit(len(changes), results, config.require)


# Spec AC4: a setup failure is one named probe error, never a traceback.
def _probe_fail(reason: str, detail: str, *, json_mode: bool) -> int:
    message = tail(detail)
    if json_mode:
        print(
            json.dumps(
                {"error": {"kind": "probe", "reason": reason, "message": message}},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    else:
        print(f"tenon: probe: {reason}: {message}", file=sys.stderr)
    return 2


# Spec AC1/AC2: split the commands, load the tasks, probe, then render.
def _probe(args: argparse.Namespace) -> int:
    json_mode = bool(args.json)
    if not args.timeout > 0:
        return _probe_fail(
            "invalid_timeout",
            f"--timeout must be positive: {args.timeout}",
            json_mode=json_mode,
        )
    try:
        server_cmd = shlex.split(args.server_cmd)
        agent_cmd = shlex.split(args.agent)
    except ValueError as error:
        return _probe_fail("invalid_command", str(error), json_mode=json_mode)
    try:
        tasks = load_tasks(args.tasks)
    except (OSError, ValueError) as error:
        return _probe_fail("invalid_tasks", str(error), json_mode=json_mode)
    try:
        report = probe(server_cmd, tasks, agent_cmd, args.timeout)
    except (ProbeError, AgentError) as error:
        return _probe_fail(error.reason, error.detail, json_mode=json_mode)
    # Spec AC2/AC3: a task failure is a report with exit 1, never an error envelope.
    if args.json:
        print(report.to_json())
    else:
        print(report.render_text(), end="")
    return 0 if report.summary.failed == 0 else 1


# Spec AC2: the lowercase user token is the CLI spelling of the uppercase enum.
def _outcome(value: str) -> Outcome:
    try:
        return Outcome(value.upper())
    except (AttributeError, ValueError):
        raise ValueError(f"unknown outcome: {value}") from None


# Spec AC1: read the shipped fix envelope; anything else is one named error.
def _load_fix_json(path: str) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise CorpusError(f"cannot read fix JSON {path}: {error}") from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CorpusError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise CorpusError(f"{path}: fix JSON must be a JSON object")
    if payload.get("command") != "fix":
        raise CorpusError(f'{path}: not a tenon fix report (command != "fix")')
    if not isinstance(payload.get("results"), list):
        raise CorpusError(f"{path}: fix JSON must have a results list")
    return payload


# Spec AC1/AC2: one record per result; the shared flags are carried verbatim.
def _record_from_fix(
    result: object, index: int, args: argparse.Namespace, outcome: Outcome
) -> CorpusRecord:
    if not isinstance(result, dict):
        raise CorpusError(f"fix JSON result {index} must be an object")
    for key in ("change", "proposal", "proof"):
        if not isinstance(result.get(key), dict):
            raise CorpusError(f"fix JSON result {index}: {key} must be a mapping")
    pr = result.get("pr")
    if pr is not None and not isinstance(pr, dict):
        raise CorpusError(
            f"fix JSON result {index}: pr must be a mapping or null"
        )
    change = result["change"]
    proposal = result["proposal"]
    return CorpusRecord(
        id=record_id(args.repo, args.commit, change, proposal),
        repo=args.repo,
        commit=args.commit,
        change=change,
        proposal=proposal,
        proof=result["proof"],
        pr=pr,
        outcome=outcome,
        recorded=args.date,
        outcome_url=args.outcome_url,
        notes=args.notes,
        evidence=args.evidence,
    )


# Spec AC1: build every record before appending, so a bad result appends nothing.
def _corpus_record(args: argparse.Namespace) -> int:
    payload = _load_fix_json(args.fix_json)
    outcome = _outcome(args.outcome)
    records = tuple(
        _record_from_fix(result, index, args, outcome)
        for index, result in enumerate(payload["results"], start=1)
    )
    append_records(args.corpus, records)
    ids = [record.id for record in records]
    if args.json:
        print(
            json.dumps(
                {"ids": ids},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    elif ids:
        print("\n".join(ids))
    return 0


# Spec AC3: the human updates one id; the record keeps its identity.
def _corpus_outcome(args: argparse.Namespace) -> int:
    record = update_outcome(
        args.corpus,
        args.id,
        _outcome(args.outcome),
        outcome_url=args.outcome_url,
        notes=args.notes,
    )
    if args.json:
        print(record.to_json())
    else:
        print(f"updated {record.id}: {record.outcome.value}")
    return 0


# Spec AC4: the report is exactly the benchmark over the loaded history.
def _corpus_report(args: argparse.Namespace) -> int:
    report = benchmark(load_corpus(args.corpus))
    if args.json:
        print(report.to_json())
    else:
        print(report.render_text(), end="")
    return 0


# Spec AC2/AC7: every corpus failure is exit 2 with one named message.
def _corpus(args: argparse.Namespace) -> int:
    json_mode = bool(args.json)
    handlers = {
        "record": _corpus_record,
        "outcome": _corpus_outcome,
        "report": _corpus_report,
    }
    try:
        return handlers[args.corpus_command](args)
    except (CorpusError, ValueError, OSError) as error:
        return _fail("corpus", str(error), json_mode=json_mode)


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
    # Spec AC4: an explicit remote is meaningless without --open-pr.
    if args.command == "fix" and args.remote is not None and not args.open_pr:
        return _fail("usage", "--remote requires --open-pr", json_mode=json_mode)
    try:
        # Spec AC1: corpus and probe are dispatched before _config, which needs a repo.
        if args.command == "corpus":
            return _corpus(args)
        if args.command == "probe":
            return _probe(args)
        if args.command == "provider":
            return _provider(args)
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
