"""Unit tests for the seams of `tests/_surface_contract.py`.

SCOPE. This file tests the ORACLE's helpers: the parser introspector, the table parser,
the invocation tokenizer, and the defaults reader. Iteration 10's six specified
behaviors belong to `tests/test_iter10_behavior.py`, the test engineer's file, and so
does the defaults table's per-BEHAVIOR numbering; but the assertions that the SHIPPED
document agrees with the parser sit HERE deliberately, because a brake living only in a
behavior module is a brake that can fail to land, as this iteration's own did. So no
helper ships unproven: a guard nobody watches fire is decoration, and an oracle only
ever run against a passing document has never demonstrated it can say no.

Every test builds its input in memory. Nothing here edits a file, runs a subprocess,
touches the network, or reads anything under `gaps/`, so a research pass writing
records cannot redden it.
"""

from __future__ import annotations

import argparse

import pytest

from _surface_contract import (DEFAULTS_COLUMNS, DEFAULTS_HEADING,
                               STABLE_SURFACE_HEADING, ArgumentDefault,
                               DocumentedInvocation, SurfaceContractError,
                               contract_text, defaults_violations,
                               documented_defaults, documented_invocation,
                               documented_tokens, gfm_table, invocation_verb,
                               parser_defaults, parser_surface,
                               surface_table_cells, surface_violations)

#: A minimal well-formed stable-surface section, used to plant structural defects.
_MINIMAL = "\n".join([
    "# Doc",
    "",
    STABLE_SURFACE_HEADING,
    "",
    "| Verb | Promise |",
    "|---|---|",
    "| `radar taxonomy` | the closed vocabularies |",
    "",
    "trailing prose",
    "",
])


def _replace_once(text: str, old: str, new: str) -> str:
    """Mutate in memory, asserting the target is unambiguous.

    A silent zero-replacement is how a known-bad becomes a second copy of the
    known-good, and then a test that proves nothing still passes.
    """
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} time(s)"
    return text.replace(old, new)


# --- the parser introspector -------------------------------------------------

def test_parser_surface_fails_closed_when_no_subcommands_are_registered():
    """An empty surface would make every comparison two empty sets agreeing."""
    with pytest.raises(SurfaceContractError) as exc:
        parser_surface(argparse.ArgumentParser(prog="radar"))
    assert "no subcommands" in str(exc.value)


def test_parser_surface_omits_the_help_option_argparse_adds_for_itself():
    surface = parser_surface()
    assert surface, "the real CLI registers no verbs"
    for verb, verb_surface in surface.items():
        assert not verb_surface.options & {"-h", "--help"}, verb


def test_takes_value_is_read_from_the_action_not_from_the_flag_name():
    """`--floor N` is one option and `[--json]` is none; only the parser knows."""
    surface = parser_surface()
    assert surface["list"].takes_value["--floor"] is True
    assert surface["list"].takes_value["--json"] is False
    assert surface["scan"].takes_value["--prd"] is False


# --- the invocation tokenizer -------------------------------------------------

def test_an_option_value_is_not_counted_as_a_positional():
    surface = parser_surface()
    claimed = documented_invocation("`radar report <repo> [--floor N]`",
                                    surface["report"].takes_value)
    assert claimed == DocumentedInvocation("report", frozenset({"--floor"}), 1)


def test_without_parser_metadata_the_same_cell_miscounts_its_positionals():
    """The control that arms the test above.

    Tokenized with an empty map, `N` stops being `--floor`'s value and becomes a second
    positional. That is precisely the wrong answer the parser metadata prevents, so the
    passing assertion above is load-bearing rather than incidental.
    """
    claimed = documented_invocation("`radar report <repo> [--floor N]`", {})
    assert claimed.positionals == 2


def test_zero_argument_flags_consume_nothing_that_follows_them():
    surface = parser_surface()
    claimed = documented_invocation(
        "`radar scan <target> [--gaps R] [--json] [--prd]`",
        surface["scan"].takes_value)
    assert claimed.positionals == 1
    assert claimed.options == frozenset({"--gaps", "--json", "--prd"})


