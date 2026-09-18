"""Iteration 255 behaviors: `radar scan --floor N` hands the confidence floor to the caller.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads the implementation
source, the engineer's or reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors. Shapes were established by RUNNING
the tool (`radar scan --help`, `scan --json/--prd/--exit-code` over hand-built fixture
registers) and by reflection over the public interface, never by reading a body.
`docs/CONSUMER_CONTRACT.md` is read as the PUBLISHED DOCUMENT behavior 8 legislates over
-- the same class of artifact as the README, not implementation source -- and it is
parsed through the oracle already committed at `tests/_surface_contract.py`.

Structural notes, so this file cannot lie later:

* **Every floor claim is paired with its flagless or `--floor 2` twin.** A test that only
  ran the flagged form could pass against a `scan` that ignored `--floor` entirely, and a
  byte-equality claim measured across two test functions is not a claim about one
  invocation pair. Behaviors 1, 3 and 4 each compare the flagged bytes against the bytes
  of the SAME invocation without the flag, inside one test.

* **The confidence of every fixture record is DERIVED and then ASSERTED, never assumed.**
  `_confidence_by_gap()` reads the confidence the tool itself published for each record
  out of the `--json` payload, and `test_b0_...` pins that the four fixture registers
  really do carry confidences 0, 1, 3 and 5. Nothing in this module hardcodes the
  evidence ladder's rungs: if `secondary-summary` stopped scoring 1, that guard fails
  loudly instead of turning the floor sweeps into assertions about nothing.

* **The sweeps are guarded against vacuity.** Behavior 2 asserts the `below_floor` flags
  really do move across the sweep (all false at `--floor 0`, all true at `--floor 6`), so
  a payload that hardcoded `false` cannot satisfy the iff. Behavior 3 asserts the document
  is non-empty and that all four records are present in `findings` at every floor.
  Behavior 4 asserts both a `1` case and a `0` case exist for the middle confidences.

* **No new whole-repo scan.** Every register and target here is a two-file fixture tree
  built once per module under `tmp_path_factory`; no test scans this repository, so this
  module adds no ~30s scan-equivalent to the suite wall (PM acceptance criterion 8).

* **No absolute machine path and no personal identifier appears here.** Targets and
  registers live under pytest's `tmp_path_factory`; the contract document is located by
  the committed oracle.

TWO SPEC READINGS, also carried in the tester report:

1. Behavior 3 says the `findings` array keeps "the same `id` values". The published
   payload names that key `gap_id` (there is no `id` key on a finding), so `gap_id` is
   what is compared -- and the absence of `id` is asserted, so the reading is forced
   rather than assumed.
2. Behavior 7 says `--floor 0` and `--floor 6` are "ACCEPTED (no `Error: ` line about the
   value)". `--prd --floor 6` still legitimately refuses per behavior 6, so the reading
   tested is: no error about the VALUE -- the only `Error: ` permitted at floor 6 is the
   existing no-PRESENT-finding-clears sentence, and it must name 6.
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from agent_gap_radar import cli
from agent_gap_radar.cli import main
from test_iter02_behavior import _record, _target, _write_register
from _surface_contract import (contract_text, documented_tokens, invocation_verb,
                              parser_surface, surface_table_cells,
                              surface_violations)

#: The floor the register applies when `--floor` is omitted. Spelled once; behavior 1
#: is the test that this is the value `--floor` has to reproduce byte-for-byte.
DEFAULT_FLOOR = 2

#: Every floor the spec sweeps. 0 is cleared by everything and 6 is unclearable by
#: construction, because confidence is derived on 0..5.
FLOORS = (0, 1, 2, 3, 4, 5, 6)

#: Evidence classes whose derived confidence this module needs. The mapping is a
#: FIXTURE CHOICE, not an assertion: `test_b0_fixture_confidences_are_what_the_tool_
#: derives` proves the tool agrees before any sweep leans on it.
CLASS_FOR_CONFIDENCE = {
    0: "model-output",
    1: "secondary-summary",
    3: "survey-aggregate",
    5: "first-party-field",
}

#: Four PRESENT findings spanning confidence 0, 1, 3 and 5. GAP-552 (confidence 1) has
#: the HIGHEST priority, so it is the record the floor takes away from `--prd` at the
#: default and hands back at `--floor 1` -- behavior 5's register is this one.
MIX = [
    _record("GAP-551", 5, 3, 5, ("first-party-field",), "CHK-551"),    # p 8.7  c5
    _record("GAP-552", 5, 5, 5, ("secondary-summary",), "CHK-552"),    # p 10.0 c1
    _record("GAP-553", 4, 4, 4, ("survey-aggregate",), "CHK-553"),     # p 8.0  c3
    _record("GAP-554", 3, 3, 3, ("model-output",), "CHK-554"),         # p 6.0  c0
]

#: One PRESENT finding per confidence, for the `--exit-code` sweep of behavior 4.
SOLO = {
    c: [_record(f"GAP-56{c}", 4, 4, 4, (klass,), f"CHK-56{c}")]
    for c, klass in CLASS_FOR_CONFIDENCE.items()
}


def _run(argv):
    """Drive the public CLI entry point and capture stdout / stderr / exit code.

    `contextlib.redirect_*` rather than `capsys`, because the sweeps below are computed
    once in module-scoped fixtures and `capsys` is function-scoped.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    """One target tree and five registers, built once for the whole module."""
    root = tmp_path_factory.mktemp("iter255")
    return {
        "target": _target(root / "hit"),
        "mix": _write_register(root / "mix", MIX),
        "solo": {c: _write_register(root / f"solo{c}", recs)
                 for c, recs in SOLO.items()},
    }


