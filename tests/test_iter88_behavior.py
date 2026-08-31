"""Iteration 88 behaviors: the consumer contract's stable-surface table stops demanding
four argument tokens the CLI makes OPTIONAL, and its derivation from `build_parser()`
grows a REQUIREDNESS rule that is two-sided in BOTH directions.

Black-box, and the ISOLATION CONTRACT IS HONORED: no module under `src/` or `tools/` was
read to derive any expectation here, and neither the engineer's notes, the reviewer's
notes, any `IMPLEMENTATION.patch` nor any diff was opened. Every expectation comes from
`pm.md`'s Expected Behaviors. Everything is measured by CALLING a public interface -- the
`tests/_surface_contract.py` oracle that iterations 10, 11 and 30 already publish to test
modules, `agent_gap_radar.cli.build_parser`, `agent_gap_radar.cli.main` -- or by reading a
PUBLISHED document.

Structural notes, so this file cannot lie later:

* **Behavior 1 is asserted twice, from two independent derivations.** The literal mapping
  in `REQUIRED_BY_VERB` is transcribed from `pm.md`, not read out of the oracle, so a
  reader that silently returned nothing fails it. `test_b1_the_rule_is_re_derived...`
  then recomputes the same mapping straight off `build_parser()` with argparse
  introspection, so the pair still holds when a verb is added and disagrees loudly if the
  oracle's rule and the stated rule ever drift apart.
* **Behaviors 4-6 are the two-sided proof, and behavior 7 arms them.** Every known-bad is
  built in memory by `_replace_once`, which asserts `text.count(old) == 1` -- the habit
  `tests/test_surface_contract_unit.py:43` already enforces -- so a rewrite that silently
  matched nothing cannot masquerade as a proof. `test_b7_...` additionally asserts each
  mutated text DIFFERS from the committed text, and that the guard itself fires on a
  stale anchor.
* **Behavior 6 must use a SYNTHETIC surface and that is a feature, not a shortcut.** No
  shipped option is required, so the option half of the rule is undemonstrable against
  `build_parser()`; `test_b6_the_surface_argument_is_read_rather_than_defaulted` is the
  control that arms it, passing a surface which DISAGREES with the real parser about the
  shipped document and requiring the answer to follow the argument.
* **Honest limit on behavior 3.** A black-box test cannot compare today's document
  against its pre-change bytes, so "the other five cells are byte-identical to their
  pre-change form" is asserted here as "the five cells read exactly these literals". Two
  of the eight literals (`scan`, `taxonomy`) are cross-checked against pins committed by
  earlier iterations in other test modules; the rest are not independently pinned
  anywhere, and the before/after comparison belongs to the reviewer and the final gate.
* **The published arity sentence gets a RUNTIME probe.** The rule under test is a pure
  function over text and can only compare brackets against argparse ARITY, which is a
  different claim from the sentence the document publishes ("the CLI accepts the run
  WITHOUT `x`"). `test_the_published_bracket_promise_holds_when_the_cli_is_actually_run`
  settles the published sentence by running all eight bracketings.
* **Whitespace normalisation is declared where it is used.** The contract is hard-wrapped
  prose, so the arity-paragraph assertions collapse runs of whitespace on BOTH sides
  before comparing, and say so at the call site.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib

import pytest

from _surface_contract import (STABLE_SURFACE_HEADING, VerbSurface, contract_text,
                               parser_surface, requiredness_violations,
                               surface_table_cells, surface_violations)
from agent_gap_radar.cli import build_parser, main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Behavior 1 -- every argument the shipped parser REQUIRES, transcribed from `pm.md`'s
#: Expected Behavior 1 rather than read back out of the oracle. Options would appear here
#: by their option strings; none is required today, which is why behavior 6 exists.
REQUIRED_BY_VERB = {
    "validate": [],
    "list": [],
    "report": [],
    "show": ["gap_id"],
    "prd": [],
    "scan": ["target"],
    "diff": ["new", "old"],
    "taxonomy": [],
}

#: Behavior 3 -- the eight invocation cells the corrected document must carry, in the
#: order the stable-surface table lists them. The first, fourth and fifth are the three
#: cells this iteration corrects; the other five are the untouched rows.
EXPECTED_CELLS = [
    "`radar validate [<repo>]`",
    "`radar list [<repo>] [--json] [--floor N] [--layer L]`",
    "`radar show <ID> [<repo>]`",
    "`radar report [<repo>] [--floor N]`",
    "`radar prd [<repo>] [--gap <ID>] [--project NAME]`",
    "`radar scan <target> [--gaps R] [--json] [--prd] [--exit-code]`",
    "`radar diff <old> <new> [--json]`",
    "`radar taxonomy`",
]

#: Behavior 3 -- the drifted spellings, quoted from `pm.md`'s measurement table. Each
#: demanded a token the parser makes optional; none may survive anywhere in the document.
DRIFTED_SPELLINGS = [
    "`radar validate <repo>`",
    "`radar report <repo> [--floor N]`",
    "`radar prd <repo> --gap <ID> [--project NAME]`",
]


def _replace_once(text: str, old: str, new: str) -> str:
    """Mutate in memory, asserting the target is unambiguous.

    Behavior 7. A silent zero-replacement is how a known-bad becomes a second copy of
    the known-good, and then a two-sided test proves nothing while still passing. Same
    shape as `tests/test_surface_contract_unit.py::_replace_once`, restated here rather
    than imported so this module's proof does not depend on another module's private
    helper keeping its assertion.
    """
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} time(s)"
    return text.replace(old, new)


def _synthetic_document(cell: str) -> str:
    """A minimal well-formed stable-surface section carrying exactly one invocation."""
    return "\n".join([
        "# Doc",
        "",
        STABLE_SURFACE_HEADING,
        "",
        "| Verb | Promise |",
        "|---|---|",
        f"| {cell} | a promise |",
        "",
        "trailing prose",
        "",
    ])


def _collapse(text: str) -> str:
    """Whitespace-collapsed text. Declared because the contract is hard-wrapped prose."""
    return " ".join(text.split())


# --- behavior 1: the requiredness reader is derived from the parser --------------

def test_b1_the_parser_reports_exactly_this_required_argument_mapping():
    """The whole mapping, explicitly -- a reader returning nothing cannot pass this."""
    surface = parser_surface()
    assert {verb: sorted(vs.required) for verb, vs in surface.items()} == REQUIRED_BY_VERB


def test_b1_three_verbs_really_do_require_something():
    """Anti-vacuity for the assertion above: the mapping is not empty everywhere.

    Without this, an oracle whose `required` was always `frozenset()` would agree with a
    `REQUIRED_BY_VERB` that had been transcribed wrong in the same direction.
    """
    surface = parser_surface()
    assert sorted(verb for verb, vs in surface.items() if vs.required) == [
        "diff", "scan", "show"]
    assert sum(len(vs.required) for vs in surface.values()) == 4


def test_b1_the_rule_is_re_derived_independently_off_build_parser():
    """The same rule computed here with argparse introspection, not read from the oracle.

    `pm.md` states the rule as `action.required` for options and `nargs not in ("?", "*")`
    for positionals. Recomputing it makes the pair of assertions survive a new verb, and
    makes a disagreement between the stated rule and the oracle's rule loud.
    """
    parser = build_parser()
    subparsers = next(action for action in parser._actions
                      if isinstance(action, argparse._SubParsersAction))
    recomputed: dict[str, list[str]] = {}
    for verb, subparser in subparsers.choices.items():
        required: list[str] = []
        for action in subparser._actions:
            if not action.option_strings:
                if action.nargs not in ("?", "*"):
                    required.append(action.dest)
            elif action.required and not (
                    set(action.option_strings) & {"-h", "--help"}):
                required.extend(action.option_strings)
        recomputed[verb] = sorted(required)
    assert recomputed == REQUIRED_BY_VERB
    assert {verb: sorted(vs.required) for verb, vs in parser_surface().items()} == recomputed


def test_b1_positionals_are_named_so_a_verdict_can_be_checked_against_the_parser():
    """Requiredness by index needs the dest names, or a message cannot be audited."""
    surface = parser_surface()
    named = {verb: vs.positional_dests for verb, vs in surface.items()}
    assert named == {
        "validate": ("path",), "list": ("path",), "report": ("path",),
        "show": ("gap_id", "path"), "prd": ("path",), "scan": ("target",),
        "diff": ("old", "new"), "taxonomy": (),
    }
    for verb, vs in surface.items():
        assert len(vs.positional_dests) == vs.positionals, verb


def _synthetic_parser(*, required: bool) -> argparse.ArgumentParser:
    """A parser with a subcommand whose option requiredness is under the test's control.

    `parser_surface()` takes its parser as an argument, which is the only way to exercise
    the OPTION half of behavior 1's stated rule (`action.required`): no shipped verb has a
    required option, so that branch of the READER is unobservable through `build_parser()`
    and would keep every other assertion in this module green if it were deleted. Measured
    -- planting exactly that deletion left all 30 of this module's other tests passing.
    """
    parser = argparse.ArgumentParser(prog="radar")
    subparsers = parser.add_subparsers(dest="command")
    demo = subparsers.add_parser("demo")
    demo.add_argument("-f", "--flag", required=required)
    demo.add_argument("--switch", action="store_true")
    demo.add_argument("target")
    demo.add_argument("path", nargs="?", default=".")
    return parser


def test_b1_option_requiredness_is_read_from_the_parser_and_not_assumed_absent():
    """Behavior 1's option branch, and EVERY spelling of the required option answers.

    A cell may document either `-f` or `--flag`; both must be judged required, or the
    verdict depends on which spelling an editor happened to write.
    """
    surface = parser_surface(_synthetic_parser(required=True))["demo"]
    assert surface.required == frozenset({"-f", "--flag", "target"})
    assert "--switch" not in surface.required
    assert "path" not in surface.required


def test_b1_an_option_the_parser_does_not_require_is_absent_from_required():
    """The control that arms the test above: only `required=` on the option differs."""
    surface = parser_surface(_synthetic_parser(required=False))["demo"]
    assert surface.required == frozenset({"target"})


# --- behavior 2: the shipped contract reports zero requiredness violations -------

def test_b2_the_shipped_contract_reports_zero_requiredness_violations():
    assert requiredness_violations(parser_surface(), contract_text()) == []


def test_b2_the_iteration_30_surface_rule_still_reports_zero_too():
    """Non-regression: correcting the brackets must not disturb the older derivation.

    `surface_violations()` compares flag NAMES, option arity and POSITIONAL COUNTS, and
    bracketing changes none of the three -- so this staying empty is what shows the
    correction was confined to notation.
    """
    assert surface_violations(contract_text()) == []


def test_b2_an_unreadable_document_is_a_violation_rather_than_agreement():
    """Behavior 2 reads an empty list as agreement, so a failed parse must not return one."""
    violations = requiredness_violations(parser_surface(), "# Doc\n\nnothing here\n")
    assert violations != []
    assert "occurs 0 time(s)" in violations[0]


# --- behavior 3: exactly the three drifted cells are corrected -------------------

def test_b3_the_document_carries_exactly_these_eight_invocation_cells_in_order():
    assert surface_table_cells(contract_text()) == EXPECTED_CELLS


def test_b3_no_drifted_spelling_survives_anywhere_in_the_document():
    document = contract_text()
    assert [spelling for spelling in DRIFTED_SPELLINGS
            if spelling in document] == []


def test_b3_each_corrected_cell_is_present_exactly_once():
    """Once, not at least once: a second copy is a stale row answering for the live one."""
    document = contract_text()
    for cell in EXPECTED_CELLS[:-1]:
        assert document.count(cell) == 1, cell
    # `radar taxonomy` is a substring of the longer prose references to the verb, so it
    # is counted as a whole table row instead.
    assert document.count("| `radar taxonomy` |") == 1


def test_b3_two_untouched_cells_match_pins_committed_by_earlier_iterations():
    """Cross-check against literals this iteration did not write.

    Only `scan` and `taxonomy` are independently pinned under `tests/`, so only those two
    of the five untouched rows can be corroborated from outside this module. The honest
    limit is stated in the module docstring: a before/after byte comparison is the
    reviewer's and the final gate's, not a black-box test's.
    """
    scan_cell = "`radar scan <target> [--gaps R] [--json] [--prd] [--exit-code]`"
    assert scan_cell in EXPECTED_CELLS
    pinned = (REPO_ROOT / "tests" / "test_surface_contract_unit.py").read_text(
        encoding="utf-8")
    assert pinned.count(scan_cell) == 1
    assert "`radar taxonomy`" in EXPECTED_CELLS
    assert (REPO_ROOT / "tests" / "test_iter71_behavior.py").read_text(
        encoding="utf-8").count("`radar taxonomy`") > 0


# --- behavior 4: direction A -- optional documented as REQUIRED is refused -------

@pytest.mark.parametrize("verb, old, new", [
    ("validate", "`radar validate [<repo>]`", "`radar validate <repo>`"),
    ("report", "`radar report [<repo>] [--floor N]`",
     "`radar report <repo> [--floor N]`"),
    ("prd", "`radar prd [<repo>] [--gap <ID>] [--project NAME]`",
     "`radar prd [<repo>] --gap <ID> [--project NAME]`"),
])
def test_b4_an_optional_argument_documented_as_required_is_refused(verb, old, new):
    document = _replace_once(contract_text(), old, new)
    violations = requiredness_violations(parser_surface(), document)
    assert len(violations) == 1, violations
    assert violations[0].startswith(f"{verb}: "), violations
    assert "as required, parser makes it optional" in violations[0], violations


def test_b4_the_gap_flag_cell_is_the_one_that_costs_a_consumer_something():
    """The `--gap` half of the `prd` row, named as an OPTION rather than a positional.

    `pm.md` singles this cell out: `radar prd` with no `--gap` selects the top-ranked gap
    and `README.md` documents exactly that, so a contract demanding the flag sends a
    consumer looking for a gap id it never needed. The message must name the flag, or an
    editor cannot tell which of the row's three tokens to unbracket.
    """
    document = _replace_once(
        contract_text(), "`radar prd [<repo>] [--gap <ID>] [--project NAME]`",
        "`radar prd [<repo>] --gap <ID> [--project NAME]`")
    violations = requiredness_violations(parser_surface(), document)
    assert violations == [
        "prd: documents '--gap' as required, parser makes it optional"]


# --- behavior 5: direction B -- required documented as OPTIONAL is refused -------

@pytest.mark.parametrize("verb, old, new", [
    ("scan", "`radar scan <target> [--gaps R] [--json] [--prd] [--exit-code]`",
     "`radar scan [<target>] [--gaps R] [--json] [--prd] [--exit-code]`"),
    ("show", "`radar show <ID> [<repo>]`", "`radar show [<ID>] [<repo>]`"),
])
def test_b5_a_required_argument_documented_as_optional_is_refused(verb, old, new):
    document = _replace_once(contract_text(), old, new)
    violations = requiredness_violations(parser_surface(), document)
    assert len(violations) == 1, violations
    assert violations[0].startswith(f"{verb}: "), violations
    assert "as optional, parser makes it required" in violations[0], violations


def test_b5_the_message_names_both_the_documented_token_and_the_parser_dest():
    """The documented spelling is what an editor changes; the dest is what makes the
    verdict checkable against the parser. Naming only one of the two is not actionable."""
    document = _replace_once(contract_text(), "`radar show <ID> [<repo>]`",
                             "`radar show [<ID>] [<repo>]`")
    violations = requiredness_violations(parser_surface(), document)
    assert len(violations) == 1, violations
    assert "'<ID>'" in violations[0]
    assert "gap_id" in violations[0]


def test_b5_this_direction_now_holds_for_a_row_iteration_11_never_checked():
    """`tests/test_iter11_behavior.py` covers direction B for the `diff` row alone.

    `show` is a row that older assertion could not see, so its refusal here is the part
    of behavior 5 that is genuinely new rather than already covered.
    """
    document = _replace_once(contract_text(), "`radar show <ID> [<repo>]`",
                             "`radar show [<ID>] [<repo>]`")
    assert requiredness_violations(parser_surface(), document) != []
    untouched = "`radar diff <old> <new> [--json]`"
    assert document.count(untouched) == 1


# --- behavior 6: option requiredness is READ, not assumed absent -----------------

def _synthetic_surface(*, required: bool) -> dict[str, VerbSurface]:
    """One verb, one valueless option, requiredness under the test's control."""
    return {"demo": VerbSurface(
        options=frozenset({"--flag"}),
        positionals=0,
        takes_value={"--flag": False},
        required=frozenset({"--flag"}) if required else frozenset(),
        positional_dests=())}