def test_a_valued_option_reads_its_bracketing_from_the_token_that_opens_its_group():
    """`[--floor N]` is ONE optional option, not optional `--floor` plus required `N`.

    argparse closes the bracket on the VALUE, so a reader taking optionality per token
    would call the flag optional and its value required -- and the value is not an
    argument at all.
    """
    surface = parser_surface()
    tokens = documented_tokens("`radar report [<repo>] [--floor N]`",
                               surface["report"].takes_value)
    assert [(token.name, token.is_option, token.optional) for token in tokens] == [
        ("<repo>", False, True), ("--floor", True, True)]


def test_the_same_cell_without_brackets_reads_as_required():
    """The control that arms the test above: only the bracketing differs."""
    surface = parser_surface()
    tokens = documented_tokens("`radar report <repo> --floor N`",
                               surface["report"].takes_value)
    assert [(token.name, token.is_option, token.optional) for token in tokens] == [
        ("<repo>", False, False), ("--floor", True, False)]


def test_invocation_verb_rejects_a_cell_that_is_not_a_radar_invocation():
    with pytest.raises(SurfaceContractError) as exc:
        invocation_verb("see the section below")
    assert "not a `radar <verb> ...` invocation" in str(exc.value)


# --- the table parser --------------------------------------------------------

def test_only_the_first_cell_of_a_row_is_read():
    """The Promise cell names flags in prose; reading it would be fail-open.

    Measured on the real document: the `scan` row's Promise names `--prd` twice. With
    `--prd` deleted from the INVOCATION the flag is still present in the row, so a
    whole-row checker would find it and pass. This must still report the difference.
    """
    document = _replace_once(
        contract_text(),
        "`radar scan <target> [--gaps R] [--gap <ID>] [--json] [--floor N] [--prd] [--exit-code]`",
        "`radar scan <target> [--gaps R] [--gap <ID>] [--json] [--floor N] [--exit-code]`")
    scan_row = next(line for line in document.splitlines()
                    if line.startswith("| `radar scan"))
    assert "--prd" in scan_row, "the fail-open this test guards is not set up"
    assert "--prd" not in "".join(surface_table_cells(document))
    assert surface_violations(document) == ["scan: missing ['--prd'], unexpected []"]


def test_a_duplicated_heading_is_refused():
    document = _replace_once(
        _MINIMAL, STABLE_SURFACE_HEADING,
        f"{STABLE_SURFACE_HEADING}\n\n{STABLE_SURFACE_HEADING}")
    with pytest.raises(SurfaceContractError) as exc:
        surface_table_cells(document)
    assert "occurs 2 time(s)" in str(exc.value)


def test_a_missing_heading_is_refused():
    with pytest.raises(SurfaceContractError) as exc:
        surface_table_cells("# Doc\n\nno surface section here\n")
    assert "occurs 0 time(s)" in str(exc.value)


def test_a_heading_with_no_table_under_it_is_refused():
    with pytest.raises(SurfaceContractError) as exc:
        surface_table_cells(f"# Doc\n\n{STABLE_SURFACE_HEADING}\n\nprose only\n")
    assert "no table follows" in str(exc.value)


def test_a_table_with_no_data_rows_is_refused():
    document = _replace_once(
        _MINIMAL, "| `radar taxonomy` | the closed vocabularies |\n", "")
    with pytest.raises(SurfaceContractError) as exc:
        surface_table_cells(document)
    assert "at least one data row" in str(exc.value)


def test_a_row_narrower_than_the_header_is_refused():
    """A stray pipe must fail loudly, not silently shift which cell is read."""
    document = _replace_once(
        _MINIMAL, "| `radar taxonomy` | the closed vocabularies |",
        "| `radar taxonomy` |")
    with pytest.raises(SurfaceContractError) as exc:
        surface_table_cells(document)
    assert "has 1 cell(s), but the header row has 2" in str(exc.value)


