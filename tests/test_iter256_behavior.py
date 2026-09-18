"""Iteration 256 behaviors: `docs/CONSUMER_CONTRACT.md` publishes the CLI's defaults.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads the implementation
source, the engineer's or reviewer's notes, or any diff. Every expectation comes from
`pm.md`'s Expected Behaviors. `docs/CONSUMER_CONTRACT.md` is read as the PUBLISHED
DOCUMENT those behaviors legislate over -- the same class of artifact as the README, not
implementation source -- and it is parsed through the reader committed under `tests/`.
Shapes were established by RUNNING the tool (`radar --help`, `radar <verb> --help`, and
the document verbs over hand-built fixture registers) and by reflection over the public
parser, never by reading a body.

Structural notes, so this file cannot lie later:

* **Every default is proved TWICE, once as text and once as behavior.** A table asserted
  set-equal to `build_parser()` is still only two readings of the same parser, so for
  each published value there is a run WITHOUT the flag compared byte-for-byte against the
  run that passes the published value explicitly -- and, as a vacuity guard, against a
  run that passes a DIFFERENT value, which must differ. That is what makes `2` and `.`
  and `agent-gap-radar` claims about the tool rather than about the reader.

* **Every planted defect starts from a pair the reader calls CLEAN.**
  `test_b0_the_minimal_pair_is_clean` asserts `defaults_violations(_MINIMAL, _synthetic
  ())` is empty, so when a mutation makes it non-empty the mutation is the reason. A
  structural test whose baseline was never green proves nothing.

* **Refusals are asserted as REPORTED violations, not as raises.** `defaults_violations`
  is documented to convert an unreadable table into a violation string, so asserting
  non-emptiness covers both spellings and does not pin which one a defect takes.

* **No absolute machine path and no personal identifier appears here.** Registers live
  under pytest's `tmp_path_factory`; the contract document is located by the committed
  reader. No test here scans this repository, so the module adds no scan-sized wall time.
"""

import argparse
import contextlib
import io

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _record, _write_register
from _surface_contract import (DEFAULTS_COLUMNS, DEFAULTS_HEADING, ArgumentDefault,
                              SurfaceContractError, contract_text, defaults_violations,
                              documented_defaults, gfm_table, parser_defaults)

#: Every (verb, argument, default) triple this iteration MEASURED out of the shipped
#: parser (`parser_defaults()` over `build_parser()`, run at iteration 256). Written as a
#: literal on purpose: set-equality between the document and the parser stays green if
#: BOTH sides drift together, and this is the third opinion that catches that. A CLI that
#: legitimately gains an eleventh default updates this row, the document, and nothing else.
EXPECTED_DEFAULTS = frozenset({
    ArgumentDefault("list", "--floor", "2"),
    ArgumentDefault("list", "path", "."),
    ArgumentDefault("prd", "--project", "agent-gap-radar"),
    ArgumentDefault("prd", "path", "."),
    ArgumentDefault("report", "--floor", "2"),
    ArgumentDefault("report", "path", "."),
    ArgumentDefault("scan", "--floor", "2"),
    ArgumentDefault("scan", "--gaps", "."),
    ArgumentDefault("show", "path", "."),
    ArgumentDefault("validate", "path", "."),
})

#: The one row every structural fixture below is built from, and the header it must carry.
_HEADER_ROW = "| Verb | Argument | Default |"
_SEPARATOR_ROW = "|---|---|---|"
_MINIMAL_ROW = "| `list` | `--floor` | `2` |"

#: A minimal well-formed document, used to plant structural defects without disturbing
#: the shipped ten-row table. Paired with `_synthetic()`, whose only default is this row.
_MINIMAL = (
    "# Consumer contract\n"
    "\n"
    "## Exit codes\n"
    "\n"
    "prose that belongs to another section\n"
    "\n"
    f"{DEFAULTS_HEADING}\n"
    "\n"
    f"{_HEADER_ROW}\n"
    f"{_SEPARATOR_ROW}\n"
    f"{_MINIMAL_ROW}\n"
    "\n"
    "## After\n"
    "\n"
    "tail prose\n"
)

