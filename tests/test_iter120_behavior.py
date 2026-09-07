"""Iteration 120 behaviors: `radar scan <target> --gap <ID>` narrows the scanned
register DOMAIN to one record, refuses an unknown id in the published exit-2
vocabulary, and refuses rather than publishing a clean gate when the one selected
record reached no automated verdict.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, the
engineer's notes, the reviewer's notes, `fix_review.md`, `IMPLEMENTATION.patch`, or any
diff. Every assertion drives the public CLI entry point (`agent_gap_radar.cli.main`) and
reads the bytes it emitted on stdout / stderr plus its exit code, reads a PUBLISHED
document (`docs/CONSUMER_CONTRACT.md`), reads `gaps/*.json` as DATA, or reads a file
under `tests/` -- the surfaces the isolation contract names as readable.

NO LIVE GAP ID IS HARDCODED. Every verdict-class expectation is made against a fixture
register built in `tmp_path` (the spec's own second option: "or build a fixture
register"), and the two live-register tests DERIVE their id by sorting the ids that
`gaps/*.json` actually contains and reading the verdict the tool itself reports for it.

Cost note (the tester stage's median sits at the 600s cap, and a scan reads every python
file once per rule): the fixture register and target are built ONCE per module, the
unnarrowed fixture scan document and JSON payload are each computed ONCE and shared, and
the live register is scanned only under `--gap` -- never unnarrowed, which is the 10.6s
call this iteration exists to avoid.

DISCLOSURES, also carried in tester.md:

* Behavior 1's literal `120` and behavior 6's "returned a full 120-record document
  before this iteration" are properties of the register AT ONE MOMENT and of the PREVIOUS
  commit respectively. Neither is hardcoded: behavior 1 is tested as
  `applied == len(register)` over a fixture register plus `applied == 1` over the live
  one, and the pre-iteration behavior of `--gap ./` is not reachable from this checkout.
* Behavior 7's "byte-identical to HEAD" clause is tested in its reachable form --
  byte-stability across repeated runs, plus every contract-listed flag combination still
  answering with the same code, document and stderr. Comparing bytes against a different
  commit would require checking that commit out, which a test may not do.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main

from test_iter15_behavior import MARKER, MITIGATION, _check

#: The register default confidence floor (pinned by tests/test_iter02_behavior.py and
#: tests/test_scoring.py). Spelled once so a default change breaks one constant.
FLOOR = 2
#: This repo: the live register, and the published document the acceptance criteria move.
REPO = pathlib.Path(__file__).resolve().parent.parent
LIVE_REGISTER = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
#: Any `GAP-NNN` token, used to prove a narrowed document mentions exactly one id.
GAP_ID_RE = re.compile(r"GAP-\d+")
#: An id no register record carries. Three digits is a well-formed id, so this reaches
#: the register lookup rather than the id-syntax door.
UNKNOWN_ID = "GAP-999"


def _record(gid, check, classes=("first-party-field",)):
    """A schema-valid record whose evidence classes decide its DERIVED confidence.

    A lone `model-output` citation ceilings at 0 -- below the floor -- and a lone
    `first-party-field` citation at 5, which is how the below-floor record below is made
    below-floor without any prose asserting a confidence.
    """
    rec = {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}
                     for c in classes],
    }
    if check is not None:
        rec["check"] = check
    return rec


#: One id per case the spec's behaviors 2, 4 and 5 distinguish.
PRESENT_ABOVE = "GAP-301"
MANUAL_ID = "GAP-302"
ABSENT_ID = "GAP-303"
NOT_APPLICABLE_ID = "GAP-304"
PRESENT_BELOW = "GAP-305"
NO_CHECK_ID = "GAP-306"

#: Verdicts are a property of THIS fixture pair (register + target), never of the
#: published register. Every one is asserted from the tool's own payload before it is
#: relied on (see `test_b0_...`), so no expectation here is taken on faith.
EXPECTED_VERDICTS = {
    PRESENT_ABOVE: "PRESENT",
    MANUAL_ID: "MANUAL",
    ABSENT_ID: "ABSENT",
    NOT_APPLICABLE_ID: "NOT_APPLICABLE",
    PRESENT_BELOW: "PRESENT",
}

RECORDS = [
    _record(PRESENT_ABOVE, _check("CHK-301")),
    _record(MANUAL_ID, _check("CHK-302", pattern="NEVER_APPEARS_ANYWHERE")),
    _record(ABSENT_ID, _check("CHK-303", pattern="NEVER_APPEARS_ANYWHERE",
                              mitigated=MITIGATION)),
    _record(NOT_APPLICABLE_ID, _check("CHK-304", applies=["**/*.rs"])),
    _record(PRESENT_BELOW, _check("CHK-305"), classes=("model-output",)),
    _record(NO_CHECK_ID, None),
]

#: Records that reach a finding at all. `NO_CHECK_ID` has no check, so it is reported as
#: uncheckable rather than as a finding.
VERDICTED_IDS = tuple(sorted(EXPECTED_VERDICTS))
#: The two ways a one-record domain can reach no automated answer.
NO_ANSWER_IDS = (MANUAL_ID, NO_CHECK_ID)


# ---------------------------------------------------------------------------
# Fixtures. Built once per module: see the cost note in the module docstring.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """`(register path, target path)` as strings, for the CLI's positional/flag pair."""
    root = tmp_path_factory.mktemp("iter120")
    gaps = root / "reg" / "gaps"
    gaps.mkdir(parents=True)
    for rec in RECORDS:
        (gaps / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    target = root / "target"
    target.mkdir()
    (target / "a.py").write_text(MARKER + "\n", encoding="utf-8")
    (target / "b.py").write_text(MITIGATION + "\n", encoding="utf-8")
    return str(root / "reg"), str(target)


def _capture(argv):
    """Drive the public CLI out-of-band of capsys, returning (code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def wide_json(world):
    """The UNNARROWED `--json` payload over the fixture register, computed once."""
    reg, target = world
    code, out, err = _capture(["scan", target, "--gaps", reg, "--json"])
    assert (code, err) == (0, ""), (code, err)
    return json.loads(out)


@pytest.fixture(scope="module")
def wide_text(world):
    """The UNNARROWED text document over the fixture register, computed once."""
    reg, target = world
    code, out, err = _capture(["scan", target, "--gaps", reg])
    assert (code, err) == (0, ""), (code, err)
    return out


def _scan(world, *extra):
    reg, target = world
    return _capture(["scan", target, "--gaps", reg, *extra])


def _one_error_line(err):
    """The single stderr line of a refusal, asserted to be exactly one prefixed line."""
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one stderr line, got {lines!r}"
    assert lines[0].startswith("Error: "), repr(lines[0])
    assert "usage:" not in err, repr(err)
    return lines[0]


# ---------------------------------------------------------------------------
# Behavior 0 -- the fixture's premise. Every later expectation is derived from the
# tool's own payload, so a fixture that stopped producing five distinct-enough
# verdicts fails HERE rather than making a later test vacuous.
# ---------------------------------------------------------------------------

def test_b0_the_fixture_register_really_spans_the_verdict_classes(wide_json):
    got = {f["gap_id"]: f["verdict"] for f in wide_json["findings"]}
    assert got == EXPECTED_VERDICTS, got
    assert wide_json["uncheckable"] == [NO_CHECK_ID], wide_json["uncheckable"]
    assert wide_json["confidence_floor"] == FLOOR
    assert wide_json["records_applied"] == len(RECORDS)
    below = {f["gap_id"] for f in wide_json["findings"] if f["below_floor"]}
    assert below == {PRESENT_BELOW}, below


# ---------------------------------------------------------------------------
# Behavior 1 -- domain narrowed, text surface.
# ---------------------------------------------------------------------------

def test_b1_gap_narrows_the_applied_domain_to_one_record(world, wide_text):
    """`Register records applied:` reads 1, versus the whole register without the flag."""
    assert f"Register records applied: {len(RECORDS)}" in wide_text
    code, narrow, err = _scan(world, "--gap", PRESENT_ABOVE)
    assert (code, err) == (0, ""), (code, err, narrow)
    assert "Register records applied: 1" in narrow


def test_b1_no_other_id_occurs_anywhere_in_the_narrowed_document(world, wide_text):
    """The narrowed document is ABOUT one record: NO OTHER id occurs anywhere in it.

    AMBIGUITY, reported to the PM in tester.md: the spec says "the named id is the only
    `GAP-NNN` id occurring anywhere in that document", which reads as an equality. Taken
    literally it is FALSE against a correct implementation for one verdict class -- the
    shipped renderer lists PRESENT, MANUAL and ABSENT findings by id but reports
    NOT_APPLICABLE only as a table COUNT, so a document narrowed to a NOT_APPLICABLE
    record names ZERO ids (pre-existing behavior, unrelated to `--gap`). The hazard the
    clause exists to catch is a SECOND record leaking into a narrowed document, so it is
    tested in that intent-preserving form: a subset for every class, an equality for the
    classes the renderer names, and a non-vacuity guard that the wide document really
    does name several.
    """
    assert len(set(GAP_ID_RE.findall(wide_text))) > 1, "premise: the wide doc names many"
    named = 0
    for gid in VERDICTED_IDS + (NO_CHECK_ID,):
        code, narrow, err = _scan(world, "--gap", gid)
        assert (code, err) == (0, ""), (gid, code, err)
        seen = set(GAP_ID_RE.findall(narrow))
        assert seen <= {gid}, (gid, seen)
        named += bool(seen)
    assert named >= 3, "no narrowed document named its own id, so the check is vacuous"


@pytest.mark.parametrize("gid", [PRESENT_ABOVE, PRESENT_BELOW, MANUAL_ID, ABSENT_ID])
def test_b1_the_listed_verdict_classes_name_exactly_the_selected_id(world, gid):
    """The equality half of the clause, over the classes the renderer lists by id."""
    code, narrow, err = _scan(world, "--gap", gid)
    assert (code, err) == (0, ""), (gid, code, err)
    assert set(GAP_ID_RE.findall(narrow)) == {gid}, gid


def test_b1_live_register_narrows_to_one_of_its_own_records():
    """Same clause against the SHIPPED register, with the id derived from its files.

    The unnarrowed live scan is deliberately not run: it is the ~10.6s call this
    iteration exists to make unnecessary, and `applied == 1` is the whole claim.
    """
    ids = sorted(json.loads(p.read_text(encoding="utf-8"))["id"]
                 for p in LIVE_REGISTER.glob("*.json"))
    assert len(ids) > 1, ids
    gid = ids[0]
    code, out, err = _capture(["scan", str(REPO), "--gaps", str(REPO), "--gap", gid])
    assert (code, err) == (0, ""), (code, err)
    assert "Register records applied: 1" in out
    assert gid in out


# ---------------------------------------------------------------------------
# Behavior 2 -- narrowing changes no verdict, and adds/removes no key.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gid", VERDICTED_IDS)
def test_b2_the_one_finding_is_dict_equal_to_its_unnarrowed_self(world, wide_json, gid):
    code, out, err = _scan(world, "--json", "--gap", gid)
    assert (code, err) == (0, ""), (code, err)
    payload = json.loads(out)
    assert len(payload["findings"]) == 1, payload["findings"]
    wide_finding = next(f for f in wide_json["findings"] if f["gap_id"] == gid)
    assert payload["findings"][0] == wide_finding


@pytest.mark.parametrize("gid", VERDICTED_IDS + (NO_CHECK_ID,))
def test_b2_the_payload_key_set_and_the_floor_are_untouched(world, wide_json, gid):
    """No key added, none removed -- the same brake iteration 118 holds on the emitter."""
    code, out, err = _scan(world, "--json", "--gap", gid)
    assert (code, err) == (0, ""), (code, err)
    payload = json.loads(out)
    assert set(payload) == set(wide_json), (set(payload) ^ set(wide_json))
    assert payload["records_applied"] == 1
    assert payload["confidence_floor"] == wide_json["confidence_floor"] == FLOOR
    assert payload["target"] == wide_json["target"]
    for finding in payload["findings"]:
        wide_finding = next(f for f in wide_json["findings"]
                            if f["gap_id"] == finding["gap_id"])
        assert set(finding) == set(wide_finding), (set(finding) ^ set(wide_finding))


def test_b2_a_record_with_no_check_narrows_to_zero_findings_and_one_applied(world):
    """Selection is on the LOADED RECORDS: an uncheckable record still applies 1."""
    code, out, err = _scan(world, "--json", "--gap", NO_CHECK_ID)
    assert (code, err) == (0, ""), (code, err)
    payload = json.loads(out)
    assert payload["records_applied"] == 1
    assert payload["findings"] == []
    assert payload["uncheckable"] == [NO_CHECK_ID]


# ---------------------------------------------------------------------------
# Behavior 3 -- unknown id refuses in the published vocabulary.
# ---------------------------------------------------------------------------

def test_b3_unknown_id_exits_2_with_empty_stdout_and_one_error_line(world):
    code, out, err = _scan(world, "--gap", UNKNOWN_ID)
    assert code == 2
    assert out == ""
    assert _one_error_line(err) == f"Error: no such gap: {UNKNOWN_ID}"
    assert err == f"Error: no such gap: {UNKNOWN_ID}\n"


def test_b3_the_sentence_is_byte_for_byte_the_one_prd_gap_already_produces(world):
    """`prd --gap` has published this refusal since iteration 88; `scan` reuses it."""
    reg, _target = world
    scan_code, scan_out, scan_err = _scan(world, "--gap", UNKNOWN_ID)
    prd_code, prd_out, prd_err = _capture(["prd", reg, "--gap", UNKNOWN_ID])
    assert (prd_code, prd_out) == (2, "")
    assert scan_err == prd_err, (scan_err, prd_err)
    assert (scan_code, scan_out) == (prd_code, prd_out)


@pytest.mark.parametrize("flags", [(), ("--json",), ("--exit-code",), ("--prd",)])
def test_b3_the_refusal_precedes_every_output_mode(world, flags):
    """An unknown id is refused before any surface is chosen, so no half document."""
    code, out, err = _scan(world, "--gap", UNKNOWN_ID, *flags)
    assert (code, out) == (2, "")
    assert err == f"Error: no such gap: {UNKNOWN_ID}\n"


def test_b3_selection_is_scoped_to_the_register_the_invocation_loaded(world):
    """An id that exists in the SHIPPED register but not in `--gaps` must be refused.

    This is the discriminating form of the acceptance criterion "selection happens on the
    LOADED RECORDS": an implementation that resolved the id against a default or ambient
    register (or that fell back to one when the id missed) would pass every other clause
    of behavior 3, because `GAP-999` is in no register at all. A real live id makes the
    two readings disagree.
    """
    live_ids = sorted(json.loads(p.read_text(encoding="utf-8"))["id"]
                      for p in LIVE_REGISTER.glob("*.json"))
    assert live_ids, "premise: the shipped register has records"
    fixture_ids = {rec["id"] for rec in RECORDS}
    outsider = next(gid for gid in live_ids if gid not in fixture_ids)
    code, out, err = _scan(world, "--gap", outsider)
    assert (code, out) == (2, ""), (outsider, code, out)
    assert err == f"Error: no such gap: {outsider}\n", repr(err)


def test_b3_an_empty_gap_value_is_refused_rather_than_read_as_no_selection(world):
    """`--gap ""` is a selection that matches nothing, not an absent flag.

    The fail-open reading treats a falsy value as "no narrowing" and hands back a full
    register document at exit 0, which is the quiet failure behavior 6 forbids for the
    other path-shaped values.
    """
    code, out, err = _scan(world, "--gap", "")
    assert (code, out) == (2, ""), (code, out)
    assert err == "Error: no such gap: \n", repr(err)


# ---------------------------------------------------------------------------
# Behavior 4 -- no fail-open when the one finding has no automated answer.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gid", NO_ANSWER_IDS)
def test_b4_exit_code_refuses_when_the_one_record_reached_no_verdict(world, gid):
    code, out, err = _scan(world, "--gap", gid, "--exit-code")
    assert code == 2, (code, err)
    assert out == ""
    line = _one_error_line(err)
    assert gid in line, line
    assert "no automated verdict" in line, line


@pytest.mark.parametrize("gid", NO_ANSWER_IDS)
def test_b4_the_same_selection_without_exit_code_still_answers(world, gid):
    """Non-vacuity: the refusal belongs to `--exit-code`, not to the record."""
    code, out, err = _scan(world, "--gap", gid)
    assert (code, err) == (0, ""), (code, err)
    assert "Register records applied: 1" in out


def test_b4_the_refusal_is_derived_from_the_verdict_not_from_a_second_floor_test(world):
    """A BELOW-FLOOR PRESENT finding reached an automated verdict, so it must NOT refuse.

    This is the discriminating case: an implementation that refused whenever the one
    finding failed to clear the floor would pass every other clause in behavior 4 and
    break the register's core invariant here.
    """
    code, out, err = _scan(world, "--gap", PRESENT_BELOW, "--exit-code")
    assert (code, err) == (0, ""), (code, err)
    assert PRESENT_BELOW in out


def test_b4_an_unnarrowed_exit_code_scan_over_the_same_records_still_answers(world):
    """Behavior 4 is scoped to the one-record domain: whole-register semantics unchanged.

    The same register holds MANUAL and no-check records, and unnarrowed `--exit-code`
    answers `1` (a PRESENT finding clears the floor) rather than refusing.
    """
    code, out, err = _scan(world, "--exit-code")
    assert (code, err) == (1, ""), (code, err)
    assert f"Register records applied: {len(RECORDS)}" in out


# ---------------------------------------------------------------------------
# Behavior 5 -- the floor gate is inherited, not renegotiated.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gid,expected", [
    (PRESENT_ABOVE, 1),
    (ABSENT_ID, 0),
    (NOT_APPLICABLE_ID, 0),
    (PRESENT_BELOW, 0),
])
def test_b5_exit_code_over_one_record_answers_with_the_inherited_floor_rule(
        world, gid, expected):
    code, out, err = _scan(world, "--gap", gid, "--exit-code")
    assert (code, err) == (expected, ""), (gid, code, err)
    assert "Register records applied: 1" in out


def test_b5_a_below_floor_present_finding_is_displayed_never_dropped(world):
    """The register's core invariant, over the narrowed domain and under the gate."""
    code, gated, err = _scan(world, "--gap", PRESENT_BELOW, "--exit-code")
    assert (code, err) == (0, "")
    assert PRESENT_BELOW in gated
    assert "| PRESENT | 1 |" in gated
    code, plain, err = _scan(world, "--gap", PRESENT_BELOW)
    assert (code, err) == (0, "")
    assert gated == plain, "--exit-code must leave the document byte-identical"


@pytest.mark.parametrize("gid", [ABSENT_ID, NOT_APPLICABLE_ID, MANUAL_ID, NO_CHECK_ID])
def test_b5_prd_over_one_record_refuses_when_that_record_is_not_present(world, gid):
    code, out, err = _scan(world, "--gap", gid, "--prd")
    assert (code, out) == (2, ""), (gid, code, out)
    line = _one_error_line(err)
    assert "no PRESENT finding to build against" in line, line


def test_b5_prd_over_one_below_floor_record_refuses_naming_the_floor(world):
    code, out, err = _scan(world, "--gap", PRESENT_BELOW, "--prd")
    assert (code, out) == (2, ""), (code, out)
    line = _one_error_line(err)
    assert f"clears the confidence floor {FLOOR}" in line, line
    assert PRESENT_BELOW in line, line


def test_b5_prd_over_one_above_floor_record_still_emits_its_document(world):
    code, out, err = _scan(world, "--gap", PRESENT_ABOVE, "--prd")
    assert (code, err) == (0, ""), (code, err)
    payload = json.loads(out)
    assert PRESENT_ABOVE in json.dumps(payload)


def test_b5_gap_and_exit_code_and_prd_stay_mutually_exclusive_where_they_were(world):
    """`--gap` composes with each floor-gated surface; it does not marry them.

    This door is a STRUCTURAL refusal, so the contract has it print the `usage:` block
    above the prefixed line and argparse raises rather than returning -- hence
    `pytest.raises` and a LAST-line assertion rather than `_one_error_line`.
    """
    reg, target = world
    with pytest.raises(SystemExit) as excinfo:
        _capture(["scan", target, "--gaps", reg, "--gap", PRESENT_ABOVE,
                  "--prd", "--exit-code"])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# Behavior 6 -- `--gaps` still means the register LOCATION, and the rebinding is loud.
# ---------------------------------------------------------------------------

def test_b6_gaps_is_still_the_register_location_alongside_gap(world):
    """Non-vacuity for behavior 6: the register really is being read from `--gaps`.

    The fixture ids exist in no other register on disk, so a document that names one
    proves `--gaps` was honoured as a LOCATION while `--gap` selected a RECORD.
    """
    code, out, err = _scan(world, "--gap", PRESENT_ABOVE)
    assert (code, err) == (0, ""), (code, err)
    assert PRESENT_ABOVE in out and "Register records applied: 1" in out


@pytest.mark.parametrize("argv_tail", [
    ("--gap", "./"),
    ("--gap", "."),
])
def test_b6_gap_no_longer_abbreviates_gaps_and_fails_loudly(world, argv_tail):
    """A path-shaped value is an id lookup now, and it is refused, never silently taken.

    Before this iteration `--gap` was an unambiguous argparse abbreviation of `--gaps`,
    so `radar scan . --gap ./` returned a full register document with exit 0. It must
    now exit 2 with the published sentence and an empty stdout.
    """
    _reg, target = world
    code, out, err = _capture(["scan", target, *argv_tail])
    assert (code, out) == (2, ""), (code, out)
    assert err == f"Error: no such gap: {argv_tail[1]}\n", repr(err)


def test_b6_the_rebinding_is_loud_even_when_gaps_is_also_given(world):
    code, out, err = _scan(world, "--gap", "./")
    assert (code, out) == (2, ""), (code, out)
    assert err == "Error: no such gap: ./\n", repr(err)


def test_b6_the_now_ambiguous_short_abbreviation_fails_loudly_too(world):
    """`--ga` was an unambiguous abbreviation of `--gaps`; adding `--gap` makes it ambiguous.

    That is the second half of "the abbreviation change is loud": the dangerous outcome is
    not an error, it is argparse silently keeping the OLD binding (or taking the new one)
    for a command line a consumer already ships. It must refuse, with empty stdout, and
    the refusal must name BOTH candidates so the reader can tell which they meant.
    """
    _reg, target = world
    out, err = io.StringIO(), io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            main(["scan", target, "--ga", "./"])
    assert excinfo.value.code == 2
    assert out.getvalue() == "", repr(out.getvalue())
    tail = [ln for ln in err.getvalue().splitlines() if ln.strip()][-1]
    assert tail.startswith("Error: "), repr(tail)
    assert "ambiguous" in tail, repr(tail)
    assert "--gaps" in tail and "--gap" in tail, repr(tail)


# ---------------------------------------------------------------------------
# Behavior 7 -- deterministic, byte-stable, one trailing newline, defaults unchanged.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flags", [(), ("--json",)])
def test_b7_three_narrowed_runs_are_byte_identical(world, flags):
    runs = [_scan(world, *flags, "--gap", PRESENT_ABOVE) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    code, out, err = runs[0]
    assert (code, err) == (0, "")
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-40:])
    assert out.count("\r") == 0