def test_an_unreadable_document_is_reported_rather_than_read_as_agreement():
    """`surface_violations` must never turn a failed parse into an empty list."""
    assert surface_violations("# Doc\n\nnothing here\n") != []


#: The shipped Promise cell of the `radar taxonomy` row, held ONCE so the two
#: known-bad fixtures below cannot drift apart from each other. `_replace_once`
#: asserts `count(old) == 1`, so a stale value fails loudly rather than quietly
#: proving nothing -- but two independently retyped copies could still disagree,
#: and only one of them would be the row the document actually carries.
TAXONOMY_PROMISE = (
    "the closed vocabularies -- layers, gap types, the evidence ladder with its "
    "weights, and record statuses. Sizes are deliberately not restated in this cell: "
    "a hand-maintained count of a machine-published vocabulary decays silently and "
    "then misleads with authority")


# --- the comparison, both directions ----------------------------------------

def test_the_shipped_document_agrees_with_the_parser():
    assert surface_violations(contract_text()) == []


def test_an_omitted_flag_is_reported():
    document = _replace_once(contract_text(), "`radar report [<repo>] [--floor N]`",
                             "`radar report [<repo>]`")
    assert surface_violations(document) == ["report: missing ['--floor'], unexpected []"]


def test_an_invented_flag_is_reported():
    document = _replace_once(contract_text(), "`radar report [<repo>] [--floor N]`",
                             "`radar report [<repo>] [--floor N] [--strict]`")
    assert surface_violations(document) == [
        "report: missing [], unexpected ['--strict']"]


def test_a_missing_verb_row_is_reported():
    document = _replace_once(
        contract_text(), "| `radar taxonomy` | "
                         + TAXONOMY_PROMISE + " |\n", "")
    assert surface_violations(document) == [
        "verb set: missing ['taxonomy'], unexpected []"]


def test_a_duplicated_verb_row_is_reported_because_set_equality_cannot_see_it():
    row = "| `radar taxonomy` | " + TAXONOMY_PROMISE + " |"
    document = _replace_once(contract_text(), row + "\n", row + "\n" + row + "\n")
    # The two counts are DERIVED from the parser, not restated. Written as literals
    # ("8 row(s) for 7 verb(s)") this assertion was a closed-set census over the live
    # document, so shipping any new verb reddened it while the check under test was
    # working perfectly -- the same shape as the live-register id censuses iteration 09
    # had to convert, one level up. The discriminating clause stays literal: if
    # duplication went undetected the list would be empty and this still fails.
    verbs = len(parser_surface())
    assert surface_violations(document) == [
        f"verb set: {verbs + 1} row(s) for {verbs} verb(s); duplicated ['taxonomy']"]
# --- the same table reader, pointed at a second heading -----------------------
#
# The contract now publishes record-shape tables under `###` headings, read by COLUMN
# NAME rather than by cell 0. These tests exist because an optional parameter is the
# easiest thing in this file to accept and then ignore: a reader that took `heading`
# and still resolved `STABLE_SURFACE_HEADING` internally would pass every pre-existing
# test in this module, since every one of them uses the default.

_KEYED = "\n".join([
    "# Doc",
    "",
    "### Gap record keys",
    "",
    "| Key | Required | Type |",
    "|---|---|---|",
    "| `id` | yes | string |",
    "| `tags` | no | list of strings |",
    "",
    "prose after the table",
    "",
])


def test_the_reader_reads_the_table_under_the_heading_it_is_given():
    table = gfm_table(_KEYED, "### Gap record keys")
    assert table.header == ("Key", "Required", "Type")
    assert table.column("Key") == ("`id`", "`tags`")
    assert table.column("Required") == ("yes", "no")


