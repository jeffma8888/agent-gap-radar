"""Iteration 125 behaviors: `radar prd` refuses to build against a gap the register
says is already done -- the default pick considers only citable statuses, and an
explicit `--gap` naming a terminal record is refused with exit 2 and one `Error: ` line.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, the
engineer's notes, the reviewer's notes, `fix_review.md`, `IMPLEMENTATION.patch`, or any
diff. Every assertion drives the public CLI entry point (`agent_gap_radar.cli.main`) and
reads the bytes it emitted on stdout / stderr plus its exit code, reads the PUBLISHED
`docs/CONSUMER_CONTRACT.md`, reads `gaps/*.json` as DATA through the tool's own `list
--json`, or reuses a fixture builder from `tests/`.

Structural notes, so this file cannot lie later:

* **No status literal drives a table.** Every per-status case is parametrized from
  `taxonomy.citable_statuses()` / `taxonomy.terminal_statuses()`, and behavior 5's
  expected vocabulary is rebuilt as "the members of `models.STATUSES`, in `STATUSES`
  order, that are citable". A future status lands here without an edit.
* **Every derived table owes a non-emptiness premise.** `test_premise_*` asserts the
  partition is exhaustive over `STATUSES`, disjoint, and that NEITHER side is empty --
  an empty side would make a parametrized table silently collect zero cases and read
  as green.
* **The patched-vocabulary probe keeps its register on ONE side of the partition.**
  Behavior 5's `TERMINAL_STATUSES = ("retired",)` case runs over an ALL-`retired`
  register. Patching that tuple over a register that also holds an `addressed` record
  turns that record citable, so the refusal branch is never reached and the probe
  measures nothing.
* **Non-regression is asserted TWO-SIDED where it can be.** Behaviors 4, 8 and 9
  compare two registers that differ in exactly one status string and require the
  emitted bytes to be identical after substituting that string, having first asserted
  the string occurs exactly once. A comparison that can only ever see a
  non-discriminating emitter is indistinguishable from one that cannot see
  discrimination at all.

DISCLOSURES, also carried in tester.md:

* Behaviors 2, 8 and 9 say "byte-identical to today". A test may not check out another
  commit, so the reachable in-test form is asserted here: the premise that makes the
  new filter the identity (the live register carries zero terminal records), the
  selection agreeing with the UNFILTERED ranking when no record is terminal, byte
  stability across repeated runs, and the substitution-identity pairs above. The
  cross-commit byte comparison is measured once, out of band, in tester.md.
* Behavior 8's spec text says `radar show <reg> --gap <id>`; `show` takes the id
  POSITIONALLY (`radar show <ID> [<path>]`, measured from `radar show --help`), so the
  positional form is what is tested. Noted for the PM as a spec-wording nit.
* No absolute machine path and no personal identifier appears here. The repo root is
  derived from `__file__`; every register and target is built under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main
from agent_gap_radar.models import STATUSES
from agent_gap_radar.taxonomy import citable_statuses, terminal_statuses
from test_iter02_behavior import MARKER, _record, _target, _write_register

#: The register default confidence floor (pinned by tests/test_iter02_behavior.py).
FLOOR = 2
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_REGISTER = REPO_ROOT / "gaps"
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The pre-iteration claim behavior 10 retires, verbatim from the shipped document.
RETIRED_SENTENCE = "the prd verb selects the same record whatever the status says"
SOURCE_GAP_HEADING = "### The sourceGap object"

#: Ids. `TOP` outranks `MID` outranks `LOW`; the ordering is ASSERTED from the tool's own
#: `list --json` priorities in `test_premise_the_fixture_ranking_is_what_this_file_assumes`,
#: never taken on faith from the scoring formula.
TOP_ID = "GAP-710"
MID_ID = "GAP-711"
LOW_ID = "GAP-712"

DEFAULT_STATUS = "open"
#: A citable status that is not the default (iteration 100 decided it IS citable).
OTHER_CITABLE = "partially-addressed"

#: Snapshotted at import because `pytest.mark.parametrize` needs its values at COLLECTION
#: time. The premise test below guards the snapshot.
CITABLE = citable_statuses()
TERMINAL = terminal_statuses()


def _expected_citable_phrase():
    """Behavior 5's vocabulary, DERIVED: citable members of `STATUSES` in `STATUSES` order.

    Read at CALL time so a `TERMINAL_STATUSES` patch is reflected, which is exactly what
    behavior 5's derived-not-literal clause asks to be proven.
    """
    citable = set(taxonomy.citable_statuses())
    return ", ".join(s for s in STATUSES if s in citable)


def _terminal_message(gid, status):
    return (f"Error: {gid} carries the terminal status '{status}'; the work is already "
            f"done, so no prd is emitted for it\n")


def _all_terminal_message():
    return ("Error: every gap record carries a terminal status; the citable statuses "
            f"are: {_expected_citable_phrase()}\n")


FLOOR_MESSAGE = "Error: no gap clears the confidence floor\n"


# --------------------------------------------------------------------------- fixtures

def _with_status(record, status):
    return {**record, "status": status}


_SEQ = {"n": 0}


def _reg(tmp_path, records):
    """A register under a FRESH subdirectory of `tmp_path` (`_write_register` mkdirs)."""
    _SEQ["n"] += 1
    return _write_register(tmp_path / f"r{_SEQ['n']}", list(records))


def _run(argv, capsys):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


#: The three-record spine. `check_id` is set so the same records also reach `scan`.
TOP = _record(TOP_ID, 5, 5, 5, ("first-party-field",), "CHK-710")
MID = _record(MID_ID, 4, 4, 4, ("first-party-field",), "CHK-711")
LOW = _record(LOW_ID, 3, 3, 3, ("first-party-field",), "CHK-712")

#: Below-floor twins: a lone `model-output` citation ceilings the DERIVED confidence at 0.
TOP_WEAK = _record(TOP_ID, 5, 5, 5, ("model-output",), "CHK-710")
MID_WEAK = _record(MID_ID, 4, 4, 4, ("model-output",), "CHK-711")


@pytest.fixture()
def target(tmp_path):
    """A target that trips the fixture checks, so the checked records are PRESENT."""
    return _target(tmp_path / "hit")


# --------------------------------------------------------------------------- premises

def test_premise_the_status_partition_is_what_this_file_assumes():
    """An empty side would make the parametrized tables below collect zero cases."""
    assert set(CITABLE) | set(TERMINAL) == set(STATUSES), STATUSES
    assert not set(CITABLE) & set(TERMINAL), (CITABLE, TERMINAL)
    assert CITABLE and TERMINAL, (CITABLE, TERMINAL)
    assert DEFAULT_STATUS in CITABLE, CITABLE
    assert OTHER_CITABLE in CITABLE, CITABLE
    assert len(CITABLE) >= 2, "behavior 4's citable pair needs two members"


def test_premise_the_fixture_ranking_is_what_this_file_assumes(tmp_path, capsys):
    """TOP really is the top-ranked record, measured by the tool, not by the formula."""
    reg = _reg(tmp_path, [TOP, MID, LOW])
    rc, out, err = _run(["list", str(reg), "--json"], capsys)
    assert rc == 0 and err == ""
    by_id = {r["gap_id"]: r for r in json.loads(out)["records"]}
    assert set(by_id) == {TOP_ID, MID_ID, LOW_ID}
    assert by_id[TOP_ID]["priority"] > by_id[MID_ID]["priority"] > by_id[LOW_ID]["priority"]
    for gid in (TOP_ID, MID_ID, LOW_ID):
        assert by_id[gid]["confidence"] >= FLOOR, (gid, by_id[gid])
        assert by_id[gid]["below_floor"] is False, gid


def test_premise_the_weak_records_are_below_floor(tmp_path, capsys):
    reg = _reg(tmp_path, [TOP_WEAK, MID_WEAK])
    rc, out, _err = _run(["list", str(reg), "--json"], capsys)
    assert rc == 0
    for rec in json.loads(out)["records"]:
        assert rec["confidence"] < FLOOR, rec
        assert rec["below_floor"] is True, rec


# ---------------------------------------------------------------------------
# Behavior 1 -- the default pick skips a terminal record and takes the top CITABLE one.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", TERMINAL)
def test_b1_the_top_ranked_record_being_terminal_does_not_make_it_the_selection(
        tmp_path, capsys, status):
    reg = _reg(tmp_path, [_with_status(TOP, status), MID, LOW])
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == MID_ID, (
        f"the top-ranked record is {status}; the pick must be the top CITABLE record")
    assert doc["sourceGap"]["id"] != TOP_ID
    assert doc["sourceGap"]["status"] in CITABLE, doc["sourceGap"]["status"]


@pytest.mark.parametrize("status", TERMINAL)
def test_b1_a_terminal_record_is_skipped_at_every_rank_not_only_the_top(
        tmp_path, capsys, status):
    """Two terminal records above the pick, so the filter is a DOMAIN filter."""
    reg = _reg(tmp_path, [_with_status(TOP, status), _with_status(MID, status), LOW])
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 0, err
    assert json.loads(out)["sourceGap"]["id"] == LOW_ID


def test_b1_with_no_terminal_record_the_pick_is_the_unfiltered_top_rank(
        tmp_path, capsys):
    """The filter is the IDENTITY when nothing is terminal -- behavior 2's mechanism."""
    reg = _reg(tmp_path, [TOP, MID, LOW])
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 0 and err == ""
    assert json.loads(out)["sourceGap"]["id"] == TOP_ID