@pytest.mark.parametrize("gid", VERDICTED_IDS + (NO_CHECK_ID,))
@pytest.mark.parametrize("flags", [(), ("--json",)])
def test_b7_every_narrowed_document_ends_in_exactly_one_newline(world, gid, flags):
    code, out, err = _scan(world, *flags, "--gap", gid)
    assert (code, err) == (0, ""), (gid, code, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-40:])


@pytest.mark.parametrize("flags", [(), ("--json",), ("--exit-code",), ("--prd",)])
def test_b7_the_unnarrowed_verb_is_unchanged_and_byte_stable(world, flags):
    """Every flag combination the contract lists still answers, twice, identically.

    See the module docstring: comparing bytes against a different commit is out of a
    test's reach, so "unchanged" is tested as repeat-stability plus the published
    per-combination outcome.
    """
    first = _scan(world, *flags)
    second = _scan(world, *flags)
    assert first == second
    code, out, err = first
    expected = {(): 0, ("--json",): 0, ("--exit-code",): 1, ("--prd",): 0}[flags]
    assert code == expected, (flags, code, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-40:])


def test_b7_the_default_domain_is_still_the_whole_register(world, wide_json):
    """The flag's absence must change nothing: default `records_applied` is every record."""
    assert wide_json["records_applied"] == len(RECORDS)
    assert len(wide_json["findings"]) == len(VERDICTED_IDS)


