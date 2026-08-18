"""Iteration 10 behaviors: the consumer contract's stable-surface table is DERIVED from
`agent_gap_radar.cli.build_parser()` instead of hand-copied.

`docs/CONSUMER_CONTRACT.md` is the one document written for machine consumers, and its
"The stable surface" table is the list a CI job or build loop is told it may rely on.
Five of its seven rows named LESS than the CLI accepts, so a consumer copying a
documented invocation could get exit 0 over whatever register sat in its own working
directory -- a silent wrong answer, not an error. This module turns that table into an
assertion.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. The document is read as
published text and the expectation is introspected from the public `build_parser()` at
test time. No verb, flag, positional count or cell text is hand-listed as an expectation
anywhere in this file, and every known-bad is DERIVED from the shipped table.

Habits kept on purpose:

* the heading is asserted unique in BOTH units -- lines equal to it and raw substring
  occurrences -- because a check keyed on a heading string cannot see document-level
  duplication, and the two units disagree about a heading quoted mid-line;
* only each row's FIRST cell is read. The Promise cell names flags in prose, so a
  whole-row reader would let prose satisfy an assertion about the invocation. The
  known-bad that proves it is DERIVED: the flag it deletes from the invocation is chosen
  BECAUSE the rest of that row still mentions it, so a whole-row reader passes the
  mutation while a first-cell reader fails it;
* whether an option consumes the token after it is read FROM THE PARSER, never from the
  flag's spelling, and both branches are exercised;
* the two-sided proof is a SWEEP, not four hand-picked cases: every documented flag is
  deleted in turn, an invented flag is added to every verb in turn, and every documented
  positional is deleted in turn. Every mutation asserts it actually CHANGED the text --
  a known-bad that silently no-ops reads exactly like a check that passed;
* anti-vacuity is asserted over the parser's own shape (some verb takes more than one
  positional, some verb takes none, some option consumes a value and some consumes
  nothing), so no comparison here is the `set() == set()` green that means nothing;
* no test here may stand down. One test asserts that over this module's own source,
  because a stood-down test is invisible in a suite total.
"""

from __future__ import annotations

import argparse
import pathlib
import re
from collections.abc import Callable
from typing import NamedTuple

import pytest

from agent_gap_radar.cli import build_parser

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The heading behavior 1 names. Asserted to occur exactly once.
SURFACE_HEADING = "## The stable surface"

#: Every invocation in the table's first column begins with this token.
INVOCATION_PREFIX = "radar"

#: argparse adds these to every subparser; behavior 3 excludes them by name.
HELP_FLAGS = frozenset({"-h", "--help"})

#: A flag no parser registers, used only to build the invented-flag known-bads.
INVENTED_FLAG = "--" + "not-a-real-flag"

_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


class VerbSurface(NamedTuple):
    """What one subparser accepts, read from argparse's own action list."""

    options: frozenset[str]
    takes_value: dict[str, bool]
    positionals: int


def _parser_surface() -> dict[str, VerbSurface]:
    """verb -> what that subparser accepts. The ONLY source of expectations here."""
    parser = build_parser()
    subactions = [
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subactions) == 1, (
        "build_parser() must expose exactly one subparsers action to introspect, found "
        f"{len(subactions)} -- fail closed rather than compare a table against an empty "
        "surface, which every table satisfies")
    surface: dict[str, VerbSurface] = {}
    for verb, subparser in subactions[0].choices.items():
        options: set[str] = set()
        takes_value: dict[str, bool] = {}
        positionals = 0
        for action in subparser._actions:
            if not action.option_strings:
                positionals += 1
                continue
            if HELP_FLAGS.intersection(action.option_strings):
                continue
            for flag in action.option_strings:
                options.add(flag)
                # nargs == 0 is argparse's shape for a store_true / count flag: it
                # consumes NOTHING that follows it. Read from the action, never from
                # the flag's spelling.
                takes_value[flag] = action.nargs != 0
        surface[verb] = VerbSurface(frozenset(options), takes_value, positionals)
    assert surface, "build_parser() registers no verbs; an empty surface passes any table"
    return surface


SURFACE = _parser_surface()
CONTRACT_TEXT = CONTRACT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# document plumbing -- parse only what the contract publishes
# ---------------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|")


