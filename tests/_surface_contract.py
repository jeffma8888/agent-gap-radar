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

WHY REQUIREDNESS IS A SECOND, SEPARATE COMPARISON
`surface_violations()` compares flag NAMES, option ARITY and POSITIONAL COUNTS, and it
reads a cell through `_tokens()`, which strips `[]` before comparing -- so the table's
own `<x>` required / `[x]` optional notation is invisible to it. That blindness shipped
four token-level drifts at once: `validate` and `report` documented an optional `<repo>`
as required, and `prd` documented an optional `<repo>` AND an optional `--gap` as
required, so a consumer reading the contract alone believed it had to resolve a gap id
before it could emit a `prd.json` -- while `README.md` published the working default.
`requiredness_violations()` therefore reads the brackets instead of discarding them, and
it takes its surface as an ARGUMENT rather than calling `parser_surface()` itself: no
shipped option is required, so the option half of the rule is only provable against a
SYNTHETIC surface, and a rule that cannot be proved in one direction is a rule nobody
can trust in the other.

WHY POSITIONAL REQUIREDNESS IS MATCHED BY INDEX
A cell spells its positionals in the consumer's vocabulary (`<ID>`, `<repo>`), not in
argparse's (`gap_id`, `path`), so there is no name to join on -- the nth documented
positional is compared against the nth positional the parser registers. That only holds
while the two counts agree, so a disagreement is reported as "not decidable" instead of
being zipped over silently: `zip()` would drop the tail and report agreement about
arguments it never looked at.

WHY THE TABLE READER TAKES A HEADING
The same document now publishes a second kind of surface: the on-disk record shape,
under its own `###` headings. Those tables are read by COLUMN NAME rather than by
"cell 0 of each row", so `gfm_table()` returns whole rows and `GfmTable.column()`
resolves a named column, while `surface_table_cells()` stays the cell-0 reader the
stable-surface comparison needs. One parser, two callers: a second GFM parser one
directory over is the duplicated invariant this product has already paid three times
to remove, and it would drift exactly the way the hand-copied table did.

WHY A SECOND TABLE PUBLISHES THE DEFAULTS, AND NOT A THIRD COLUMN
A stable-surface cell brackets an argument the CLI runs without and stops there: it
cannot say WHAT the parse fills in. That was cosmetic until iteration 255, when
`scan --floor` made one of those fill-ins -- the confidence floor, `2` -- decide
`--exit-code`'s verdict, `--prd`'s selection and the fields `--json` publishes, and the
document published the number nowhere. `## Defaults` therefore carries one row per
value-bearing argument with a default, and `defaults_violations()` compares the set of
(verb, argument, value) triples against `build_parser()` in BOTH directions. A separate
table rather than a widened surface row on purpose: the surface comparison reads cell 0
and nothing else (above), and a third column would either be invisible to it or drag it
into the Promise prose that rule exists to keep out.

WHY AN ARGUMENT IS NAMED THE WAY THE PARSER NAMES IT
A surface cell spells positionals in the consumer's vocabulary (`<repo>`), which is
exactly why requiredness above is matched by INDEX -- there is no name to join on. A
per-row SET comparison has no index to fall back on, so this table publishes the name
the parser knows: an option's longest spelling, a positional's `dest`. Longest rather
than first because that is the spelling a document publishes, and a tie is broken
alphabetically so the choice is deterministic rather than registration-order luck.

WHY BOOLEAN FLAGS ARE NOT DEFAULTS HERE, AND WHY AN EMPTY-LOOKING VALUE RAISES
`nargs == 0` is argparse's spelling for a flag that consumes nothing, and every one of
them defaults to off -- which the surface table's `[--json]` already says. Publishing
them would cost the table its signal, so they are skipped and the document says so.
`_render_default()` then refuses a value that renders blank or carries a pipe, a
backtick or a newline: such a value cannot be published in a GFM cell unambiguously, and
a blank cell would compare equal to a blank cell for the wrong reason.
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

#: The heading whose table publishes what an OMITTED argument is filled in with, and
#: that table's exact header. The header is asserted whole rather than resolved column
#: by column: an added or reordered column is a shape change, and a reader that shrugs
#: at one reads some other cell as the value.
DEFAULTS_HEADING = "## Defaults"
DEFAULTS_COLUMNS = ("Verb", "Argument", "Default")

