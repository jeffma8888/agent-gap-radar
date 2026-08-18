"""Oracle for the CLI surface that `docs/CONSUMER_CONTRACT.md` publishes.

WHY THIS EXISTS
The contract's `## The stable surface` table is the list a build loop or a CI job is
told it may rely on, and until iteration 10 every cell of it was hand-copied from the
CLI. Five of its seven rows named LESS than the parser accepts: `report` omitted
`--floor`, `prd` omitted `--project`, `scan` omitted `--json` -- the exact object the
same document points a release gate at, named only in prose under a different heading
43 lines further down -- and `list` and `show` omitted their register-path positional.
That last one is the expensive shape rather than a cosmetic one: the positional is
`nargs="?", default="."`, so a consumer copying the documented invocation gets exit 0
over whatever register happens to sit in its own working directory. A silent wrong
answer, not an error.

WHY THE EXPECTATION IS BOTH-DIRECTIONAL
The live drift was one-directional OMISSION. A containment check -- "every documented
flag exists" -- therefore passes the table exactly as it stood and proves nothing, so
every comparison here is SET EQUALITY: an omitted flag and an invented flag both fail.

WHY THE EXPECTATION IS INTROSPECTED, NOT LISTED
A hand-written list of verbs, flags and arities in a test is the same artifact as the
hand-copied table, one directory over: it drifts the same way and it would have to be
edited by the same person who forgot the document. Reading `build_parser()` makes the
document's claim decidable from the implementation that has to honour it.

WHY ONLY A ROW'S FIRST CELL IS READ
The Promise cell names flags in prose -- the `scan` row's promise discusses `--prd` --
so scanning a whole row lets documentation ABOUT a flag satisfy an assertion about the
INVOCATION a consumer copies. That is fail-open in the one direction that matters, and
it is why `surface_table_cells()` returns cell 0 of each row and nothing else.

WHY ARGPARSE INTERNALS
argparse publishes no API for enumerating a parser's subcommands, or one subparser's
options and arity, so `_actions`, `_SubParsersAction`, `option_strings` and `nargs` are
the only way to ask the question. Every use here is read-only. `parser_surface()` FAILS
CLOSED when no subparsers action is found: an empty surface would turn every comparison
below into two empty sets agreeing with each other, which is the green that means
nothing.
"""

from __future__ import annotations

import argparse
import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent_gap_radar.cli import build_parser

#: The one heading whose table this module treats as the published surface.
STABLE_SURFACE_HEADING = "## The stable surface"

#: The tracked document that carries the published surface. Resolved from THIS file
#: rather than from the process cwd, so the oracle reads the repo's own document under
#: `pytest -n auto` no matter which directory a worker starts in.
CONTRACT_PATH = (pathlib.Path(__file__).resolve().parent.parent
                 / "docs" / "CONSUMER_CONTRACT.md")

#: A GFM alignment row: pipes, dashes, colons and whitespace only.
_SEPARATOR_ROW = re.compile(r"\|[\s:|-]+\|")

#: Options every argparse parser adds for itself; not part of the published surface.
_IMPLICIT_OPTIONS = frozenset({"-h", "--help"})


class SurfaceContractError(Exception):
    """The stable-surface table could not be READ at all.

    Distinct from a violation on purpose. A violation is a difference between two
    surfaces that were both understood; this is a document whose shape defeats the
    parse -- a missing heading, a duplicated heading, a ragged row, a table with no
    data. Raising rather than returning an empty list keeps an unreadable document
    from being indistinguishable from a document with no differences.
    """


@dataclass(frozen=True)
class VerbSurface:
    """What one subparser actually accepts, as read from the parser."""

    options: frozenset[str]
    positionals: int
    #: option string -> does argparse consume a following token as its value. Needed
    #: because the documented tokenizer cannot otherwise tell `[--floor N]` (two
    #: tokens, one option) from `[--json] [--prd]` (two tokens, two options).
    takes_value: Mapping[str, bool]