def _surface_table(document: str) -> tuple[list[str], list[list[str]], list[int]]:
    """(header cells, data rows, 0-based line index of each data row).

    Behavior 1's shape: the heading occurs exactly once, then a header row, then a
    `|---|` separator, then data rows UNTIL the first line that is not a table row.
    """
    lines = document.splitlines()
    heading_lines = [i for i, line in enumerate(lines) if line.strip() == SURFACE_HEADING]
    occurrences = document.count(SURFACE_HEADING)
    assert len(heading_lines) == 1 and occurrences == 1, (
        f"heading {SURFACE_HEADING!r} must appear EXACTLY ONCE: found "
        f"{len(heading_lines)} heading line(s) at lines {[i + 1 for i in heading_lines]} "
        f"and {occurrences} raw occurrence(s). A check keyed on a heading string cannot "
        "see document-level duplication, so a second copy would leave one table entirely "
        "unexamined while every assertion still passed")
    index = heading_lines[0] + 1
    while index < len(lines) and not _is_table_row(lines[index]):
        assert not lines[index].startswith("## "), (
            f"no table between {SURFACE_HEADING!r} and the next section heading "
            f"{lines[index]!r}")
        index += 1
    assert index < len(lines), f"no table follows {SURFACE_HEADING!r}"
    header = _cells(lines[index])
    assert index + 1 < len(lines) and _is_table_row(lines[index + 1]), (
        f"the {SURFACE_HEADING!r} table has a header row and no separator row")
    separator = _cells(lines[index + 1])
    assert separator and all(_SEPARATOR_CELL.match(cell) for cell in separator), (
        f"the row under the header is not a GFM separator: {separator}")
    rows: list[list[str]] = []
    numbers: list[int] = []
    index += 2
    while index < len(lines) and _is_table_row(lines[index]):
        rows.append(_cells(lines[index]))
        numbers.append(index)
        index += 1
    assert rows, f"the {SURFACE_HEADING!r} table has a header and no data rows"
    for number, row in zip(numbers, rows):
        assert len(row) == len(header), (
            f"line {number + 1}: row has {len(row)} cell(s), header has {len(header)} -- "
            f"a cell contains a pipe, so every cell after it is shifted: {row}")
    return header, rows, numbers


def _tokens(invocation: str) -> list[str]:
    """Whitespace tokens of a cell, backticks and optional-brackets stripped."""
    return [token.strip("[]") for token in invocation.replace("`", "").split()]


def _invocation_verb(cell: str) -> str:
    tokens = _tokens(cell)
    assert len(tokens) >= 2 and tokens[0] == INVOCATION_PREFIX, (
        f"first cell {cell!r} is not an invocation of the form "
        f"{INVOCATION_PREFIX} <verb>")
    return tokens[1]


def _kinds(raw_tokens: list[str], verb: str) -> list[str]:
    """Per raw token: prefix / verb / option / value / positional.

    A token is a POSITIONAL when, stripped of backticks and brackets, it is non-empty,
    does not begin with `-`, and was not consumed as the value of the immediately
    preceding option -- where whether an option takes a value comes from the PARSER.
    """
    takes_value = SURFACE[verb].takes_value if verb in SURFACE else {}
    kinds = ["prefix", "verb"]
    pending = False
    for token in raw_tokens[2:]:
        bare = token.strip("[]")
        if not bare:
            kinds.append("value" if pending else "positional")
            continue
        if bare.startswith("-"):
            kinds.append("option")
            pending = takes_value.get(bare, False)
        elif pending:
            kinds.append("value")
            pending = False
        else:
            kinds.append("positional")
    return kinds


def _documented(cell: str, verb: str) -> tuple[set[str], int]:
    """(option strings, positional count) that a first cell names.

    An INVENTED flag has no parser entry, so its arity is unknowable and it is assumed
    to consume nothing; the option-set difference reports it either way.
    """
    raw = cell.replace("`", "").split()
    kinds = _kinds(raw, verb)
    options = {
        token.strip("[]") for token, kind in zip(raw, kinds) if kind == "option"
    }
    positionals = sum(1 for kind in kinds[2:] if kind == "positional")
    return options, positionals