def test_the_heading_argument_is_used_rather_than_the_default():
    """The control that arms the test above.

    `_KEYED` carries no stable-surface heading, so a reader ignoring its argument
    refuses this document instead of reading it -- and the refusal has to NAME the
    heading it was handed, or the parameter is decoration.
    """
    with pytest.raises(SurfaceContractError) as exc:
        gfm_table(_KEYED)
    assert repr(STABLE_SURFACE_HEADING) in str(exc.value)
    assert "occurs 0 time(s)" in str(exc.value)


def test_a_named_column_the_header_does_not_carry_is_refused():
    with pytest.raises(SurfaceContractError) as exc:
        gfm_table(_KEYED, "### Gap record keys").column("Model")
    assert "0 column(s) headed 'Model'" in str(exc.value)


def test_two_columns_with_the_same_heading_are_refused_not_silently_resolved():
    """A stale duplicate column would answer for the live one, undetected.

    Taking the first match is the fail-open here: cell 1 and cell 2 can disagree --
    one correct, one left behind by a half-finished edit -- with every assertion
    about "the Required column" still passing.
    """
    document = _replace_once(
        _KEYED, "| Key | Required | Type |", "| Key | Required | Required |")
    with pytest.raises(SurfaceContractError) as exc:
        gfm_table(document, "### Gap record keys").column("Required")
    assert "2 column(s) headed 'Required'" in str(exc.value)


def test_a_ragged_row_is_refused_under_a_non_default_heading_too():
    document = _replace_once(_KEYED, "| `tags` | no | list of strings |", "| `tags` | no |")
    with pytest.raises(SurfaceContractError) as exc:
        gfm_table(document, "### Gap record keys")
    assert "has 2 cell(s), but the header row has 3" in str(exc.value)


def test_a_table_with_no_data_rows_is_refused_under_a_non_default_heading_too():
    """Zero rows must raise, not hand back an empty set for a caller to compare."""
    document = _KEYED
    for row in ("| `id` | yes | string |\n", "| `tags` | no | list of strings |\n"):
        document = _replace_once(document, row, "")
    with pytest.raises(SurfaceContractError) as exc:
        gfm_table(document, "### Gap record keys")
    assert "at least one data row" in str(exc.value)


def test_the_cell_zero_reader_delegates_to_the_one_table_parser():
    """One parser, two callers: the point of the parameter, asserted on real bytes.

    If `surface_table_cells` grew its own copy of the row walk, these two lists could
    drift apart while both looked right in isolation -- which is the duplicated
    invariant this repo has already paid three times to remove.
    """
    document = contract_text()
    assert surface_table_cells(document) == [
        row[0] for row in gfm_table(document).rows]


# --- the defaults reader ------------------------------------------------------
#
# The SEAMS only, per the scope note above: that the parser side skips what it must and
# fails closed when it would otherwise hand back an empty expectation, that the document
# side refuses a shape it cannot trust, and that the comparison reports a difference in
# BOTH directions. Which defaults the shipped CLI actually has, and which rows the
# shipped document must carry, are the behavior module's assertions.

#: A minimal well-formed defaults section, used to plant structural defects. Deliberately
#: NOT derived from the real table: a synthetic document can be made ill-shaped in ways
#: the tracked one must never be.
_MINIMAL_DEFAULTS = "\n".join([
    "# Doc",
    "",
    DEFAULTS_HEADING,
    "",
    "| " + " | ".join(DEFAULTS_COLUMNS) + " |",
    "|---|---|---|",
    "| `probe` | `--floor` | `2` |",
    "",
    "trailing prose",
    "",
])


def _one_verb_parser(*arguments: tuple[tuple[str, ...], dict[str, object]]):
    """A `radar`-shaped parser with one `probe` verb carrying `arguments`.

    Built here rather than shared with the real CLI because every fail-closed path below
    -- a verb that defaults nothing, a default that cannot be published -- is a parser
    the shipped CLI must never be, so it can only be shown against a synthetic one.
    """
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="command")
    probe = sub.add_parser("probe")
    for names, options in arguments:
        probe.add_argument(*names, **options)
    return parser