#: Two records with derived confidence 5 and 0, so the published floor of `2` is a
#: threshold that actually partitions the fixture register.
FIXTURE_RECORDS = [
    _record("GAP-256", 5, 5, 5, ("first-party-field",)),   # confidence 5
    _record("GAP-257", 4, 4, 4, ("model-output",)),        # confidence 0
]


def _run(argv):
    """Drive the public CLI entry point and capture stdout / stderr / exit code."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _synthetic(*specs):
    """A parser carrying exactly the (verb, option, default) triples asked for.

    Injectable synthetics are the only way to reach the reader's PARSER side without
    touching the shipped CLI, which behavior 6 forbids moving.
    """
    if not specs:
        specs = (("list", "--floor", "2"),)
    parser = argparse.ArgumentParser(prog="radar")
    subs = parser.add_subparsers(dest="verb")
    made = {}
    for verb, option, default in specs:
        sub = made.get(verb) or subs.add_parser(verb)
        made[verb] = sub
        sub.add_argument(option, default=default)
    return parser


def _replace_once(text, old, new):
    """`old` -> `new`, refusing unless `old` occurs exactly once."""
    assert text.count(old) == 1, f"fixture anchor {old!r} occurs {text.count(old)} times"
    return text.replace(old, new)


@pytest.fixture(scope="module")
def register(tmp_path_factory):
    """One fixture register, built once for the whole module."""
    root = tmp_path_factory.mktemp("iter256")
    return _write_register(root / "reg", FIXTURE_RECORDS)


# ---------------------------------------------------------------------------
# Behavior 0 (guards, not spec behaviors) -- the fixtures are not vacuous.
# ---------------------------------------------------------------------------

def test_b0_the_parser_carries_exactly_the_ten_measured_defaults():
    """Every set-equality below is meaningless if the parser side is not these ten."""
    measured = parser_defaults()
    assert len(measured) == 10, f"parser reports {len(measured)} defaults, expected 10"
    assert measured == EXPECTED_DEFAULTS, (
        f"parser side moved: missing {sorted(e.label for e in EXPECTED_DEFAULTS - measured)}, "
        f"unexpected {sorted(e.label for e in measured - EXPECTED_DEFAULTS)}")


def test_b0_the_minimal_pair_is_clean():
    """Every planted defect below must be the ONLY reason its assertion moves."""
    assert defaults_violations(_MINIMAL, _synthetic()) == []


# ---------------------------------------------------------------------------
# Behavior 1 -- exactly one `## Defaults` heading.
# ---------------------------------------------------------------------------

def test_b1_the_contract_publishes_exactly_one_defaults_heading():
    headings = [line for line in contract_text().splitlines()
                if line.strip() == DEFAULTS_HEADING]
    assert len(headings) == 1, f"expected one {DEFAULTS_HEADING!r} heading, got {headings}"


def test_b1_a_second_defaults_heading_is_refused():
    """Two sections cannot both be the contract: one of them would go unread."""
    doubled = _MINIMAL + f"\n{DEFAULTS_HEADING}\n\n{_HEADER_ROW}\n{_SEPARATOR_ROW}\n{_MINIMAL_ROW}\n"
    assert defaults_violations(doubled, _synthetic()) != []


def test_b1_a_missing_defaults_heading_is_refused():
    removed = _replace_once(_MINIMAL, DEFAULTS_HEADING, "## Something else")
    assert defaults_violations(removed, _synthetic()) != []
    with pytest.raises(SurfaceContractError):
        documented_defaults(removed)


# ---------------------------------------------------------------------------
# Behavior 2 -- immediately under it, a table headed Verb | Argument | Default.
# ---------------------------------------------------------------------------

def test_b2_the_shipped_table_header_is_exactly_verb_argument_default():
    assert gfm_table(contract_text(), DEFAULTS_HEADING).header == DEFAULTS_COLUMNS


def test_b2_the_shipped_table_sits_immediately_under_the_heading():
    """The first non-blank line after the heading is the header row, then the separator."""
    lines = contract_text().splitlines()
    at = lines.index(DEFAULTS_HEADING)
    after = [line for line in lines[at + 1:] if line.strip()]
    assert after[0].strip() == _HEADER_ROW, f"line after the heading is {after[0]!r}"
    assert set(after[1].strip()) <= set("|-: "), f"no separator row: {after[1]!r}"
    assert after[2].strip().startswith("|"), "the first data row does not follow"


def test_b2_prose_between_the_heading_and_the_table_is_refused():
    """Prose is enough to hide the table a reader that scanned forward would find."""
    pushed = _replace_once(_MINIMAL, f"{DEFAULTS_HEADING}\n\n{_HEADER_ROW}",
                           f"{DEFAULTS_HEADING}\n\nan explanatory sentence\n\n{_HEADER_ROW}")
    assert defaults_violations(pushed, _synthetic()) != []


@pytest.mark.parametrize("header", [
    "| Verb | Arg | Default |",             # renamed cell
    "| Argument | Verb | Default |",        # reordered -- would swap every triple
    "| Verb | Argument | Value |",          # renamed value column
    "| Verb | Argument |",                  # a column short
])
def test_b2_a_header_that_is_not_the_three_named_columns_is_refused(header):
    assert defaults_violations(_replace_once(_MINIMAL, _HEADER_ROW, header),
                               _synthetic()) != []


def test_b2_a_fourth_column_is_refused():
    """A fourth column is where a second, unread opinion about a default would live."""
    widened = _replace_once(_MINIMAL, f"{_HEADER_ROW}\n{_SEPARATOR_ROW}\n{_MINIMAL_ROW}",
                            "| Verb | Argument | Default | Note |\n"
                            "|---|---|---|---|\n"
                            "| `list` | `--floor` | `2` | `see below` |")
    assert defaults_violations(widened, _synthetic()) != []


def test_b2_a_table_with_no_data_rows_is_refused():
    empty = _replace_once(_MINIMAL, f"{_SEPARATOR_ROW}\n{_MINIMAL_ROW}", _SEPARATOR_ROW)
    assert defaults_violations(empty, _synthetic()) != []


@pytest.mark.parametrize("row", [
    "| list | --floor | 2 |",                     # no code spans at all
    "| `list` | `--floor` | `2` (see below) |",    # prose beside the value
    "| `list` | `--floor` |  |",                   # blank value cell
    "| `list` | `--floor` | `2` `3` |",            # two values in one cell
])
def test_b2_a_cell_that_is_not_a_single_backticked_value_is_refused(row):
    assert defaults_violations(_replace_once(_MINIMAL, _MINIMAL_ROW, row),
                               _synthetic()) != []


# ---------------------------------------------------------------------------
# Behavior 3 -- the documented triples EQUAL what `build_parser()` reports.
# ---------------------------------------------------------------------------

def test_b3_the_shipped_document_and_the_real_parser_agree():
    assert defaults_violations(contract_text()) == []


def test_b3_both_sides_equal_the_ten_measured_triples():
    documented = documented_defaults(contract_text())
    assert set(documented) == EXPECTED_DEFAULTS
    assert parser_defaults() == EXPECTED_DEFAULTS
    assert len(documented) == 10, f"{len(documented)} rows, expected 10"
    assert len(set(documented)) == len(documented), "a row is duplicated"


def test_b3_the_published_rows_are_sorted_by_verb_then_argument():
    """The document publishes this rule, so a new default has exactly one right place."""
    keys = [(entry.verb, entry.argument) for entry in documented_defaults(contract_text())]
    assert keys == sorted(keys)


def test_b3_the_floor_column_publishes_the_floor_a_flagless_run_meets(register):
    """`2` is the value an invocation WITHOUT `--floor` actually applies."""
    published = {entry.default for entry in EXPECTED_DEFAULTS
                 if entry.argument == "--floor"}
    assert published == {"2"}, f"the floor rows publish {published}"
    for verb in ("list", "report"):
        bare = _run([verb, str(register)])
        same = _run([verb, str(register), "--floor", "2"])
        other = _run([verb, str(register), "--floor", "6"])
        assert bare[0] == 0 and bare[2] == "" and len(bare[1]) > 40
        assert same == bare, f"{verb}: inserting the published default moved bytes"
        assert other != bare, f"{verb}: --floor is ignored, so the row proves nothing"


def test_b3_the_path_column_publishes_the_directory_a_flagless_run_reads(register,
                                                                        monkeypatch):
    """`.` is the cwd: omitting the positional is the same run as passing the cwd."""
    argv_for = {"list": ["list"], "report": ["report"], "validate": ["validate"],
                "show": ["show", "GAP-256"], "prd": ["prd"]}
    monkeypatch.chdir(register)
    for verb, argv in argv_for.items():
        bare = _run(argv)
        explicit = _run([*argv, str(register)])
        assert bare[0] == 0, f"{verb} exited {bare[0]}: {bare[2]!r}"
        assert bare == explicit, f"{verb}: the cwd is not the published `.` default"


def test_b3_the_project_column_publishes_the_project_a_flagless_prd_carries(register):
    """`agent-gap-radar` is what `prd` fills in when `--project` is omitted."""
    published = [entry.default for entry in EXPECTED_DEFAULTS
                 if entry.argument == "--project"]
    assert published == ["agent-gap-radar"]
    bare = _run(["prd", str(register)])
    same = _run(["prd", str(register), "--project", published[0]])
    other = _run(["prd", str(register), "--project", "some-other-project"])
    assert bare[0] == 0 and bare[2] == ""
    assert published[0] in bare[1], "the flagless payload never names the default project"
    assert same == bare, "passing the published default moved bytes"
    assert other != bare, "--project is ignored, so the row proves nothing"


def test_b3_the_gaps_column_publishes_the_register_a_flagless_scan_reads(register,
                                                                        monkeypatch,
                                                                        tmp_path):
    """`.` is the cwd for `scan --gaps` too."""
    target = tmp_path / "target"
    (target / "app").mkdir(parents=True)
    (target / "app" / "loop.py").write_text("pass\n", encoding="utf-8")
    explicit = _run(["scan", str(target), "--gaps", str(register)])
    monkeypatch.chdir(register)
    bare = _run(["scan", str(target)])
    assert explicit[0] == 0 and explicit[2] == ""
    assert bare == explicit, "the cwd is not the published `.` default for --gaps"


# ---------------------------------------------------------------------------
# Behavior 4 -- the reader fails on a documented default the parser does not carry.
# ---------------------------------------------------------------------------

def test_b4_a_row_for_an_argument_the_parser_does_not_carry_is_reported():
    invented = _replace_once(_MINIMAL, _MINIMAL_ROW,
                             f"{_MINIMAL_ROW}\n| `list` | `--nonexistent` | `7` |")
    problems = defaults_violations(invented, _synthetic())
    assert problems != []
    assert "list --nonexistent=7" in " ".join(problems), problems


def test_b4_a_row_for_a_verb_the_parser_does_not_have_is_reported():
    invented = _replace_once(_MINIMAL, _MINIMAL_ROW,
                             f"{_MINIMAL_ROW}\n| `taxonomy` | `--floor` | `2` |")
    problems = defaults_violations(invented, _synthetic())
    assert problems != []
    assert "taxonomy --floor=2" in " ".join(problems), problems


def test_b4_a_row_with_the_wrong_value_is_reported_from_both_sides():
    """A value the parser does not use is BOTH an unbacked claim and a missing row."""
    wrong = _replace_once(_MINIMAL, _MINIMAL_ROW, "| `list` | `--floor` | `3` |")
    problems = defaults_violations(wrong, _synthetic())
    joined = " ".join(problems)
    assert "list --floor=3" in joined, problems
    assert "list --floor=2" in joined, problems


def test_b4_the_real_document_with_one_value_edited_is_reported():
    """The same rule over the SHIPPED table and the SHIPPED parser."""
    edited = _replace_once(contract_text(), "| `scan` | `--floor` | `2` |",
                           "| `scan` | `--floor` | `4` |")
    problems = defaults_violations(edited)
    assert "scan --floor=4" in " ".join(problems), problems
    assert "scan --floor=2" in " ".join(problems), problems


def test_b4_a_duplicated_row_is_reported_because_set_equality_cannot_see_it():
    doubled = _replace_once(_MINIMAL, _MINIMAL_ROW, f"{_MINIMAL_ROW}\n{_MINIMAL_ROW}")
    problems = defaults_violations(doubled, _synthetic())
    assert problems != [], "two rows for one argument passed the set comparison"
    assert "list --floor" in " ".join(problems), problems


# ---------------------------------------------------------------------------
# Behavior 5 -- the reader fails on a parser default the table omits.
# ---------------------------------------------------------------------------

def test_b5_a_parser_default_no_row_claims_is_reported():
    extra = _synthetic(("list", "--floor", "2"), ("list", "--other", "x"))
    problems = defaults_violations(_MINIMAL, extra)
    assert problems != []
    assert "list --other=x" in " ".join(problems), problems


def test_b5_a_verb_whose_defaults_are_undocumented_is_reported():
    extra = _synthetic(("list", "--floor", "2"), ("report", "--floor", "2"))
    problems = defaults_violations(_MINIMAL, extra)
    assert "report --floor=2" in " ".join(problems), problems


def test_b5_dropping_a_row_from_the_shipped_table_is_reported():
    dropped = _replace_once(contract_text(), "| `prd` | `--project` | `agent-gap-radar` |\n", "")
    problems = defaults_violations(dropped)
    assert "prd --project=agent-gap-radar" in " ".join(problems), problems


def test_b5_dropping_every_row_of_the_shipped_table_is_reported():
    text = contract_text()
    stripped = text
    for entry in documented_defaults(text):
        row = f"| `{entry.verb}` | `{entry.argument}` | `{entry.default}` |\n"
        stripped = _replace_once(stripped, row, "")
    assert defaults_violations(stripped) != [], "an empty table certified the parser"


def test_b5_one_call_reports_a_missing_row_and_a_surplus_row_together():
    """Two-sidedness is a property of ONE comparison, not of two tests."""
    swapped = _replace_once(_MINIMAL, _MINIMAL_ROW, "| `list` | `--other` | `x` |")
    problems = defaults_violations(swapped, _synthetic())
    joined = " ".join(problems)
    assert "list --floor=2" in joined, problems
    assert "list --other=x" in joined, problems
    assert len(problems) == 2, f"expected one message per direction, got {problems}"


# ---------------------------------------------------------------------------
# Behavior 6 -- `radar --help`, the document verbs and the goldens do not move.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    [], ["validate"], ["list"], ["report"], ["show"], ["prd"], ["scan"], ["diff"],
    ["taxonomy"],
])
def test_b6_help_is_deterministic_and_says_nothing_about_the_new_section(argv):
    """A doc-only iteration may not move a byte of any help text."""
    with pytest.raises(SystemExit) as first:
        _run([*argv, "--help"])
    assert first.value.code == 0
    once = _run_help([*argv, "--help"])
    twice = _run_help([*argv, "--help"])
    assert once == twice, "help output is not deterministic"
    assert once and once.endswith("\n")
    assert DEFAULTS_HEADING not in once


def _run_help(argv):
    """`--help` exits, so capture its stdout around the SystemExit."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        main(list(argv))
    return out.getvalue()


@pytest.mark.parametrize("argv", [
    ["validate"], ["list"], ["report"], ["show", "GAP-256"], ["prd"],
])
def test_b6_every_document_verb_still_ends_in_exactly_one_newline(register, argv):
    code, out, err = _run([*argv, str(register)])
    assert code == 0, f"{argv} exited {code}: {err!r}"
    assert err == "", f"{argv} wrote to stderr: {err!r}"
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-20:])
    assert DEFAULTS_HEADING not in out, "the new doc section leaked into a document"