# ---------------------------------------------------------------------------
# the check -- one entry point, so a known-bad fails the same way a real drift does
# ---------------------------------------------------------------------------

def _violations(document: str) -> list[str]:
    _header, rows, _numbers = _surface_table(document)
    first_cells = [row[0] for row in rows]
    verbs = [_invocation_verb(cell) for cell in first_cells]
    problems: list[str] = []
    missing = sorted(set(SURFACE) - set(verbs))
    unexpected = sorted(set(verbs) - set(SURFACE))
    if missing or unexpected:
        problems.append(f"verb rows: missing {missing}, unexpected {unexpected}")
    duplicated = sorted({verb for verb in verbs if verbs.count(verb) > 1})
    if duplicated:
        problems.append(
            f"verb rows: duplicated {duplicated} -- set equality cannot see a second row")
    for verb, cell in zip(verbs, first_cells):
        if verb not in SURFACE:
            continue
        options, positionals = _documented(cell, verb)
        expected = SURFACE[verb]
        opt_missing = sorted(expected.options - options)
        opt_unexpected = sorted(options - expected.options)
        if opt_missing or opt_unexpected:
            problems.append(
                f"{verb}: option strings missing {opt_missing}, "
                f"unexpected {opt_unexpected}")
        if positionals != expected.positionals:
            problems.append(
                f"{verb}: documents {positionals} positional(s), "
                f"parser accepts {expected.positionals}")
    return problems


def _check(document: str) -> None:
    problems = _violations(document)
    assert not problems, (
        "the documented surface disagrees with build_parser():\n" + "\n".join(problems))


def _refused(document: str) -> str:
    """Run the check on a known-bad, require it to FAIL, return the message."""
    with pytest.raises(AssertionError) as caught:
        _check(document)
    return str(caught.value)


# ---------------------------------------------------------------------------
# mutators -- every known-bad is built in memory from the SHIPPED text
# ---------------------------------------------------------------------------

def _rewrite_first_cell(
    document: str, verb: str, transform: Callable[[list[str]], list[str]]
) -> str:
    """`document` with `verb`'s first-cell tokens transformed. Asserts it changed."""
    _header, rows, numbers = _surface_table(document)
    lines = document.splitlines(keepends=True)
    for number, row in zip(numbers, rows):
        if _invocation_verb(row[0]) != verb:
            continue
        cell = row[0]
        assert cell.startswith("`") and cell.endswith("`"), (
            f"first cell of {verb!r} is not a backticked invocation: {cell!r}")
        rebuilt = "`" + " ".join(transform(cell[1:-1].split())) + "`"
        assert rebuilt != cell, (
            f"mutation of {verb!r} did not change the cell {cell!r} -- a known-bad that "
            "no-ops proves nothing and reads exactly like a check that passed")
        ending = "\n" if lines[number].endswith("\n") else ""
        lines[number] = "| " + " | ".join([rebuilt] + row[1:]) + " |" + ending
        mutated = "".join(lines)
        assert mutated != document, "mutation did not change the document"
        return mutated
    raise AssertionError(f"no data row documents verb {verb!r}")


def _without_flag(verb: str, flag: str) -> Callable[[list[str]], list[str]]:
    def transform(raw: list[str]) -> list[str]:
        kinds = _kinds(raw, verb)
        drop: set[int] = set()
        for index, (token, kind) in enumerate(zip(raw, kinds)):
            if kind == "option" and token.strip("[]") == flag:
                drop.add(index)
                if index + 1 < len(kinds) and kinds[index + 1] == "value":
                    drop.add(index + 1)
        assert drop, f"{verb!r} does not name {flag!r}, so nothing would be mutated"
        return [token for index, token in enumerate(raw) if index not in drop]

    return transform


def _with_invented_flag(raw: list[str]) -> list[str]:
    return raw + ["[" + INVENTED_FLAG + "]"]


def _without_last_positional(verb: str) -> Callable[[list[str]], list[str]]:
    def transform(raw: list[str]) -> list[str]:
        kinds = _kinds(raw, verb)
        indices = [index for index, kind in enumerate(kinds) if kind == "positional"]
        assert indices, f"{verb!r} documents no positional, so nothing would be mutated"
        return [token for index, token in enumerate(raw) if index != indices[-1]]

    return transform