def test_parser_defaults_fails_closed_when_no_subcommands_are_registered():
    """The shared lookup: one fail-closed message, not two copies of it."""
    with pytest.raises(SurfaceContractError) as exc:
        parser_defaults(argparse.ArgumentParser(prog="radar"))
    assert "no subcommands" in str(exc.value)


def test_parser_defaults_fails_closed_when_nothing_carries_a_default():
    """An empty expectation would let the table say anything and still pass."""
    parser = _one_verb_parser((("target",), {}), (("--json",), {"action": "store_true"}))
    with pytest.raises(SurfaceContractError) as exc:
        parser_defaults(parser)
    assert "no value-bearing default" in str(exc.value)


def test_a_zero_argument_flag_is_not_published_as_a_default():
    """`store_true` defaults to off, which the surface table's `[--json]` already says."""
    defaults = parser_defaults()
    assert defaults, "the real CLI defaults nothing"
    assert not [entry for entry in defaults if entry.argument == "--json"]


def test_the_help_option_argparse_adds_for_itself_is_not_published():
    for entry in parser_defaults():
        assert entry.argument not in {"-h", "--help"}, entry


def test_an_argument_is_named_by_its_longest_spelling_alphabetically_broken():
    """Not the first-registered spelling: that is registration-order luck, not a name."""
    parser = _one_verb_parser((("--bbb", "--aaa", "-b"), {"default": "x"}))
    assert {entry.argument for entry in parser_defaults(parser)} == {"--aaa"}


def test_a_positional_is_named_by_its_dest_because_it_has_no_typed_name():
    parser = _one_verb_parser((("path",), {"nargs": "?", "default": "."}))
    assert parser_defaults(parser) == frozenset({ArgumentDefault("probe", "path", ".")})


def test_a_default_that_renders_blank_is_refused_rather_than_published():
    """A blank cell would compare equal to another blank cell for the wrong reason."""
    parser = _one_verb_parser((("--label",), {"default": "  "}))
    with pytest.raises(SurfaceContractError) as exc:
        parser_defaults(parser)
    assert "blank" in str(exc.value)


def test_a_default_carrying_a_pipe_is_refused_because_the_row_would_break():
    parser = _one_verb_parser((("--label",), {"default": "a|b"}))
    with pytest.raises(SurfaceContractError) as exc:
        parser_defaults(parser)
    assert "'|'" in str(exc.value)


def test_the_documented_header_is_compared_whole_so_a_fourth_column_is_refused():
    """Resolving three columns by name would pass a table carrying a fourth.

    A fourth column is where a second, unread opinion about a default would live.
    """
    document = _replace_once(
        _MINIMAL_DEFAULTS,
        "| Verb | Argument | Default |\n|---|---|---|\n| `probe` | `--floor` | `2` |",
        "| Verb | Argument | Default | Note |\n|---|---|---|---|\n"
        "| `probe` | `--floor` | `2` | ignored |")
    with pytest.raises(SurfaceContractError) as exc:
        documented_defaults(document)
    assert "expected exactly ['Verb', 'Argument', 'Default']" in str(exc.value)


def test_a_renamed_column_is_refused_rather_than_read_by_position():
    document = _replace_once(_MINIMAL_DEFAULTS, "| Argument |", "| Flag |")
    with pytest.raises(SurfaceContractError):
        documented_defaults(document)


def test_a_cell_that_is_not_a_single_backticked_value_is_refused():
    """`.` is a value only a code span can tell from a full stop."""
    document = _replace_once(_MINIMAL_DEFAULTS, "| `2` |", "| `2` (see below) |")
    with pytest.raises(SurfaceContractError) as exc:
        documented_defaults(document)
    assert "not a single backticked value" in str(exc.value)