@dataclass(frozen=True)
class DocumentedInvocation:
    """What one table cell CLAIMS a verb accepts."""

    verb: str
    options: frozenset[str]
    positionals: int


def contract_text() -> str:
    """The tracked contract document, decoded.

    A separate function so a caller can mutate the returned string in memory to build
    a known-bad, instead of editing the file on disk and having to put it back.
    """
    return CONTRACT_PATH.read_text(encoding="utf-8")


def parser_surface(
    parser: argparse.ArgumentParser | None = None,
) -> dict[str, VerbSurface]:
    """Every verb `build_parser()` registers, and what that verb accepts.

    `parser` is injectable so the fail-closed path can be exercised with a parser that
    has no subcommands; production callers pass nothing and get the real CLI.
    """
    parser = parser if parser is not None else build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {verb: _verb_surface(subparser)
                    for verb, subparser in action.choices.items()}
    raise SurfaceContractError(
        "parser registers no subcommands, so there is no surface to compare "
        "against; refusing to report agreement between two empty sets")


def _verb_surface(subparser: argparse.ArgumentParser) -> VerbSurface:
    """One subparser's option strings, positional count and value-taking map."""
    options: set[str] = set()
    takes_value: dict[str, bool] = {}
    positionals = 0
    for action in subparser._actions:
        if not action.option_strings:
            positionals += 1
            continue
        if set(action.option_strings) & _IMPLICIT_OPTIONS:
            continue
        options.update(action.option_strings)
        # `nargs == 0` is how argparse spells a flag that consumes nothing
        # (`store_true`); anything else -- including the default `None` -- consumes at
        # least one token.
        for option_string in action.option_strings:
            takes_value[option_string] = action.nargs != 0
    return VerbSurface(frozenset(options), positionals, takes_value)