#: One defaults cell: a single backticked value and nothing else. Prose around the value
#: would let "`2` (see below)" satisfy an assertion about `2`, and `.` is a value only
#: backticks can tell from a full stop.
_BACKTICKED_CELL = re.compile(r"`([^`]+)`")

#: Characters no published default may contain: a pipe ends the cell, a backtick ends the
#: code span, a newline ends the row.
_UNPUBLISHABLE_IN_A_CELL = "|`\n"

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
    #: Every argument name this verb REQUIRES: an option's option strings when
    #: `action.required`, a positional's `dest` when its `nargs` is neither `"?"` nor
    #: `"*"`. One set for both kinds because a documented cell brackets them the same
    #: way, so the rule that reads the brackets should not care which it is looking at.
    required: frozenset[str] = frozenset()
    #: Positional `dest`s in the order the parser registers them, so the nth documented
    #: positional can be named as well as judged. Defaulted for synthetic surfaces; a
    #: length disagreeing with `positionals` is reported, never zipped over.
    positional_dests: tuple[str, ...] = ()


@dataclass(frozen=True)
class GfmTable:
    """One GFM table read out of a published document, cells stripped.

    Rows are whole cell tuples rather than one chosen cell, because the record-shape
    tables published by the contract are read by COLUMN NAME (`Required`, `Model`) and
    a caller cannot name a column it cannot see. `heading` is carried so a message can
    say WHICH table refused, which matters once one document publishes several.
    """

    heading: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def column(self, name: str) -> tuple[str, ...]:
        """Every data row's cell under the header cell named exactly `name`.

        Fails closed when the header names that column zero times OR more than once.
        Silently taking the first of two identically-headed columns is how a stale
        column answers for a live one with every assertion still passing -- the same
        document-level blindness the unique-heading rule closes, one level down.
        """
        at = [i for i, cell in enumerate(self.header) if cell == name]
        if len(at) != 1:
            raise SurfaceContractError(
                f"table under {self.heading!r} has {len(at)} column(s) headed "
                f"{name!r}, expected exactly 1; header is {list(self.header)}")
        return tuple(row[at[0]] for row in self.rows)


@dataclass(frozen=True)
class DocumentedInvocation:
    """What one table cell CLAIMS a verb accepts."""

    verb: str
    options: frozenset[str]
    positionals: int


@dataclass(frozen=True)
class DocumentedToken:
    """One argument a table cell spells, with the bracketing kept.

    `DocumentedInvocation` deliberately throws bracketing away -- it answers "which
    flags, how many positionals" -- so requiredness needs a representation that keeps
    it. Both are built from ONE tokenizer rather than two: a second opinion about which
    token is an option value is the duplicated invariant this module exists to avoid.
    """

    #: The token with backticks and brackets removed: `--floor`, `<repo>`.
    name: str
    is_option: bool
    #: The cell wraps this argument in `[...]`, i.e. claims the CLI runs without it.
    optional: bool


@dataclass(frozen=True)
class ArgumentDefault:
    """One (verb, argument, default) triple, as a parser reports it or a row claims it.

    The value is carried as the TEXT a table publishes, never as the Python object: the
    document is the other side of every comparison here and it can only hold text.
    Rendering happens in exactly one place (`_render_default()`), so the parser side and
    the document side can never be compared through two different spellings of one value
    -- which is the same one-reader rule the GFM parser above is built on.
    """

    verb: str
    #: The name the PARSER knows: an option's longest spelling, a positional's `dest`.
    argument: str
    default: str

    @property
    def label(self) -> str:
        """`verb argument=value` -- the one spelling every message below uses."""
        return f"{self.verb} {self.argument}={self.default}"


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
    return {verb: _verb_surface(subparser)
            for verb, subparser in _verb_subparsers(parser).items()}