def test_b6_a_required_option_documented_as_optional_is_refused():
    violations = requiredness_violations(
        _synthetic_surface(required=True), _synthetic_document("`radar demo [--flag]`"))
    assert len(violations) == 1, violations
    assert "--flag" in violations[0]
    assert violations[0].startswith("demo: ")
    assert "as optional, parser makes it required" in violations[0]


def test_b6_the_same_required_option_documented_unbracketed_is_accepted():
    """The control that arms the test above: only the bracketing differs."""
    assert requiredness_violations(
        _synthetic_surface(required=True),
        _synthetic_document("`radar demo --flag`")) == []


def test_b6_an_optional_option_documented_as_required_is_refused():
    """The option half of direction A, which no shipped row can demonstrate."""
    violations = requiredness_violations(
        _synthetic_surface(required=False), _synthetic_document("`radar demo --flag`"))
    assert len(violations) == 1, violations
    assert "--flag" in violations[0]
    assert "as required, parser makes it optional" in violations[0]


def test_b6_an_optional_option_documented_as_optional_is_accepted():
    assert requiredness_violations(
        _synthetic_surface(required=False),
        _synthetic_document("`radar demo [--flag]`")) == []


def test_b6_the_surface_argument_is_read_rather_than_defaulted():
    """The check must be a PURE function of its two arguments.

    A reader that took `surface` and still resolved `build_parser()` internally would
    pass every other assertion in this module, because every one of them passes the real
    surface. Here the SHIPPED document is judged against a surface that disagrees with
    the real parser -- `validate`'s `path` reported REQUIRED -- so the answer has to
    follow the argument, not the live CLI.
    """
    surface = dict(parser_surface())
    surface["validate"] = dataclasses.replace(
        surface["validate"], required=frozenset({"path"}))
    violations = requiredness_violations(surface, contract_text())
    assert len(violations) == 1, violations
    assert violations[0].startswith("validate: ")
    assert "as optional, parser makes it required" in violations[0]
    # And the real surface still agrees with the same document, so the difference above
    # came from the argument rather than from the document.
    assert requiredness_violations(parser_surface(), contract_text()) == []