def _scan(bed, *extra, register="mix"):
    reg = bed["mix"] if register == "mix" else bed["solo"][register]
    return _run(["scan", str(bed["target"]), "--gaps", str(reg), *extra])


@pytest.fixture(scope="module")
def md_sweep(bed):
    """The markdown document with no `--floor`, and at every floor 0..6."""
    sweep = {None: _scan(bed)}
    sweep.update({n: _scan(bed, "--floor", str(n)) for n in FLOORS})
    return sweep


@pytest.fixture(scope="module")
def json_sweep(bed):
    """The `--json` payload with no `--floor`, and at every floor 0..6."""
    sweep = {None: _scan(bed, "--json")}
    sweep.update({n: _scan(bed, "--json", "--floor", str(n)) for n in FLOORS})
    return sweep


def _payload(json_sweep, floor):
    return json.loads(json_sweep[floor][1])


def _confidence_by_gap(json_sweep, floor=DEFAULT_FLOOR):
    """What confidence the TOOL published for each record of the MIX register."""
    return {f["gap_id"]: f["confidence"] for f in _payload(json_sweep, floor)["findings"]}


# ---------------------------------------------------------------------------
# Behavior 0 (guard, not a spec behavior) -- the fixtures really span the ladder.
# ---------------------------------------------------------------------------

def test_b0_fixture_confidences_are_what_the_tool_derives(bed, json_sweep):
    """Every sweep below is meaningless if the fixture confidences are not 0/1/3/5."""
    derived = _confidence_by_gap(json_sweep)
    assert derived == {"GAP-551": 5, "GAP-552": 1, "GAP-553": 3, "GAP-554": 0}
    for c in CLASS_FOR_CONFIDENCE:
        rc, out, err = _scan(bed, "--json", register=c)
        assert rc == 0 and err == ""
        findings = json.loads(out)["findings"]
        assert [f["confidence"] for f in findings] == [c], (
            f"the solo register for confidence {c} did not derive {c}")
        assert [f["verdict"] for f in findings] == ["PRESENT"], (
            "the solo fixture must be PRESENT or behavior 4 tests nothing")


# ---------------------------------------------------------------------------
# Behavior 1 -- `--floor 2` is accepted and the default is byte-preserved.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [(), ("--json",), ("--prd",), ("--exit-code",)])
def test_b1_inserting_the_default_floor_changes_no_byte(bed, extra):
    """Behavior 1: all four invocations are byte-identical with `--floor 2` inserted."""
    bare_rc, bare_out, bare_err = _scan(bed, *extra)
    flag_rc, flag_out, flag_err = _scan(bed, *extra, "--floor", str(DEFAULT_FLOOR))
    assert flag_out == bare_out, f"stdout moved for {extra}"
    assert flag_err == bare_err, f"stderr moved for {extra}"
    assert flag_rc == bare_rc, f"exit code moved for {extra}"
    # Vacuity guard: an invocation that printed nothing would satisfy the above.
    assert len(bare_out) > 100, f"{extra} produced no document to compare"
    assert bare_out.endswith("\n") and not bare_out.endswith("\n\n")