def _verb_subparsers(
    parser: argparse.ArgumentParser | None = None,
) -> dict[str, argparse.ArgumentParser]:
    """Every verb the parser registers, mapped to the subparser that owns it.

    Shared by `parser_surface()` and `parser_defaults()` rather than written twice: two
    copies of a fail-closed lookup are two chances for one of them to start returning an
    empty mapping quietly, and an empty mapping is what makes every comparison below two
    empty sets agreeing with each other. The message is unchanged from when this lived
    inside `parser_surface()`, so a caller asserting on it still reads the same words.
    """
    parser = parser if parser is not None else build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise SurfaceContractError(
        "parser registers no subcommands, so there is no surface to compare "
        "against; refusing to report agreement between two empty sets")


def _verb_surface(subparser: argparse.ArgumentParser) -> VerbSurface:
    """One subparser's option strings, positional count, value map and requiredness."""
    options: set[str] = set()
    takes_value: dict[str, bool] = {}
    required: set[str] = set()
    positional_dests: list[str] = []
    positionals = 0
    for action in subparser._actions:
        if not action.option_strings:
            positionals += 1
            positional_dests.append(action.dest)
            # `"?"` and `"*"` are the two spellings argparse uses for a positional the
            # parse succeeds without. `None` (exactly one), an int and `"+"` all mean
            # the run is refused when the token is absent.
            if action.nargs not in ("?", "*"):
                required.add(action.dest)
            continue
        if set(action.option_strings) & _IMPLICIT_OPTIONS:
            continue
        options.update(action.option_strings)
        if action.required:
            # Every spelling of a required option is required, so `-g` and `--gap`
            # answer the same way whichever one a cell happens to document.
            required.update(action.option_strings)
        # `nargs == 0` is how argparse spells a flag that consumes nothing
        # (`store_true`); anything else -- including the default `None` -- consumes at
        # least one token.
        for option_string in action.option_strings:
            takes_value[option_string] = action.nargs != 0
    return VerbSurface(frozenset(options), positionals, takes_value,
                       frozenset(required), tuple(positional_dests))