# ---------------------------------------------------------------------------
# Behavior 2 -- no byte moves on a register that holds no terminal record.
# ---------------------------------------------------------------------------

def test_b2_the_live_register_holds_no_terminal_record(capsys):
    """The PREMISE that makes behavior 2 a consequence rather than a hope."""
    rc, out, _err = _run(["list", str(LIVE_REGISTER), "--json"], capsys)
    assert rc == 0
    records = json.loads(out)["records"]
    assert records, "premise: the live register must be non-empty"
    terminal = [r["gap_id"] for r in records if r["status"] in TERMINAL]
    assert terminal == [], f"the live register now carries terminal records: {terminal}"


@pytest.mark.parametrize("tail", [[], ["--project", "downstream-repo"]])
def test_b2_the_live_register_still_emits_a_prd_byte_stably(capsys, tail):
    argv = ["prd", str(REPO_ROOT)] + tail
    rc_a, out_a, err_a = _run(argv, capsys)
    rc_b, out_b, err_b = _run(argv, capsys)
    assert rc_a == 0 and rc_b == 0, err_a
    assert err_a == "" and err_b == ""
    assert out_a == out_b, "the document is not byte-stable across runs"
    assert out_a.endswith("\n") and not out_a.endswith("\n\n")
    assert json.loads(out_a)["sourceGap"]["status"] in CITABLE