def test_b6_an_unknown_verb_is_left_to_the_verb_set_rule():
    """One defect must not read as two: a verb the surface lacks is skipped here.

    `surface_violations()` already reports a verb-set difference, and a row reported by
    both rules would make a single missing row look like two problems.
    """
    document = _synthetic_document("`radar nosuchverb [--flag]`")
    assert requiredness_violations(_synthetic_surface(required=True), document) == []


# --- behavior 7: every planted defect actually changes the document --------------

def test_b7_every_planted_known_bad_differs_from_the_committed_document():
    committed = contract_text()
    plants = [
        ("`radar validate [<repo>]`", "`radar validate <repo>`"),
        ("`radar report [<repo>] [--floor N]`", "`radar report <repo> [--floor N]`"),
        ("`radar prd [<repo>] [--gap <ID>] [--project NAME]`",
         "`radar prd [<repo>] --gap <ID> [--project NAME]`"),
        ("`radar scan <target> [--gaps R] [--json] [--prd] [--exit-code]`",
         "`radar scan [<target>] [--gaps R] [--json] [--prd] [--exit-code]`"),
        ("`radar show <ID> [<repo>]`", "`radar show [<ID>] [<repo>]`"),
    ]
    for old, new in plants:
        assert committed.count(old) == 1, old
        mutated = _replace_once(committed, old, new)
        assert mutated != committed, old
        assert mutated.count(new) == 1, new
        assert old not in mutated, old