def _cells(row: str) -> list[str]:
    """The pipe-delimited cells of one GFM row, outer pipes discarded."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|")


def _table_lines(
    document: str, heading: str = STABLE_SURFACE_HEADING
) -> list[str]:
    """Header, separator and data rows of the table under `heading`.

    `heading` defaults to the stable-surface heading, so every existing caller and
    every message it can raise are unchanged. It is a parameter because the contract
    now publishes a SECOND kind of surface -- the on-disk record shape, under its own
    `###` headings -- and a second GFM parser one directory over is the duplicated
    invariant this product has already paid three times to remove.

    The heading must occur EXACTLY ONCE. A detector keyed on a heading string cannot
    otherwise see document-level duplication: a second `## The stable surface` section
    would leave one whole table unexamined while every assertion downstream passed.
    """
    lines = document.splitlines()
    at = [i for i, line in enumerate(lines)
          if line.strip() == heading]
    if len(at) != 1:
        raise SurfaceContractError(
            f"heading {heading!r} occurs {len(at)} time(s) in the "
            f"document, expected exactly 1")

    cursor = at[0] + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines) or not _is_table_row(lines[cursor]):
        raise SurfaceContractError(
            f"no table follows heading {heading!r}")

    table: list[str] = []
    while cursor < len(lines) and _is_table_row(lines[cursor]):
        table.append(lines[cursor])
        cursor += 1
    if len(table) < 3 or not _SEPARATOR_ROW.fullmatch(table[1].strip()):
        raise SurfaceContractError(
            f"table under {heading!r} is not a header row, a "
            f"'|---|' separator and at least one data row")
    return table


def gfm_table(
    document: str, heading: str = STABLE_SURFACE_HEADING
) -> GfmTable:
    """The whole table under `heading`: header cells and every data row's cells.

    The width check lives HERE rather than in each caller, because a stray pipe does
    not announce itself -- it shifts every cell after it, so a reader asking for cell 1
    silently gets cell 0's tail. Failing loudly on a ragged row is what keeps "the
    document says X" from meaning "the document says something, one column over".
    """
    header_line, _separator, *data = _table_lines(document, heading)
    header = tuple(_cells(header_line))
    rows: list[tuple[str, ...]] = []
    for row in data:
        row_cells = _cells(row)
        if len(row_cells) != len(header):
            raise SurfaceContractError(
                f"table row {row.strip()!r} has {len(row_cells)} cell(s), but the "
                f"header row has {len(header)}")
        rows.append(tuple(row_cells))
    return GfmTable(heading, header, tuple(rows))


def surface_table_cells(
    document: str, heading: str = STABLE_SURFACE_HEADING
) -> list[str]:
    """The FIRST cell of every data row of the stable-surface table, in order.

    Only cell 0 is returned, and that is the whole point -- see the module docstring on
    why reading the Promise cell would let prose satisfy an assertion about the
    invocation. Every data row is required to have the header's width, so a stray pipe
    inside a Promise cell fails loudly here instead of silently shifting which text is
    read as the invocation.
    """
    return [row[0] for row in gfm_table(document, heading).rows]


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


def documented_tokens(
    cell: str, takes_value: Mapping[str, bool]
) -> tuple[DocumentedToken, ...]:
    """Every argument one first cell spells, in order, bracketing preserved.

    `takes_value` comes FROM THE PARSER, never from the shape of the documented token:
    that is what makes `[--floor N]` one option and `[--json] [--prd]` two, without
    this module holding a second opinion about which flags carry values.

    Optionality is read from the token that OPENS a group, because a valued option
    closes its bracket on its value (`[--floor N]` is `[--floor` then `N]`). Reading it
    per-token instead would call `--floor` required and `N` optional.
    """
    tokens = _tokens(cell)
    out: list[DocumentedToken] = []
    expecting_value = False
    for raw in tokens[2:]:
        token = raw.strip("[]")
        if not token:
            continue
        # Tested before `expecting_value` on purpose, matching the order this
        # tokenizer has always used: a token spelled like a flag is read as a flag even
        # where a value was expected, so `[--gaps --json]` reports two options rather
        # than swallowing the second.
        if token.startswith("-"):
            out.append(DocumentedToken(token, True, raw.startswith("[")))
            expecting_value = takes_value.get(token, False)
            continue
        if expecting_value:
            expecting_value = False  # the value of the option just seen
            continue
        out.append(DocumentedToken(token, False, raw.startswith("[")))
    return tuple(out)


def documented_invocation(
    cell: str, takes_value: Mapping[str, bool]
) -> DocumentedInvocation:
    """Parse one first cell into the surface it claims.

    Bracketing is discarded here on purpose: this answers "which flags, how many
    positionals", and `requiredness_violations()` answers what the brackets claim. An
    unknown verb is tokenized with an empty map -- its option/arity numbers are then
    not meaningful, and the caller reports it as a verb-set difference instead.
    """
    tokens = documented_tokens(cell, takes_value)
    return DocumentedInvocation(
        invocation_verb(cell),
        frozenset(token.name for token in tokens if token.is_option),
        sum(1 for token in tokens if not token.is_option))


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


def requiredness_violations(
    surface: Mapping[str, VerbSurface], document: str
) -> list[str]:
    """Every argument whose bracketing disagrees with the parser about requiredness.

    A pure function of its two arguments: the surface is passed IN rather than read from
    `build_parser()`, because no shipped option is required and so the option half of
    this rule is only demonstrable against a synthetic surface. An unreadable document
    is returned as a violation rather than raised, mirroring `surface_violations()`, so
    one call site can assert "no disagreements" over a document whose SHAPE may itself
    be the planted defect.

    Verbs the surface does not know are skipped: that is a verb-set difference, which
    `surface_violations()` already reports, and reporting it twice would make one defect
    read as two.
    """
    try:
        cells = surface_table_cells(document)
    except SurfaceContractError as exc:
        return [str(exc)]

    violations: list[str] = []
    for cell in cells:
        try:
            verb = invocation_verb(cell)
        except SurfaceContractError as exc:
            violations.append(str(exc))
            continue
        expected = surface.get(verb)
        if expected is None:
            continue
        violations.extend(_cell_requiredness_violations(
            verb, documented_tokens(cell, expected.takes_value), expected))
    return violations


def _cell_requiredness_violations(
    verb: str, tokens: Sequence[DocumentedToken], expected: VerbSurface
) -> list[str]:
    """One cell's disagreements: positionals by index, options by name."""
    if len(expected.positional_dests) != expected.positionals:
        return [f"{verb}: surface reports {expected.positionals} positional(s) but "
                f"names {len(expected.positional_dests)}, so requiredness is not "
                f"decidable"]

    documented = [token for token in tokens if not token.is_option]
    if len(documented) != expected.positionals:
        # Reported, never zipped over: `zip()` drops the tail and would claim agreement
        # about positionals it never compared. The COUNT difference itself is
        # `surface_violations()`'s to report, so this only says why the brackets went
        # unjudged.
        return [f"{verb}: documents {len(documented)} positional(s) against the "
                f"parser's {expected.positionals}, so their requiredness is not "
                f"decidable by position"]

    violations: list[str] = []
    for index, token in enumerate(documented):
        dest = expected.positional_dests[index]
        violations.extend(
            _requiredness_violation(verb, token, dest, dest in expected.required))
    for token in tokens:
        if not token.is_option or token.name not in expected.options:
            continue  # an invented flag; `surface_violations()` reports it
        violations.extend(_requiredness_violation(
            verb, token, token.name, token.name in expected.required))
    return violations