# ---------------------------------------------------------------------------
# Behavior 3 -- `--gap` naming a terminal record: exit 2, one stderr line, no stdout.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", TERMINAL)
def test_b3_an_explicit_terminal_gap_is_refused_with_the_exact_line(
        tmp_path, capsys, status):
    reg = _reg(tmp_path, [_with_status(TOP, status), MID, LOW])
    rc, out, err = _run(["prd", str(reg), "--gap", TOP_ID], capsys)
    assert rc == 2, (rc, out, err)
    assert out == "", "stdout must carry only the document, and there is none"
    assert err == _terminal_message(TOP_ID, status)


@pytest.mark.parametrize("status", TERMINAL)
def test_b3_the_refusal_is_exactly_one_stderr_line(tmp_path, capsys, status):
    reg = _reg(tmp_path, [_with_status(MID, status), TOP, LOW])
    _rc, _out, err = _run(["prd", str(reg), "--gap", MID_ID], capsys)
    assert err.count("\n") == 1, repr(err)
    assert err.startswith("Error: ")
    assert err.endswith("\n") and not err.endswith("\n\n")
    assert MID_ID in err and f"'{status}'" in err


# ---------------------------------------------------------------------------
# Behavior 4 -- `--gap` naming a CITABLE record is unchanged, `partially-addressed` too.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", CITABLE)
def test_b4_an_explicit_citable_gap_still_yields_a_prd(tmp_path, capsys, status):
    reg = _reg(tmp_path, [_with_status(MID, status), TOP, LOW])
    rc, out, err = _run(["prd", str(reg), "--gap", MID_ID], capsys)
    assert rc == 0, err
    assert err == ""
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == MID_ID
    assert doc["sourceGap"]["status"] == status
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b4_the_two_citable_documents_differ_only_in_the_status_string(
        tmp_path, capsys):
    """Two-sided: nothing but the published status moves between the citable statuses."""
    reg_a = _reg(tmp_path, [_with_status(MID, DEFAULT_STATUS), TOP, LOW])
    reg_b = _reg(tmp_path, [_with_status(MID, OTHER_CITABLE), TOP, LOW])
    rc_a, out_a, _ = _run(["prd", str(reg_a), "--gap", MID_ID], capsys)
    rc_b, out_b, _ = _run(["prd", str(reg_b), "--gap", MID_ID], capsys)
    assert rc_a == 0 and rc_b == 0
    token_a, token_b = f'"{DEFAULT_STATUS}"', f'"{OTHER_CITABLE}"'
    assert out_a.count(token_a) == 1, out_a
    assert out_b.count(token_b) == 1, out_b
    assert out_a.replace(token_a, token_b) == out_b