def test_b7_the_synthetic_plants_change_their_document_too():
    """Behaviors 4-5 mutate the real contract; behavior 6 builds two cells from scratch.

    Both synthetic cells must differ from each other, or the two-sided option proof is
    one document compared with itself.
    """
    bracketed = _synthetic_document("`radar demo [--flag]`")
    bare = _synthetic_document("`radar demo --flag`")
    assert bracketed != bare
    assert surface_table_cells(bracketed) == ["`radar demo [--flag]`"]
    assert surface_table_cells(bare) == ["`radar demo --flag`"]


def test_b7_the_mutation_guard_refuses_a_stale_anchor():
    """The guard that arms every plant above, shown firing.

    A `_replace_once` whose assertion never fails is decoration, and a stale anchor is
    exactly how a "known-bad" silently becomes a second copy of the known-good.
    """
    with pytest.raises(AssertionError) as exc:
        _replace_once(contract_text(), "`radar validate <repo>`", "anything")
    assert "occurs 0 time(s)" in str(exc.value)
    with pytest.raises(AssertionError) as exc:
        _replace_once("aa", "a", "b")
    assert "occurs 2 time(s)" in str(exc.value)


# --- the published notation: what the document promises, run ---------------------

def test_the_contract_states_once_that_the_bracketing_is_arity_and_not_advice():
    """Acceptance criterion: the notation is pinned as ARITY, in exactly one place.

    Compared on whitespace-COLLAPSED text on both sides, because the contract is
    hard-wrapped prose and the sentence spans three source lines.
    """
    document = _collapse(contract_text())
    assert document.count(
        "`[x]` means the CLI accepts the run WITHOUT `x` and `<x>` means it refuses "
        "without it") == 1
    assert document.count("The brackets are that argument's ARITY as `build_parser()` "
                          "reports it") == 1
    assert document.count("never advice") == 1
    for token in ("`action.required` for an option", "`nargs` for a positional"):
        assert document.count(token) == 1, token


def test_the_published_bracket_promise_holds_when_the_cli_is_actually_run(monkeypatch,
                                                                         capsys):
    """The runtime probe the pure rule cannot make.

    `requiredness_violations()` compares brackets against argparse ARITY. The sentence
    the document publishes is stronger -- that the run SUCCEEDS without a bracketed
    argument and is REFUSED without an unbracketed one -- and only running it settles
    that. Offline: every invocation reads the tracked register from the repo root.
    """
    monkeypatch.chdir(REPO_ROOT)
    for argv in (["validate"], ["report"], ["prd"], ["prd", "--project", "demo"]):
        assert main(argv) == 0, argv
        assert capsys.readouterr().out.strip(), argv
    for argv in (["show"], ["scan"], ["diff"], ["diff", "gaps"]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2, argv
        assert "the following arguments are required" in capsys.readouterr().err, argv