def _cells(row: str) -> list[str]:
    """The pipe-delimited cells of one GFM row, outer pipes discarded."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|")


def _table_lines(document: str) -> list[str]:
    """Header, separator and data rows of the table under the stable-surface heading.

    The heading must occur EXACTLY ONCE. A detector keyed on a heading string cannot
    otherwise see document-level duplication: a second `## The stable surface` section
    would leave one whole table unexamined while every assertion downstream passed.
    """
    lines = document.splitlines()
    at = [i for i, line in enumerate(lines)
          if line.strip() == STABLE_SURFACE_HEADING]
    if len(at) != 1:
        raise SurfaceContractError(
            f"heading {STABLE_SURFACE_HEADING!r} occurs {len(at)} time(s) in the "
            f"document, expected exactly 1")

    cursor = at[0] + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines) or not _is_table_row(lines[cursor]):
        raise SurfaceContractError(
            f"no table follows heading {STABLE_SURFACE_HEADING!r}")

    table: list[str] = []
    while cursor < len(lines) and _is_table_row(lines[cursor]):
        table.append(lines[cursor])
        cursor += 1
    if len(table) < 3 or not _SEPARATOR_ROW.fullmatch(table[1].strip()):
        raise SurfaceContractError(
            f"table under {STABLE_SURFACE_HEADING!r} is not a header row, a "
            f"'|---|' separator and at least one data row")
    return table


def surface_table_cells(document: str) -> list[str]:
    """The FIRST cell of every data row of the stable-surface table, in order.

    Only cell 0 is returned, and that is the whole point -- see the module docstring on
    why reading the Promise cell would let prose satisfy an assertion about the
    invocation. Every data row is required to have the header's width, so a stray pipe
    inside a Promise cell fails loudly here instead of silently shifting which text is
    read as the invocation.
    """
    header, _separator, *data = _table_lines(document)
    width = len(_cells(header))
    cells = []
    for row in data:
        row_cells = _cells(row)
        if len(row_cells) != width:
            raise SurfaceContractError(
                f"table row {row.strip()!r} has {len(row_cells)} cell(s), but the "
                f"header row has {width}")
        cells.append(row_cells[0])
    return cells


def invocation_verb(cell: str) -> str:
    """The verb a first cell documents, read from its first two tokens.

    Split out because the tokenizer below needs that verb's parser metadata to know
    which tokens are option VALUES, and the metadata is per-verb: the cell has to be
    read far enough to learn the verb before the table it is tokenized against exists.
    """
    tokens = _tokens(cell)
    if len(tokens) < 2 or tokens[0] != "radar":
        raise SurfaceContractError(
            f"table cell {cell!r} is not a `radar <verb> ...` invocation")
    return tokens[1]


def _tokens(cell: str) -> list[str]:
    """Whitespace-split tokens of a backticked invocation, backticks removed."""
    return [token.strip("`") for token in cell.strip().strip("`").split()]


def documented_invocation(
    cell: str, takes_value: Mapping[str, bool]
) -> DocumentedInvocation:
    """Parse one first cell into the surface it claims.

    `takes_value` comes FROM THE PARSER, never from the shape of the documented token:
    that is what makes `[--floor N]` one option and `[--json] [--prd]` two, without
    this module holding a second opinion about which flags carry values. An unknown
    verb is tokenized with an empty map -- its option/arity numbers are then not
    meaningful, and the caller reports it as a verb-set difference instead.
    """
    tokens = _tokens(cell)
    verb = invocation_verb(cell)
    options: set[str] = set()
    positionals = 0
    expecting_value = False
    for raw in tokens[2:]:
        token = raw.strip("[]")
        if not token:
            continue
        if token.startswith("-"):
            options.add(token)
            expecting_value = takes_value.get(token, False)
            continue
        if expecting_value:
            expecting_value = False  # the value of the option just seen
            continue
        positionals += 1
    return DocumentedInvocation(verb, frozenset(options), positionals)


def surface_violations(
    document: str, parser: argparse.ArgumentParser | None = None
) -> list[str]:
    """Every difference between the documented surface and the parser's.

    Returns one message per difference, each naming the offending verb (or the
    unreadable document) and the exact difference. An empty list means the document
    and `build_parser()` agree on the verb set, on each verb's option set in BOTH
    directions, and on each verb's positional arity.
    """
    try:
        cells = surface_table_cells(document)
    except SurfaceContractError as exc:
        # Returned rather than raised so one call site can assert "no differences"
        # over a document whose shape may itself be the planted defect.
        return [str(exc)]

    surface = parser_surface(parser)
    violations: list[str] = []
    documented: list[str] = []

    for cell in cells:
        try:
            verb = invocation_verb(cell)
        except SurfaceContractError as exc:
            violations.append(str(exc))
            continue
        documented.append(verb)
        if verb not in surface:
            continue  # reported once, below, as a verb-set difference
        expected = surface[verb]
        claimed = documented_invocation(cell, expected.takes_value)
        if claimed.options != expected.options:
            violations.append(
                f"{verb}: missing {sorted(expected.options - claimed.options)}, "
                f"unexpected {sorted(claimed.options - expected.options)}")
        if claimed.positionals != expected.positionals:
            violations.append(
                f"{verb}: documents {claimed.positionals} positional(s), parser "
                f"accepts {expected.positionals}")

    violations.extend(_verb_set_violations(documented, surface))
    return violations


def _verb_set_violations(
    documented: Sequence[str], surface: Mapping[str, VerbSurface]
) -> list[str]:
    """Verb-set differences, plus duplicate rows for one verb.

    Duplication is checked because set equality cannot see it, and two rows for one
    verb can disagree -- one correct, one stale -- with every other assertion here
    still passing. Same document-level blindness the unique-heading rule closes, one
    level down.
    """
    violations = []
    seen = set(documented)
    if seen != set(surface):
        violations.append(
            f"verb set: missing {sorted(set(surface) - seen)}, "
            f"unexpected {sorted(seen - set(surface))}")
    duplicated = sorted({verb for verb in seen if documented.count(verb) > 1})
    if duplicated:
        violations.append(
            f"verb set: {len(documented)} row(s) for {len(seen)} verb(s); "
            f"duplicated {duplicated}")
    return violations