# ---------------------------------------------------------------------------
# Behavior 5 -- an ALL-terminal register: exit 2, one derived stderr line, no stdout.
# ---------------------------------------------------------------------------

def _all_terminal_records():
    """One record per terminal status, so the register is all-terminal for real."""
    spine = [TOP, MID, LOW]
    return [_with_status(rec, TERMINAL[i % len(TERMINAL)])
            for i, rec in enumerate(spine)]


def test_b5_an_all_terminal_register_is_refused_with_the_exact_derived_line(
        tmp_path, capsys):
    reg = _reg(tmp_path, _all_terminal_records())
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 2, (rc, out, err)
    assert out == ""
    assert err == _all_terminal_message()
    assert err.count("\n") == 1, repr(err)


def test_b5_the_all_terminal_refusal_never_claims_the_confidence_floor(
        tmp_path, capsys):
    """Every record here CLEARS the floor, so the floor line would be a false claim."""
    reg = _reg(tmp_path, _all_terminal_records())
    _rc, _out, err = _run(["prd", str(reg)], capsys)
    assert "confidence floor" not in err, err


def test_b5_the_named_vocabulary_is_derived_from_the_taxonomy_not_a_literal(
        tmp_path, capsys, monkeypatch):
    """The patch keeps EVERY fixture record on the terminal side (all `retired`).

    Patching `TERMINAL_STATUSES` over a register that also holds an `addressed` record
    would turn that record citable, route the run away from the branch under test, and
    measure nothing.
    """
    reg = _reg(tmp_path, [_with_status(rec, "retired") for rec in (TOP, MID, LOW)])
    monkeypatch.setattr(taxonomy, "TERMINAL_STATUSES", ("retired",))
    expected = ", ".join(s for s in STATUSES if s != "retired")
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 2, (rc, out, err)
    assert out == ""
    assert err == ("Error: every gap record carries a terminal status; the citable "
                   f"statuses are: {expected}\n")
    assert "addressed" in err, "the patched vocabulary must be reflected, not hardcoded"


def test_b5_the_refusal_is_falsifiable_with_an_empty_terminal_side(
        tmp_path, capsys, monkeypatch):
    """`TERMINAL_STATUSES = ()` makes the refusal branch unreachable BY CONSTRUCTION.

    A single-member patch would instead move a probed record across the partition, so
    the empty side is the honest inverse probe.
    """
    reg = _reg(tmp_path, [_with_status(rec, "retired") for rec in (TOP, MID, LOW)])
    monkeypatch.setattr(taxonomy, "TERMINAL_STATUSES", ())
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 0, err
    assert out, "with no terminal status the all-retired register must emit a prd again"
    assert json.loads(out)["sourceGap"]["id"] == TOP_ID


