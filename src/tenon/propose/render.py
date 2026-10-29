"""Verify located spans, apply edits in memory, and render a unified diff."""

import difflib
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from tenon.detect import Change
from tenon.locate import LocateResult, Site, SiteShape

from .result import Edit, Proposal, ProposalReason, SkipReason, Skipped
from .rules import RuleProposer, has_rule


def _safety(path: str) -> None:
    """Reject a path that could escape the repository root."""
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
        raise ValueError(f"unsafe repository path: {path!r}")


def _line(root: str | Path, path: str, line: int) -> str:
    """One 1-based source line, with no line terminator."""
    text = (Path(root) / path).read_text(encoding="utf-8")
    return text.split("\n")[line - 1].removesuffix("\r")


def _identifier_char(char: str) -> bool:
    return bool(char) and (char.isalnum() or char == "_")


def _at_identifier(line: str, column: int, old: str) -> bool:
    """The span equals ``old`` and is the whole identifier, not a prefix."""
    start = column - 1
    end = start + len(old)
    if line[start:end] != old:
        return False
    before = line[start - 1] if start else ""
    after = line[end] if end < len(line) else ""
    return not _identifier_char(before) and not _identifier_char(after)


def verify(edit: Edit, root: str | Path) -> bool:
    """Whether the current source still holds this edit's exact old span.

    A missing file, a short line or a decode error is ``False``: assembly turns
    those into ``STALE_SITE``. An unsafe path is a caller error and raises.
    """
    _safety(edit.path)
    if edit.line < 1 or edit.column < 1 or not edit.old:
        return False
    try:
        line = _line(root, edit.path, edit.line)
    except (OSError, UnicodeDecodeError, IndexError):
        return False
    if edit.shape is SiteShape.DICT_KEY:
        start = edit.column - 1
        quote = line[start : start + 1]
        end = start + len(edit.old) + 2
        return (
            quote in ("'", '"')
            and line[start + 1 : end - 1] == edit.old
            and line[end - 1 : end] == quote
        )
    if edit.shape in (SiteShape.KEYWORD, SiteShape.ATTRIBUTE):
        return _at_identifier(line, edit.column, edit.old)
    return False


def apply_edits(text: str, edits: Sequence[Edit]) -> str:
    """Apply edits in descending ``(line, column)`` order to one file's text."""
    lines = text.split("\n")
    grouped: dict[int, list[Edit]] = {}
    for edit in edits:
        if edit.line < 1 or edit.column < 1:
            raise ValueError(f"edit outside the file: {edit!r}")
        grouped.setdefault(edit.line, []).append(edit)
    for line_number, line_edits in grouped.items():
        if line_number > len(lines):
            raise ValueError(f"edit beyond the last line: {line_number}")
        line = lines[line_number - 1]
        last_start: int | None = None
        for edit in sorted(line_edits, key=lambda item: item.column, reverse=True):
            start = edit.column - 1
            if edit.shape is SiteShape.DICT_KEY:
                quote = line[start : start + 1]
                if quote not in ("'", '"'):
                    raise ValueError(f"dict key without a quote: {edit!r}")
                end = start + len(edit.old) + 2
                replacement = quote + edit.new + quote
            else:
                end = start + len(edit.old)
                replacement = edit.new
            if last_start is not None and end > last_start:
                raise ValueError(f"overlapping edits on line {line_number}")
            line = line[:start] + replacement + line[end:]
            last_start = start
        lines[line_number - 1] = line
    return "\n".join(lines)


def render(files: Mapping[str, tuple[str, str]]) -> str:
    """Render ``path -> (old, new)`` as one ordered, newline-stable diff.

    An unchanged file emits nothing.

    shortcut: a file without a final newline keeps difflib's adjacent ``-``/``+``
    lines and no git no-newline markers, so that hunk will not git-apply; add
    the markers when such files must apply.
    """
    chunks: list[str] = []
    for path in sorted(files):
        old, new = files[path]
        if old == new:
            continue
        chunks.extend(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
                lineterm="\n",
            )
        )
    diff = "".join(chunks)
    if diff and not diff.endswith("\n"):
        diff += "\n"
    return diff


def _add_skipped(
    entries: dict[tuple[str, int, int, str], Skipped], entry: Skipped
) -> None:
    key = (entry.site.path, entry.site.line, entry.site.column, entry.reason.value)
    entries.setdefault(key, entry)


def propose(
    change: Change,
    located: LocateResult,
    root: str | Path,
    proposer=RuleProposer(),
) -> Proposal:
    """Assemble verified edits into a diff; never write to disk.

    The proposer is untrusted: a candidate is edited only if its exact span
    still verifies, and a site the locator called ambiguous is never edited.
    """
    candidates = tuple(proposer.propose(change, located, root))
    ambiguous = {
        (site.path, site.line, site.column)
        for group in located.ambiguous
        for site in group.candidates
    }
    uneditable = {
        (site.path, site.line, site.column)
        for site in located.certain
        if site.shape is SiteShape.CALL
    }
    certain = {
        (site.path, site.line, site.column): site for site in located.certain
    }
    skipped: dict[tuple[str, int, int, str], Skipped] = {}
    for group in located.ambiguous:
        reason = SkipReason(group.reason.value)
        for site in group.candidates:
            _add_skipped(skipped, Skipped(site, reason))
    for site in located.certain:
        if site.shape is SiteShape.CALL:
            _add_skipped(skipped, Skipped(site, SkipReason.SHAPE_NOT_EDITABLE))
    accepted: list[Edit] = []
    stale = 0
    for candidate in dict.fromkeys(candidates):
        key = (candidate.path, candidate.line, candidate.column)
        if key in ambiguous or key in uneditable:
            continue
        if verify(candidate, root):
            accepted.append(candidate)
            continue
        site = certain.get(key) or Site(
            path=candidate.path,
            line=candidate.line,
            column=candidate.column,
            shape=candidate.shape,
            symbol=candidate.old,
        )
        _add_skipped(skipped, Skipped(site, SkipReason.STALE_SITE))
        stale += 1
    texts: dict[str, tuple[str, str]] = {}
    for path in sorted({edit.path for edit in accepted}):
        old = (Path(root) / path).read_text(encoding="utf-8")
        texts[path] = (
            old,
            apply_edits(old, [edit for edit in accepted if edit.path == path]),
        )
    if accepted:
        reason = None
    elif not has_rule(change):
        reason = ProposalReason.NO_RULE
    elif not located.certain:
        reason = ProposalReason.NO_CERTAIN_SITES
    elif stale:
        reason = ProposalReason.STALE_SITE
    else:
        # A mechanical rule, certain sites, but nothing it can edit.
        reason = ProposalReason.NO_CERTAIN_SITES
    return Proposal(
        change=change,
        edits=tuple(accepted),
        skipped=tuple(skipped.values()),
        diff=render(texts),
        reason=reason,
    )