def _with_duplicated_heading(document: str) -> str:
    mutated = document + SURFACE_HEADING + "\n"
    assert mutated != document
    return mutated


def _with_extra_row(document: str, first_cell: str, gap_lines: int = 0) -> str:
    """Append a data row `gap_lines` blank lines after the table's last row."""
    _header, _rows, numbers = _surface_table(document)
    lines = document.splitlines(keepends=True)
    row = "| " + first_cell + " | mutant row |\n"
    lines[numbers[-1] + 1: numbers[-1] + 1] = ["\n"] * gap_lines + [row]
    mutated = "".join(lines)
    assert mutated != document
    return mutated


# ---------------------------------------------------------------------------
# behavior 0 -- the derived expectations are not vacuous
# ---------------------------------------------------------------------------

def test_b0_the_introspected_surface_exercises_every_comparison() -> None:
    assert len(SURFACE) > 1, sorted(SURFACE)
    assert any(spec.positionals > 1 for spec in SURFACE.values()), SURFACE
    assert any(spec.positionals == 0 for spec in SURFACE.values()), SURFACE
    assert any(not spec.options for spec in SURFACE.values()), SURFACE
    assert any(len(spec.options) > 1 for spec in SURFACE.values()), SURFACE
    arities = [
        takes for spec in SURFACE.values() for takes in spec.takes_value.values()
    ]
    assert any(arities), "no option consumes a value; behavior 4's parser branch is dead"
    assert not all(arities), "every option consumes a value; the zero-arg branch is dead"
    assert not any(HELP_FLAGS & spec.options for spec in SURFACE.values()), (
        "-h/--help leaked into the expected surface; behavior 3 excludes them")


# ---------------------------------------------------------------------------
# behavior 1 -- one heading, one table, bounded by the first non-table line
# ---------------------------------------------------------------------------

def test_b1_the_heading_occurs_once_and_bounds_one_table() -> None:
    header, rows, numbers = _surface_table(CONTRACT_TEXT)
    assert len(header) >= 2, header
    assert len(rows) == len(SURFACE), (
        f"{len(rows)} data row(s) for {len(SURFACE)} registered verb(s)")
    assert numbers == list(range(numbers[0], numbers[0] + len(rows))), (
        f"data rows are not contiguous: {numbers}")
    for row in rows:
        assert row[0].startswith("`" + INVOCATION_PREFIX + " "), (
            f"a parsed data row's first cell is not an invocation: {row[0]!r}")


def test_b1_a_duplicated_heading_is_refused() -> None:
    message = _refused(_with_duplicated_heading(CONTRACT_TEXT))
    assert SURFACE_HEADING in message and "EXACTLY ONCE" in message, message
    assert "2 raw occurrence(s)" in message, message


def test_b1_the_table_ends_at_the_first_line_that_is_not_a_table_row() -> None:
    contiguous = _with_extra_row(CONTRACT_TEXT, "`radar mutant`", gap_lines=0)
    assert "unexpected ['mutant']" in _refused(contiguous)
    detached = _with_extra_row(CONTRACT_TEXT, "`radar mutant`", gap_lines=1)
    _check(detached)


# ---------------------------------------------------------------------------
# behavior 2 -- the documented verb set equals the registered verb set
# ---------------------------------------------------------------------------

def test_b2_documented_verbs_equal_registered_verbs() -> None:
    _header, rows, _numbers = _surface_table(CONTRACT_TEXT)
    documented = sorted(_invocation_verb(row[0]) for row in rows)
    assert documented == sorted(SURFACE), (
        f"documented {documented}, parser registers {sorted(SURFACE)}")


def test_b2_a_verb_with_no_row_is_refused() -> None:
    _header, rows, numbers = _surface_table(CONTRACT_TEXT)
    lines = CONTRACT_TEXT.splitlines(keepends=True)
    dropped = _invocation_verb(rows[0][0])
    del lines[numbers[0]]
    message = _refused("".join(lines))
    assert f"missing ['{dropped}']" in message, message


def test_b2_a_row_for_an_unregistered_verb_is_refused() -> None:
    message = _refused(_with_extra_row(CONTRACT_TEXT, "`radar mutant <repo>`"))
    assert "unexpected ['mutant']" in message, message