# ---------------------------------------------------------------------------
# Behavior 6 -- the confidence-floor refusal keeps its own bytes.
# ---------------------------------------------------------------------------

def test_b6_no_citable_record_clears_the_floor_keeps_the_floor_message(
        tmp_path, capsys):
    reg = _reg(tmp_path, [TOP_WEAK, MID_WEAK])
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 2, (rc, out, err)
    assert out == ""
    assert err == FLOOR_MESSAGE


def test_b6_an_above_floor_terminal_record_does_not_launder_the_floor_refusal(
        tmp_path, capsys):
    """The domain is filtered BEFORE the floor partition, so this is still the floor."""
    reg = _reg(tmp_path, [_with_status(LOW, TERMINAL[0]), TOP_WEAK, MID_WEAK])
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 2, (rc, out, err)
    assert out == ""
    assert err == FLOOR_MESSAGE, "a terminal record must not be the selection"


# ---------------------------------------------------------------------------
# Behavior 7 -- a register holding zero records is unchanged.
# ---------------------------------------------------------------------------

def test_b7_a_zero_record_register_keeps_the_floor_message(tmp_path, capsys):
    reg = _reg(tmp_path, [])
    assert list(reg.glob("*.json")) == []
    rc, out, err = _run(["prd", str(reg)], capsys)
    assert rc == 2, (rc, out, err)
    assert out == ""
    assert err == FLOOR_MESSAGE


# ---------------------------------------------------------------------------
# Behavior 8 -- terminal records are still DISPLAYED, never dropped.
# ---------------------------------------------------------------------------

MIXED_STATUSES = {TOP_ID: "retired", MID_ID: "addressed", LOW_ID: DEFAULT_STATUS}


def _mixed_register(tmp_path):
    return _reg(tmp_path, [_with_status(rec, MIXED_STATUSES[rec["id"]])
                           for rec in (TOP, MID, LOW)])


@pytest.mark.parametrize("verb_argv", [
    ["list"], ["list", "--json"], ["report"], ["show", TOP_ID],
])
def test_b8_every_display_surface_still_shows_the_terminal_records(
        tmp_path, capsys, verb_argv):
    reg = _mixed_register(tmp_path)
    argv = ([verb_argv[0], TOP_ID, str(reg)] if verb_argv[0] == "show"
            else [verb_argv[0], str(reg)] + verb_argv[1:])
    rc, out, err = _run(argv, capsys)
    assert rc == 0, err
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    expected_ids = [TOP_ID] if verb_argv[0] == "show" else [TOP_ID, MID_ID, LOW_ID]
    for gid in expected_ids:
        assert gid in out, f"{argv[0]} dropped {gid} ({MIXED_STATUSES[gid]})"


def test_b8_list_json_publishes_all_three_records_with_their_own_status(
        tmp_path, capsys):
    reg = _mixed_register(tmp_path)
    rc, out, _err = _run(["list", str(reg), "--json"], capsys)
    assert rc == 0
    got = {r["gap_id"]: r["status"] for r in json.loads(out)["records"]}
    assert got == MIXED_STATUSES


def test_b8_a_terminal_status_moves_nothing_but_the_status_on_the_display_surfaces(
        tmp_path, capsys):
    """Two-sided: the only difference between the mixed and all-open registers is the
    status strings themselves, so no display surface treats a terminal record specially.
    """
    mixed = _mixed_register(tmp_path)
    plain = _reg(tmp_path, [_with_status(rec, DEFAULT_STATUS)
                            for rec in (TOP, MID, LOW)])
    rc_m, out_m, _ = _run(["list", str(mixed), "--json"], capsys)
    rc_p, out_p, _ = _run(["list", str(plain), "--json"], capsys)
    assert rc_m == 0 and rc_p == 0
    substituted = out_m.replace('"retired"', f'"{DEFAULT_STATUS}"').replace(
        '"addressed"', f'"{DEFAULT_STATUS}"')
    assert substituted == out_p