def test_the_rows_are_returned_in_document_order_so_a_duplicate_stays_visible():
    document = _replace_once(
        _MINIMAL_DEFAULTS, "| `probe` | `--floor` | `2` |",
        "| `probe` | `--floor` | `2` |\n| `probe` | `--floor` | `2` |")
    assert documented_defaults(document) == (
        ArgumentDefault("probe", "--floor", "2"),
        ArgumentDefault("probe", "--floor", "2"))


def test_an_unreadable_defaults_table_is_reported_rather_than_raised():
    """One call site can then assert "no disagreements" over a planted shape defect."""
    problems = defaults_violations(_replace_once(_MINIMAL_DEFAULTS, DEFAULTS_HEADING,
                                                 "## Something else"))
    assert len(problems) == 1 and "occurs 0 time(s)" in problems[0], problems


def test_the_shipped_document_agrees_with_the_parser_about_every_default():
    assert defaults_violations(contract_text()) == []


def test_the_published_scan_floor_is_the_constant_scoring_defaults_to():
    """The table publishes the PARSER's `2`; this joins that value to `scoring`'s own.

    `cli.py:502-506` hand-copies the literal instead of reading
    `scoring.CONFIDENCE_FLOOR_DEFAULT`, deliberately -- the module's IMPORT INVARIANT
    keeps `scoring` out of `build_parser()`, which runs on every refusal, `--help` and
    `--version` path -- and that comment says outright that "The two are not asserted
    equal by a reader". A TEST is free to import both: the invariant governs what
    `build_parser()` pulls in at parse time, not what a reader may join afterwards. So
    the drift that comment leaves to a byte comparison is asserted here instead, on the
    DOCUMENTED value, which is the one a consumer reads.
    """
    from agent_gap_radar.scoring import CONFIDENCE_FLOOR_DEFAULT

    row = ArgumentDefault("scan", "--floor", str(CONFIDENCE_FLOOR_DEFAULT))
    assert row in documented_defaults(contract_text()), (
        f"the published `scan --floor` default is not {CONFIDENCE_FLOOR_DEFAULT!r}")
    assert row in parser_defaults(), "the parser's own default drifted from the constant"


def test_a_default_the_parser_fills_in_and_no_row_names_is_reported():
    document = contract_text()
    dropped = _replace_once(document, "| `scan` | `--floor` | `2` |\n", "")
    problems = defaults_violations(dropped)
    assert problems, "an omitted default passed the reader"
    assert any("scan --floor=2" in p and "no row says so" in p for p in problems), problems


def test_a_row_for_a_default_the_parser_does_not_carry_is_reported():
    document = contract_text()
    invented = _replace_once(document, "| `validate` | `path` | `.` |",
                             "| `validate` | `path` | `.` |\n| `taxonomy` | `--deep` | `9` |")
    problems = defaults_violations(invented)
    assert problems, "an invented default passed the reader"
    assert any("taxonomy --deep=9" in p and "which the parser does not" in p
               for p in problems), problems


def test_a_documented_value_that_disagrees_is_reported_on_both_sides():
    """A wrong VALUE is a missing triple AND a surplus one; both halves must say so."""
    document = contract_text()
    wrong = _replace_once(document, "| `scan` | `--floor` | `2` |",
                          "| `scan` | `--floor` | `0` |")
    problems = defaults_violations(wrong)
    assert any("scan --floor=2" in p and "no row says so" in p for p in problems), problems
    assert any("scan --floor=0" in p and "which the parser does not" in p
               for p in problems), problems


def test_a_duplicated_row_is_reported_because_set_equality_cannot_see_it():
    """Two rows for one argument can disagree, with one stale, and both sets still match."""
    document = contract_text()
    doubled = _replace_once(document, "| `show` | `path` | `.` |",
                            "| `show` | `path` | `.` |\n| `show` | `path` | `.` |")
    problems = defaults_violations(doubled)
    assert any("duplicated ['show path']" in p for p in problems), problems