def test_b1_the_flag_position_does_not_matter(bed):
    """`--floor` before the verb-shaping flag is the same run as after it."""
    before = _scan(bed, "--floor", "4", "--json")
    after = _scan(bed, "--json", "--floor", "4")
    assert before == after


# ---------------------------------------------------------------------------
# Behavior 2 -- `--json` publishes the floor it was given and derives below_floor.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", FLOORS)
def test_b2_json_publishes_the_given_floor_and_derives_below_floor(json_sweep, floor):
    """Behavior 2: `confidence_floor == N`, and `below_floor` iff `confidence < N`."""
    rc, out, err = json_sweep[floor]
    assert rc == 0 and err == ""
    payload = json.loads(out)
    assert payload["confidence_floor"] == floor
    assert payload["findings"], "an empty findings array makes the iff vacuous"
    for finding in payload["findings"]:
        assert finding["below_floor"] is (finding["confidence"] < floor), (
            f"{finding['gap_id']} confidence {finding['confidence']} at floor {floor}")


def test_b2_the_below_floor_flags_actually_move_across_the_sweep(json_sweep):
    """A payload hardcoding `below_floor` could satisfy the iff at one floor only."""
    at_zero = [f["below_floor"] for f in _payload(json_sweep, 0)["findings"]]
    at_six = [f["below_floor"] for f in _payload(json_sweep, 6)["findings"]]
    assert at_zero == [False] * len(at_zero) and at_zero
    assert at_six == [True] * len(at_six) and at_six


def test_b2_the_omitted_flag_publishes_the_register_default(json_sweep):
    """The floor the payload names without `--floor` is the one `--floor 2` names."""
    assert _payload(json_sweep, None)["confidence_floor"] == DEFAULT_FLOOR
    assert json_sweep[None] == json_sweep[DEFAULT_FLOOR]


# ---------------------------------------------------------------------------
# Behavior 3 -- the floor gates verdicts, never the domain.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", FLOORS)
def test_b3_the_markdown_document_is_floor_independent(md_sweep, floor):
    """Behavior 3: the report is byte-identical at every floor."""
    rc, out, err = md_sweep[floor]
    base_rc, base_out, base_err = md_sweep[DEFAULT_FLOOR]
    assert out == base_out, f"the document moved at floor {floor}"
    assert (rc, err) == (base_rc, base_err)
    assert len(base_out) > 100 and base_out.endswith("\n")


@pytest.mark.parametrize("floor", FLOORS)
def test_b3_the_findings_domain_is_floor_independent(json_sweep, floor):
    """Behavior 3: no record is added or dropped, and the order never moves."""
    base = _payload(json_sweep, DEFAULT_FLOOR)["findings"]
    here = _payload(json_sweep, floor)["findings"]
    assert len(here) == len(base) == len(MIX)
    assert [f["gap_id"] for f in here] == [f["gap_id"] for f in base]
    assert [f["confidence"] for f in here] == [f["confidence"] for f in base]
    # Spec reading 1: the payload names this key `gap_id`, never `id`.
    assert all("id" not in f for f in here)


def test_b3_a_below_floor_record_is_displayed_and_flagged_never_dropped(json_sweep):
    """The core invariant's never-silently-drop half, at the strictest floor."""
    at_six = _payload(json_sweep, 6)["findings"]
    assert {f["gap_id"] for f in at_six} == {r["id"] for r in MIX}
    assert all(f["below_floor"] for f in at_six)


# ---------------------------------------------------------------------------
# Behavior 4 -- `--exit-code` moves with the floor.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence", sorted(CLASS_FOR_CONFIDENCE))
@pytest.mark.parametrize("floor", FLOORS)
def test_b4_exit_code_verdict_tracks_the_floor(bed, floor, confidence):
    """Behavior 4: `1` when `N <= C`, `0` when `N > C`, document byte-identical."""
    doc_rc, doc_out, doc_err = _scan(bed, register=confidence)
    rc, out, err = _scan(bed, "--exit-code", "--floor", str(floor),
                         register=confidence)
    expected = 1 if floor <= confidence else 0
    assert rc == expected, (
        f"confidence {confidence} at floor {floor} verdicted {rc}, wanted {expected}")
    assert type(rc) is int, "a bool exit status is indistinguishable from 1 at a shell"
    assert rc in cli.EXIT_CODES
    assert out == doc_out, "the verdict changed the document"
    assert err == "" and doc_err == ""
    assert doc_rc == 0