# ---------------------------------------------------------------------------
# Behavior 9 -- `scan` is unchanged on every surface: status must not gate it.
# ---------------------------------------------------------------------------

SCAN_TAILS = [[], ["--json"], ["--prd"], ["--exit-code"]]


@pytest.mark.parametrize("tail", SCAN_TAILS)
def test_b9_status_changes_no_scan_surface(tmp_path, target, capsys, tail):
    """The same target and records, with the top record `open` vs `addressed`.

    A PRESENT verdict against an `addressed` record is positive evidence that the
    closure claim is false, so the bytes and the exit code must not move.
    """
    open_reg = _reg(tmp_path, [_with_status(TOP, DEFAULT_STATUS), MID, LOW])
    term_reg = _reg(tmp_path, [_with_status(TOP, "addressed"), MID, LOW])
    rc_o, out_o, err_o = _run(["scan", str(target), "--gaps", str(open_reg)] + tail,
                              capsys)
    rc_t, out_t, err_t = _run(["scan", str(target), "--gaps", str(term_reg)] + tail,
                              capsys)
    assert rc_o == rc_t, (rc_o, rc_t, err_o, err_t)
    assert err_o == err_t
    substituted = out_t.replace('"addressed"', f'"{DEFAULT_STATUS}"')
    assert substituted == out_o, f"scan{tail} moved bytes over a status change"


def test_b9_scan_prd_still_selects_a_terminal_record_when_the_evidence_says_present(
        tmp_path, target, capsys):
    """DECIDED, not deferred: `scan --prd` reads measured target evidence, not belief."""
    reg = _reg(tmp_path, [_with_status(TOP, "addressed"), MID, LOW])
    rc, out, err = _run(["scan", str(target), "--gaps", str(reg), "--prd"], capsys)
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == TOP_ID, "status must not gate scan --prd"
    assert doc["sourceGap"]["status"] == "addressed"


def test_b9_scan_json_still_reports_the_terminal_record_as_a_finding(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, [_with_status(TOP, "retired"), MID, LOW])
    rc, out, _err = _run(["scan", str(target), "--gaps", str(reg), "--json"], capsys)
    assert rc == 0
    statuses = {f["gap_id"]: f["status"] for f in json.loads(out)["findings"]}
    assert statuses.get(TOP_ID) == "retired", statuses


# ---------------------------------------------------------------------------
# Behavior 10 -- the consumer contract states the selection rule.
# ---------------------------------------------------------------------------

def _contract_section(heading):
    """The text from `heading` to the next heading of the same or shallower depth."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    start = text.index(heading)
    depth = len(heading) - len(heading.lstrip("#"))
    rest = text[start + len(heading):]
    ends = [rest.index(m) for m in ("\n" + "#" * d + " " for d in range(1, depth + 1))
            if m in rest]
    return heading + (rest[:min(ends)] if ends else rest)


def test_b10_the_retired_claim_is_gone_from_the_whole_document():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert RETIRED_SENTENCE not in text, (
        "the document still tells a consumer the status does not affect selection")


def test_b10_the_source_gap_section_states_the_selection_rule():
    section = _contract_section(SOURCE_GAP_HEADING)
    lowered = section.lower()
    assert "citable" in lowered, section
    assert "terminal" in lowered, section
    assert "--gap" in section, section
    assert "exit 2" in lowered or "exit code 2" in lowered, section


def test_b10_status_stays_published_in_both_prd_payloads(tmp_path, target, capsys):
    reg = _reg(tmp_path, [TOP, MID, LOW])
    rc_p, out_p, _ = _run(["prd", str(reg)], capsys)
    rc_s, out_s, _ = _run(["scan", str(target), "--gaps", str(reg), "--prd"], capsys)
    assert rc_p == 0 and rc_s == 0
    for raw in (out_p, out_s):
        assert "status" in json.loads(raw)["sourceGap"], raw