def _requiredness_violation(
    verb: str, token: DocumentedToken, parser_name: str, required: bool
) -> list[str]:
    """The one message for a bracketing that disagrees, or nothing.

    Returns a list so a caller can `extend()` without branching on `None`, and names
    BOTH spellings when they differ: the documented token is what an editor has to
    change, the `dest` is what makes the verdict checkable against the parser.
    """
    if token.optional == (not required):
        return []  # documented optional exactly when the parser is optional
    where = (repr(token.name) if token.name == parser_name
             else f"{token.name!r} (parser {parser_name!r})")
    documented_as = "optional" if token.optional else "required"
    parser_says = "required" if required else "optional"
    return [f"{verb}: documents {where} as {documented_as}, "
            f"parser makes it {parser_says}"]


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


def parser_defaults(
    parser: argparse.ArgumentParser | None = None
) -> frozenset[ArgumentDefault]:
    """Every value-bearing argument `build_parser()` defaults, as publishable triples.

    `parser` is injectable for the same reason `parser_surface()`'s is: the fail-closed
    paths -- a parser with no subcommands, a parser whose verbs default nothing -- are
    only reachable against a synthetic one, and a rule that cannot be shown failing is a
    rule nobody can trust when it passes.

    FAILS CLOSED on an empty result: a parser that defaults nothing would make the set
    comparison two empty sets agreeing, so it raises instead of certifying a table that
    could then say anything.
    """
    defaults = {
        ArgumentDefault(verb, _default_argument_name(action),
                        _render_default(action.default))
        for verb, subparser in _verb_subparsers(parser).items()
        for action in subparser._actions
        if _publishes_a_default(action)
    }
    if not defaults:
        raise SurfaceContractError(
            "parser carries no value-bearing default, so there is nothing for the "
            f"{DEFAULTS_HEADING!r} table to be compared against; refusing to report "
            "agreement between two empty sets")
    return frozenset(defaults)


def _publishes_a_default(action: argparse.Action) -> bool:
    """Is this argument one the defaults table publishes?

    Three exclusions, each for its own reason. argparse's own `-h` is not part of any
    published surface (its default is a sentinel, never a value). `nargs == 0` is a flag
    that consumes nothing, and every one defaults to off -- which the surface table's
    bracketing already says. A `None` default is argparse's "nothing was filled in", and
    a row saying so would publish the absence of a default as a default.
    """
    if set(action.option_strings) & _IMPLICIT_OPTIONS:
        return False
    if action.nargs == 0:
        return False
    return action.default is not None


def _default_argument_name(action: argparse.Action) -> str:
    """The name the PARSER knows this argument by -- the join key for one table row.

    Longest option spelling, ties broken alphabetically: a document publishes `--floor`
    rather than a short alias, and a deterministic tie-break keeps the join key from
    depending on the order the flags happened to be registered in. A positional has no
    typed name at all, so its `dest` is the only thing both sides can name it by.
    """
    if not action.option_strings:
        return action.dest
    return sorted(action.option_strings, key=lambda option: (-len(option), option))[0]