# ---------------------------------------------------------------------------
# behavior 3 -- per verb, the first cell's option strings equal the parser's
# ---------------------------------------------------------------------------

def test_b3_every_verb_documents_exactly_its_option_strings() -> None:
    _header, rows, _numbers = _surface_table(CONTRACT_TEXT)
    for row in rows:
        verb = _invocation_verb(row[0])
        options, _positionals = _documented(row[0], verb)
        assert options == set(SURFACE[verb].options), (
            f"{verb}: documents {sorted(options)}, "
            f"parser accepts {sorted(SURFACE[verb].options)}")


def test_b3_deleting_any_documented_flag_is_refused() -> None:
    checked = 0
    for verb, spec in sorted(SURFACE.items()):
        for flag in sorted(spec.options):
            mutated = _rewrite_first_cell(CONTRACT_TEXT, verb, _without_flag(verb, flag))
            message = _refused(mutated)
            assert f"{verb}: option strings missing ['{flag}']" in message, message
            checked += 1
    assert checked >= 2, f"the flag-deletion sweep only planted {checked} known-bad(s)"


def test_b3_an_invented_flag_is_refused_on_every_verb() -> None:
    for verb in sorted(SURFACE):
        mutated = _rewrite_first_cell(CONTRACT_TEXT, verb, _with_invented_flag)
        message = _refused(mutated)
        assert f"{verb}: option strings missing [], " in message, message
        assert f"unexpected ['{INVENTED_FLAG}']" in message, message


def test_b3_only_the_first_cell_of_a_row_is_read() -> None:
    """The deleted flag is one the row's PROSE still names, so a whole-row reader passes.

    Derived, not hand-picked: the sweep below looks for a verb whose first cell names a
    flag that also appears in a LATER cell of the same row. If no such row exists the
    discriminator cannot be armed, and this test says so instead of arming nothing.
    """
    armed: list[tuple[str, str]] = []
    _header, rows, _numbers = _surface_table(CONTRACT_TEXT)
    for row in rows:
        verb = _invocation_verb(row[0])
        options, _positionals = _documented(row[0], verb)
        prose = " ".join(row[1:])
        for flag in sorted(options):
            if flag in prose:
                armed.append((verb, flag))
    assert armed, (
        "no row names one of its own flags in its Promise prose, so the fail-open a "
        "whole-row reader would have cannot be demonstrated on the shipped document")
    for verb, flag in armed:
        mutated = _rewrite_first_cell(CONTRACT_TEXT, verb, _without_flag(verb, flag))
        _header, mutated_rows, _numbers = _surface_table(mutated)
        row = next(r for r in mutated_rows if _invocation_verb(r[0]) == verb)
        assert flag in " ".join(row[1:]), (
            f"{flag} was removed from the row's prose too, so this known-bad no longer "
            "discriminates a first-cell reader from a whole-row reader")
        assert flag not in row[0], row[0]
        assert f"{verb}: option strings missing ['{flag}']" in _refused(mutated)


# ---------------------------------------------------------------------------
# behavior 4 -- per verb, the first cell's positional count equals the parser's
# ---------------------------------------------------------------------------

def test_b4_every_verb_documents_exactly_its_positional_count() -> None:
    _header, rows, _numbers = _surface_table(CONTRACT_TEXT)
    for row in rows:
        verb = _invocation_verb(row[0])
        _options, positionals = _documented(row[0], verb)
        assert positionals == SURFACE[verb].positionals, (
            f"{verb}: documents {positionals} positional(s), "
            f"parser accepts {SURFACE[verb].positionals}")


def test_b4_deleting_any_documented_positional_is_refused() -> None:
    checked = 0
    for verb, spec in sorted(SURFACE.items()):
        if spec.positionals == 0:
            continue
        mutated = _rewrite_first_cell(
            CONTRACT_TEXT, verb, _without_last_positional(verb))
        message = _refused(mutated)
        assert (
            f"{verb}: documents {spec.positionals - 1} positional(s), "
            f"parser accepts {spec.positionals}"
        ) in message, message
        checked += 1
    assert checked >= 2, f"the positional sweep only planted {checked} known-bad(s)"


