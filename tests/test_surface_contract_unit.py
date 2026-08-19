"""Unit tests for the seams of `tests/_surface_contract.py`.

SCOPE. This file tests the ORACLE's helpers: the parser introspector, the table
parser, and the invocation tokenizer. The six specified behaviors of iteration 10 --
including the four planted known-bads and the per-verb message assertions -- belong to
`tests/test_iter10_behavior.py`, which is the test engineer's file. This one exists so
that no helper ships unproven: a guard nobody watches fire is decoration, and a
document-oracle that has only ever been run against a passing document has never
demonstrated it can say no.

Every test builds its input in memory. Nothing here edits a file, runs a subprocess,
touches the network, or reads anything under `gaps/`, so a research pass writing
records cannot redden it.
"""

from __future__ import annotations

import argparse

import pytest

from _surface_contract import (STABLE_SURFACE_HEADING, DocumentedInvocation,
                               SurfaceContractError, contract_text,
                               documented_invocation, gfm_table,
                               invocation_verb, parser_surface,
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
        "`radar scan <target> [--gaps R] [--json] [--prd]`",
        "`radar scan <target> [--gaps R] [--json]`")
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


# --- the comparison, both directions ----------------------------------------

def test_the_shipped_document_agrees_with_the_parser():
    assert surface_violations(contract_text()) == []


def test_an_omitted_flag_is_reported():
    document = _replace_once(contract_text(), "`radar report <repo> [--floor N]`",
                             "`radar report <repo>`")
    assert surface_violations(document) == ["report: missing ['--floor'], unexpected []"]


def test_an_invented_flag_is_reported():
    document = _replace_once(contract_text(), "`radar report <repo> [--floor N]`",
                             "`radar report <repo> [--floor N] [--strict]`")
    assert surface_violations(document) == [
        "report: missing [], unexpected ['--strict']"]


def test_a_missing_verb_row_is_reported():
    document = _replace_once(
        contract_text(), "| `radar taxonomy` | the closed vocabularies "
                         "(11 layers, 8 gap types, 9 evidence classes) |\n", "")
    assert surface_violations(document) == [
        "verb set: missing ['taxonomy'], unexpected []"]


def test_a_duplicated_verb_row_is_reported_because_set_equality_cannot_see_it():
    row = "| `radar taxonomy` | the closed vocabularies " \
          "(11 layers, 8 gap types, 9 evidence classes) |"
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