@pytest.mark.parametrize("confidence", sorted(CLASS_FOR_CONFIDENCE))
def test_b4_both_verdicts_are_reachable_for_every_fixture(bed, confidence):
    """Guard: a `--exit-code` that always returned 1 would pass half the sweep."""
    codes = {_scan(bed, "--exit-code", "--floor", str(n), register=confidence)[0]
             for n in FLOORS}
    assert codes == {0, 1}, (
        f"confidence {confidence} never crossed its own floor: {codes}")


# ---------------------------------------------------------------------------
# Behavior 5 -- `--prd` selection moves with the floor.
# ---------------------------------------------------------------------------

def _note(gap_id, priority, confidence, floor):
    return (f"Note: skipped {gap_id} (priority {priority}, confidence {confidence}) "
            f"-- below the confidence floor {floor}.\n")


def test_b5_prd_at_the_default_floor_skips_the_top_record_and_says_so(bed, json_sweep):
    """Behavior 5: `--prd --floor 2` builds the confidence-5 record, naming the skip."""
    rc, out, err = _scan(bed, "--prd", "--floor", "2")
    assert rc == 0
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == "GAP-551"
    assert doc["sourceGap"]["confidence"] == 5
    priority = {f["gap_id"]: f["priority"] for f in _payload(json_sweep, 2)["findings"]}
    assert err == _note("GAP-552", priority["GAP-552"], 1, 2)


def test_b5_prd_at_floor_1_builds_the_confidence_1_record_and_stays_silent(bed):
    """Behavior 5: `--floor 1` hands the higher-priority record back, with no Note."""
    rc, out, err = _scan(bed, "--prd", "--floor", "1")
    assert rc == 0
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == "GAP-552"
    assert doc["sourceGap"]["confidence"] == 1
    assert err == "", "nothing was passed over, so nothing may be announced"


def test_b5_the_two_floors_select_different_records(bed):
    """The pair, in one test: the floor is what moved the selection."""
    at_two = json.loads(_scan(bed, "--prd", "--floor", "2")[1])["sourceGap"]["id"]
    at_one = json.loads(_scan(bed, "--prd", "--floor", "1")[1])["sourceGap"]["id"]
    assert (at_one, at_two) == ("GAP-552", "GAP-551")


# ---------------------------------------------------------------------------
# Behavior 6 -- a `--prd` refusal names the floor actually applied.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", (2, 3, 4, 5, 6))
def test_b6_the_prd_refusal_names_the_floor_it_applied(bed, floor):
    """Behavior 6: exit 2, empty stdout, one `Error: ` line naming N -- never 2."""
    rc, out, err = _scan(bed, "--prd", "--floor", str(floor), register=1)
    assert rc == 2
    assert out == ""
    assert err.splitlines() == [line.rstrip("\n") for line in err.splitlines()]
    assert len(err.splitlines()) == 1, f"stderr was not exactly one line: {err!r}"
    assert err.endswith("\n") and not err.endswith("\n\n")
    assert err.startswith(
        f"Error: no PRESENT finding clears the confidence floor {floor}: ")
    assert "GAP-561" in err


def test_b6_the_refusal_message_is_the_existing_sentence_at_the_default(bed):
    """No new refusal dialect: `--floor 2` reproduces today's flagless refusal."""
    flagless = _scan(bed, "--prd", register=1)
    flagged = _scan(bed, "--prd", "--floor", "2", register=1)
    assert flagged == flagless
    assert flagless[0] == 2 and flagless[1] == ""


@pytest.mark.parametrize("floor", (3, 4, 5))
def test_b6_a_note_line_in_the_same_run_also_names_the_applied_floor(bed, floor):
    """Behavior 6's second half: the `Note:` line carries N, not the default."""
    rc, out, err = _scan(bed, "--prd", "--floor", str(floor))
    assert rc == 0
    assert json.loads(out)["sourceGap"]["id"] == "GAP-551"
    assert err.count("\n") == 1
    assert err.endswith(f"-- below the confidence floor {floor}.\n"), err
    assert "GAP-552" in err