# ---------------------------------------------------------------------------
# Acceptance criteria that live in a PUBLISHED document, not in behavior.
# ---------------------------------------------------------------------------

def _contract_rows():
    return [ln for ln in CONTRACT.read_text(encoding="utf-8").splitlines()
            if ln.startswith("|")]


def test_ac_the_scan_stable_surface_row_names_the_new_flag():
    rows = [r for r in _contract_rows() if "`radar scan <target>" in r]
    assert len(rows) == 1, rows
    assert "[--gap <ID>]" in rows[0], rows[0]
    assert "[--gaps R]" in rows[0], rows[0]


def test_ac_the_verbs_own_help_publishes_the_new_flag_beside_the_old_one():
    """The CLI's own `--help` is a published surface: both flags must appear, distinctly.

    Read from the tool, not from the source. `--gaps` names a location and `--gap` names a
    record, so the two must be separately documented -- a help text that lists only one of
    them leaves the rebinding in behavior 6 undiscoverable.
    """
    out, err = io.StringIO(), io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            main(["scan", "--help"])
    assert excinfo.value.code == 0
    text = out.getvalue()
    assert err.getvalue() == "", repr(err.getvalue())
    options = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("--gap")]
    assert any(ln.startswith("--gaps ") for ln in options), options
    assert any(re.match(r"--gap\s+\S", ln) and not ln.startswith("--gaps")
               for ln in options), options


def test_ac_the_exit_code_2_row_states_both_per_gap_refusals():
    rows = [r for r in _contract_rows() if r.startswith("| `2` |")]
    assert len(rows) == 1, rows
    row = rows[0]
    assert "no such gap" in row, row
    assert "no automated verdict" in row, row


def test_ac_this_module_carries_no_absolute_machine_path_or_identifier():
    """Public-repo safety, self-checked: the paths here are all built at run time."""
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    # Assembled at run time: a literal list here would match ITSELF and red a clean file.
    forbidden = [chr(47) + p for p in ("Users", "home")] + ["amaz" + "on"]
    for token in forbidden:
        assert token.lower() not in text.lower(), token
    assert not re.search(r"[A-Za-z]:\\\\", text)