def _render_default(value: object) -> str:
    """The TEXT a table cell publishes for `value`, or a refusal.

    `str()` and not `repr()`: the cell is what a consumer types after the flag, and
    `'.'` is not what anyone types. That makes the rendering lossy about TYPE, which is
    deliberate -- a contract table publishes the value a consumer supplies, and the type
    is the parser's business (`--floor` is `type=int`, and `2` is what a caller writes).

    A value that renders blank, or that carries a pipe, a backtick or a newline, is
    refused rather than published: none of the three can survive a GFM cell, and a blank
    cell would compare equal to another blank cell for the wrong reason.
    """
    text = str(value)
    if not text.strip():
        raise SurfaceContractError(
            f"default {value!r} renders as blank text, which cannot be published in a "
            f"table cell distinguishably from an empty one")
    bad = sorted({character for character in text
                  if character in _UNPUBLISHABLE_IN_A_CELL})
    if bad:
        raise SurfaceContractError(
            f"default {value!r} contains {bad} and so cannot be published in a GFM "
            f"cell without breaking the row")
    return text


def documented_defaults(document: str) -> tuple[ArgumentDefault, ...]:
    """Every row of the `## Defaults` table, in DOCUMENT order.

    Order is preserved -- a tuple, not a set -- because set equality cannot see a
    duplicated row, and two rows for one argument can disagree with one of them stale
    while every other assertion passes. Same document-level blindness the unique-heading
    rule closes, one level down; `defaults_violations()` is where it is reported.

    The header is compared WHOLE. Resolving three columns by name would pass a table
    that carried a fourth, and a fourth column is where a second, unread opinion about a
    default would live.
    """
    table = gfm_table(document, DEFAULTS_HEADING)
    if table.header != DEFAULTS_COLUMNS:
        raise SurfaceContractError(
            f"table under {DEFAULTS_HEADING!r} has header {list(table.header)}, "
            f"expected exactly {list(DEFAULTS_COLUMNS)}")
    return tuple(
        ArgumentDefault(*(_cell_value(cell, column)
                          for cell, column in zip(row, DEFAULTS_COLUMNS, strict=True)))
        for row in table.rows)


def _cell_value(cell: str, column: str) -> str:
    """The one backticked value a defaults cell carries, or a refusal.

    Backticks are required rather than merely stripped: `.` is a value only a code span
    can tell from a full stop, and a cell allowed to carry prose beside its value lets
    "`2` (see below)" answer an assertion about `2`.
    """
    match = _BACKTICKED_CELL.fullmatch(cell.strip())
    if match is None:
        raise SurfaceContractError(
            f"{column} cell {cell!r} under {DEFAULTS_HEADING!r} is not a single "
            f"backticked value")
    return match.group(1)


def defaults_violations(
    document: str, parser: argparse.ArgumentParser | None = None
) -> list[str]:
    """Every way the published defaults table and the parser disagree.

    An empty list means the document names exactly the arguments the parser defaults,
    with exactly the values it fills in, once each. An unreadable table is RETURNED as a
    violation rather than raised, mirroring `surface_violations()`, so one call site can
    assert "no disagreements" over a document whose shape may itself be the planted
    defect. The PARSER side still raises: a parser this module cannot introspect is not a
    documentation defect, and swallowing it would report agreement with nothing.
    """
    try:
        documented = documented_defaults(document)
    except SurfaceContractError as exc:
        return [str(exc)]

    expected = parser_defaults(parser)
    violations: list[str] = []

    keys = [(entry.verb, entry.argument) for entry in documented]
    duplicated = sorted(f"{verb} {argument}" for verb, argument in set(keys)
                        if keys.count((verb, argument)) > 1)
    if duplicated:
        violations.append(
            f"defaults table: {len(keys)} row(s) for {len(set(keys))} argument(s); "
            f"duplicated {duplicated}")

    claimed = frozenset(documented)
    missing = sorted(entry.label for entry in expected - claimed)
    surplus = sorted(entry.label for entry in claimed - expected)
    if missing:
        violations.append(
            f"defaults table: the parser fills in {missing}, and no row says so")
    if surplus:
        violations.append(
            f"defaults table: rows claim {surplus}, which the parser does not")
    return violations