# ---------------------------------------------------------------------------
# Behavior 7 -- no new refusal dialect.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", (0, 6))
@pytest.mark.parametrize("extra", [(), ("--json",), ("--exit-code",)])
def test_b7_the_extreme_floors_are_accepted(bed, floor, extra):
    """Behavior 7: `--floor 0` and `--floor 6` produce no `Error: ` about the value."""
    rc, out, err = _scan(bed, *extra, "--floor", str(floor))
    assert err == ""
    assert rc in cli.EXIT_CODES and type(rc) is int
    assert len(out) > 100 and out.endswith("\n")


@pytest.mark.parametrize("floor", (0, 1))
def test_b7_prd_at_a_clearable_extreme_floor_is_accepted(bed, floor):
    """`--prd --floor 0` and `--floor 1` select rather than refuse."""
    rc, out, err = _scan(bed, "--prd", "--floor", str(floor))
    assert rc == 0 and "Error: " not in err
    assert json.loads(out)["sourceGap"]["id"] == "GAP-552"


def test_b7_prd_at_floor_6_refuses_only_with_the_existing_sentence(bed):
    """Spec reading 2: at floor 6 the only permitted `Error: ` is behavior 6's."""
    rc, out, err = _scan(bed, "--prd", "--floor", "6")
    assert rc == 2 and out == ""
    assert err.startswith("Error: no PRESENT finding clears the confidence floor 6: ")
    assert len(err.splitlines()) == 1


def test_b7_a_non_integer_floor_refuses_exactly_as_list_does(bed):
    """Behavior 7: `scan --floor abc` is argparse's refusal, same shape as `list`."""
    with pytest.raises(SystemExit) as scan_exit:
        _scan(bed, "--floor", "abc")
    scan_err = _capture_argparse_stderr(["scan", str(bed["target"]),
                                         "--gaps", str(bed["mix"]),
                                         "--floor", "abc"])
    with pytest.raises(SystemExit) as list_exit:
        _run(["list", str(bed["mix"]), "--floor", "abc"])
    list_err = _capture_argparse_stderr(["list", str(bed["mix"]), "--floor", "abc"])
    assert scan_exit.value.code == list_exit.value.code == 2
    assert scan_err.splitlines()[-1] == list_err.splitlines()[-1]
    assert (scan_err.splitlines()[-1]
            == "Error: argument --floor: invalid int value: 'abc'")
    assert scan_err.startswith("usage: radar scan ")
    assert list_err.startswith("usage: radar list ")


def _capture_argparse_stderr(argv):
    """The stderr of an invocation that exits through argparse."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit):
            main(list(argv))
    return err.getvalue()


def test_b7_scan_accepts_an_out_of_range_floor_exactly_as_list_does(bed):
    """No validation on `scan --floor` that `list --floor` does not have."""
    scan_rc, scan_out, scan_err = _scan(bed, "--floor", "99")
    list_rc, list_out, list_err = _run(["list", str(bed["mix"]), "--floor", "99"])
    assert (scan_rc, scan_err) == (0, "")
    assert (list_rc, list_err) == (0, "")
    assert scan_out and list_out


# ---------------------------------------------------------------------------
# Behavior 8 -- the published surface stays truthful.
# ---------------------------------------------------------------------------

def test_b8_the_contract_scan_row_names_the_floor_flag():
    """Behavior 8: the stable-surface invocation cell for `scan` spells `--floor N`."""
    cells = surface_table_cells(contract_text())
    scan_cells = [c for c in cells if invocation_verb(c) == "scan"]
    assert len(scan_cells) == 1, "exactly one stable-surface row documents `scan`"
    assert "[--floor N]" in scan_cells[0], scan_cells[0]
    assert "[--json] [--floor N]" in scan_cells[0], (
        "place `[--floor N]` beside `[--json]`, as the `list` row does")


def test_b8_the_set_equality_oracle_still_passes_over_the_whole_document():
    """An omitted flag AND an invented flag both fail; the document must agree exactly."""
    assert surface_violations(contract_text()) == []


def test_b8_the_documented_scan_tokens_carry_floor_as_an_optional_valued_option():
    """`--floor` is documented as one option with a value, bracketed optional."""
    surface = parser_surface()
    cell = next(c for c in surface_table_cells(contract_text())
                if invocation_verb(c) == "scan")
    tokens = documented_tokens(cell, surface["scan"].takes_value)
    floors = [t for t in tokens if t.name == "--floor"]
    assert len(floors) == 1, tokens
    assert floors[0].is_option and floors[0].optional
    assert "--floor" in surface["scan"].options