def test_b4_option_arity_is_read_from_the_parser_not_the_flag_spelling() -> None:
    """A value-taking flag swallows the next token; a zero-argument flag does not."""
    valued = sorted(
        (verb, flag)
        for verb, spec in SURFACE.items()
        for flag, takes in spec.takes_value.items()
        if takes
    )
    zero_arg = sorted(
        (verb, flag)
        for verb, spec in SURFACE.items()
        for flag, takes in spec.takes_value.items()
        if not takes
    )
    assert valued and zero_arg, (valued, zero_arg)
    verb, flag = valued[0]
    cell = "`" + f"{INVOCATION_PREFIX} {verb} [{flag} VALUE]" + "`"
    options, positionals = _documented(cell, verb)
    assert options == {flag} and positionals == 0, (cell, options, positionals)
    verb, flag = zero_arg[0]
    cell = "`" + f"{INVOCATION_PREFIX} {verb} [{flag}] AFTER" + "`"
    options, positionals = _documented(cell, verb)
    assert options == {flag} and positionals == 1, (cell, options, positionals)


# ---------------------------------------------------------------------------
# behavior 5 -- the shipped document is the known-GOOD input
# ---------------------------------------------------------------------------

def test_b5_the_shipped_contract_passes_with_no_exemption() -> None:
    assert _violations(CONTRACT_TEXT) == []


#: Stand-down constructs no test in this module may use. Every needle is BUILT by
#: concatenation: spelling one as a literal puts it in this module OWN source, so the
#: detector reports a hit on itself and the self-hit reads exactly like a real finding.
_FORBIDDEN = (
    "pytest." + "skip",
    "importor" + "skip",
    "mark." + "skip",
    "x" + "fail",
)


def _stand_down_hits(source: str) -> list[str]:
    """Stand-down constructs present in `source`, in a fixed order."""
    return [needle for needle in _FORBIDDEN if needle in source]


def test_b5_no_test_in_this_module_stands_down() -> None:
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    hits = _stand_down_hits(source)
    assert not hits, (
        f"{len(hits)} stand-down construct(s) in this module: {hits} -- a skipped or "
        "expected-to-fail test asserts nothing and is invisible in a suite total")
    # Two-sided: the silence above is evidence only if the detector demonstrably fires.
    for needle in _FORBIDDEN:
        planted = "def test_planted() -> None:\n    " + needle + "(\"reason\")\n"
        assert _stand_down_hits(planted) == [needle], (
            f"the stand-down detector missed a planted {needle!r}: "
            f"{_stand_down_hits(planted)} -- a guard nobody proves fires is decoration")


# ---------------------------------------------------------------------------
# behavior 6 -- the four named known-bads and the real document, one test run
# ---------------------------------------------------------------------------

def test_b6_four_known_bads_fail_and_the_real_document_passes_in_one_run() -> None:
    flag_verb, flag = max(
        sorted(SURFACE.items()), key=lambda item: len(item[1].options))[0], ""
    flag = sorted(SURFACE[flag_verb].options)[0]
    removed = _refused(
        _rewrite_first_cell(CONTRACT_TEXT, flag_verb, _without_flag(flag_verb, flag)))
    assert f"{flag_verb}: option strings missing ['{flag}']" in removed, removed

    bare_verb = sorted(v for v, spec in SURFACE.items() if not spec.options)[0]
    invented = _refused(
        _rewrite_first_cell(CONTRACT_TEXT, bare_verb, _with_invented_flag))
    assert f"{bare_verb}: option strings missing [], unexpected " in invented, invented
    assert INVENTED_FLAG in invented, invented

    pos_verb = max(sorted(SURFACE.items()), key=lambda item: item[1].positionals)[0]
    expected = SURFACE[pos_verb].positionals
    dropped = _refused(
        _rewrite_first_cell(CONTRACT_TEXT, pos_verb, _without_last_positional(pos_verb)))
    assert (
        f"{pos_verb}: documents {expected - 1} positional(s), "
        f"parser accepts {expected}"
    ) in dropped, dropped

    duplicated = _refused(_with_duplicated_heading(CONTRACT_TEXT))
    assert SURFACE_HEADING in duplicated, duplicated

    _check(CONTRACT_TEXT)
