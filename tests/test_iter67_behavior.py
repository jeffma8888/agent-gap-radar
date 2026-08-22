"""Iteration 67 behaviors: `radar scan --exit-code` moves the ANSWER into the exit status.

A CI gate consuming this tool had to parse a document to learn whether a target exhibits
high-confidence gaps, because the one universal integration surface -- the process exit
code -- said 0 whatever the scan found. This iteration adds an OPT-IN flag that reports the
floor-gated verdict as the exit status while leaving the document byte-identical: `1` when
the target has at least one PRESENT finding that clears the confidence floor, `0` when it
has none, `2` when the scan applied no records and so verdicted nothing.

Black-box, and the ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors and from the published `docs/CONSUMER_CONTRACT.md` rows for
`scan` and for exit code `1`; every claim is measured by CALLING the public CLI entry point
`agent_gap_radar.cli.main` over registers and targets this file writes under pytest's
`tmp_path`, and by reading observable stdout / stderr / exit code. Nothing here reads the
implementation source, the engineer's or the reviewer's notes, a patch or a diff. The one
non-CLI import is `scoring.CONFIDENCE_FLOOR_DEFAULT`, which the suite already treats as
public (tests/test_iter13_behavior.py imports it for the same reason), plus
`scoring.confidence` used ONLY to assert each fixture's own premise.

Structural notes, so this file cannot lie later:

* **The floor value is never written down.** `FLOOR` is imported, and every fixture asserts
  its own confidence against it (`_assert_premises`), so a future change to the default
  moves one import rather than silencing four registers into the wrong side of the gate.
* **Byte identity is asserted as EQUALITY, never as a count.** `scan` prints the target path
  into its own document, so a byte count tracks the length of `tmp_path` and reds on a
  different machine (the lesson of iteration 66). The two invocations being compared differ
  only in the flag, so their argv-derived bytes are the same by construction.
* **Every exit-code claim is paired with a control that returns a DIFFERENT code over the
  same fixture.** A test that only ever observed 0 would pass against a flag that does
  nothing, and one that only ever observed 1 would pass against a flag that always fires;
  `test_flag_returns_exactly_the_three_documented_codes` asserts the full table AND that all
  three codes were actually produced, so a constant-returning implementation cannot pass.
* **The below-floor case asserts DISPLAY as well as the code.** The register's core invariant
  is that below-floor records are shown and never silently dropped, so the 0 in behavior 3
  is only correct if the finding it declined to fail on is still in the document.
* **Confidence 1 is exercised, not just 0.** `secondary-summary` scores 1 -- non-zero and
  still below the floor of 2 -- which is the input that separates the specified rule
  (`below_floor is false`) from the plausible mis-implementation `confidence > 0`.
* **No absolute machine path and no personal identifier appears here.** Every fixture lives
  under pytest's `tmp_path`; this file never needs the repo root.
"""

from __future__ import annotations

import json

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.scoring import CONFIDENCE_FLOOR_DEFAULT as FLOOR
from agent_gap_radar.scoring import confidence
from agent_gap_radar.models import Gap

#: Planted in the "hit" target; the fixture checks fire on exactly this token, so PRESENT is
#: a property of this file's fixtures and never of the committed register.
MARKER = "GAPMARK67"

#: A token no fixture tree contains, so a check built on it can never fire. Used to build an
#: ABOVE-floor record that is not a PRESENT finding.
NEVER = "GAPMARK67_ABSENT_FROM_EVERY_FIXTURE"

#: Evidence classes, chosen by the confidence they earn rather than by name. Asserted in
#: `_assert_premises` so this comment cannot drift away from the scoring rule.
CLEARS_FLOOR = "first-party-field"      # confidence 5
BARELY_CLEARS = "survey-aggregate"      # confidence 3 -- lowest reachable value above FLOOR
BELOW_NONZERO = "secondary-summary"     # confidence 1 -- below FLOOR yet not zero
BELOW_ZERO = "model-output"             # confidence 0


# ---------------------------------------------------------------------------
# Fixture builders. Registers and targets are built under `tmp_path`; no committed gap
# record is read or edited to make an assertion true.
# ---------------------------------------------------------------------------

def _check(cid, pattern=MARKER):
    """Fires PRESENT iff `pattern` appears in the target's python files.

    `models.Check` requires two-sided fixtures whenever `present_when` is set, so the bad
    tree carries the pattern and the good tree does not.
    """
    return {
        "id": cid,
        "rationale": "r",
        "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": pattern},
        "fixtures": {"bad": {"a.py": pattern + "\n"}, "good": {"a.py": "clean\n"}},
    }


def _record(gid, sev=3, freq=3, tract=3, classes=(CLEARS_FLOOR,), check_id=None,
            pattern=MARKER):
    """A schema-valid record. `check_id=None` means no automated check at all."""
    rec = {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": f"https://example.invalid/{index}",
                      "date": "2026-01-02", "quote": "the verbatim line"}
                     for index, c in enumerate(classes)],
    }
    if check_id is not None:
        rec["check"] = _check(check_id, pattern)
    return rec


def _write_register(root, records):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return d


def _target(root, body=MARKER):
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "loop.py").write_text(body + "\n", encoding="utf-8")
    return t


# --- registers -------------------------------------------------------------

#: One PRESENT finding whose evidence clears the floor. The behavior-2 base case.
ABOVE = [_record("GAP-501", 5, 3, 5, (CLEARS_FLOOR,), "CHK-501")]

#: The weakest evidence class that still clears the floor, so the gate is proved to be a
#: floor comparison rather than "only the strongest classes count".
NEAR_FLOOR = [_record("GAP-510", 4, 4, 4, (BARELY_CLEARS,), "CHK-510")]

#: The only PRESENT finding is model-output-only: confidence 0.
WEAK_ZERO = [_record("GAP-700", 5, 5, 5, (BELOW_ZERO,), "CHK-700")]

#: The only PRESENT finding scores 1 -- below the floor and NOT zero.
WEAK_NONZERO = [_record("GAP-710", 4, 4, 4, (BELOW_NONZERO,), "CHK-710")]

#: A below-floor finding outranks an above-floor one by priority. Rank must not decide the
#: code: the question is whether ANY above-floor PRESENT finding exists.
MIXED = [
    _record("GAP-500", 5, 5, 5, (BELOW_ZERO,), "CHK-500"),    # priority 10.0, confidence 0
    _record("GAP-501", 5, 3, 5, (CLEARS_FLOOR,), "CHK-501"),  # priority  8.7, confidence 5
]

#: The above-floor record's check CANNOT fire, so it is not a PRESENT finding; the only
#: PRESENT finding is below the floor. Separates "an above-floor record exists" from "an
#: above-floor PRESENT finding exists".
ABOVE_UNFIRED = [
    _record("GAP-300", 5, 3, 5, (CLEARS_FLOOR,), "CHK-300", pattern=NEVER),
    _record("GAP-301", 5, 5, 5, (BELOW_ZERO,), "CHK-301"),
]

#: One above-floor record carrying NO check: nothing is verdicted, yet a record WAS applied.
NOCHECK = [_record("GAP-100", 5, 3, 5, (CLEARS_FLOOR,), None)]

#: Zero records: the census is vacuous.
EMPTY: list[dict] = []


def _assert_premises():
    """Each fixture class must sit on the side of the floor this file claims for it."""
    def conf(classes):
        return confidence(Gap.model_validate(_record("GAP-001", classes=classes)))

    assert conf((CLEARS_FLOOR,)) >= FLOOR
    assert conf((BARELY_CLEARS,)) >= FLOOR
    assert conf((BELOW_NONZERO,)) < FLOOR
    assert conf((BELOW_ZERO,)) < FLOOR
    assert conf((BELOW_NONZERO,)) > 0, (
        "the non-zero below-floor case is what separates the floor rule from `> 0`")


def _reg(tmp_path, name, records):
    _assert_premises()
    return _write_register(tmp_path / name, records)


@pytest.fixture()
def hit(tmp_path):
    """A target that trips every marker check."""
    return _target(tmp_path / "hit")


@pytest.fixture()
def clean(tmp_path):
    """A target that trips none of them, so no finding is PRESENT."""
    return _target(tmp_path / "clean", "nothing interesting")


def _run(argv, capsys):
    """Call the CLI and return `(code, stdout, stderr)`; argparse refusals included."""
    try:
        code = main(argv)
    except SystemExit as exc:  # argparse refusals exit rather than return
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Behavior 1 -- without the flag, every scan still exits 0 exactly as today.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, records", [
    ("above", ABOVE),
    ("near_floor", NEAR_FLOOR),
    ("weak_zero", WEAK_ZERO),
    ("weak_nonzero", WEAK_NONZERO),
    ("mixed", MIXED),
    ("above_unfired", ABOVE_UNFIRED),
    ("nocheck", NOCHECK),
    ("empty", EMPTY),
])
def test_b1_without_the_flag_the_code_is_0_whatever_the_scan_found(
        tmp_path, hit, capsys, name, records):
    """The flag is OPT-IN: no invocation that works today may start returning 1 or 2."""
    reg = _reg(tmp_path, name, records)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg)], capsys)
    assert code == 0, f"{name}: an existing invocation changed its exit code"
    assert out != "", f"{name}: stdout must still carry the document"
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert "Error: " not in err


def test_b1_the_zeros_above_are_opt_in_not_a_dead_flag(tmp_path, hit, capsys):
    """Anti-vacuity control for behavior 1: the SAME register returns 1 WITH the flag."""
    reg = _reg(tmp_path, "above", ABOVE)
    without, _, _ = _run(["scan", str(hit), "--gaps", str(reg)], capsys)
    with_flag, _, _ = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert (without, with_flag) == (0, 1)


def test_b1_json_without_the_flag_is_also_unchanged(tmp_path, hit, capsys):
    reg = _reg(tmp_path, "above", ABOVE)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--json"], capsys)
    assert code == 0
    assert err == ""
    json.loads(out)


# ---------------------------------------------------------------------------
# Behavior 2 -- with the flag, >= 1 PRESENT finding whose `below_floor` is false exits 1.
# ---------------------------------------------------------------------------

def test_b2_an_above_floor_present_finding_exits_1(tmp_path, hit, capsys):
    reg = _reg(tmp_path, "above", ABOVE)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 1
    assert "GAP-501" in out, "the answer must be readable in the document too"


def test_b2_stderr_is_empty_because_nothing_went_wrong(tmp_path, hit, capsys):
    """Contract row for code 1: `stderr is empty -- nothing went wrong`."""
    reg = _reg(tmp_path, "above", ABOVE)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 1
    assert err == "", "exit 1 is a gate result, not an error"
    assert "Error: " not in out and out.endswith("\n") and not out.endswith("\n\n")


def test_b2_a_higher_ranked_below_floor_finding_does_not_mask_it(tmp_path, hit, capsys):
    """The top finding by priority is below the floor; an above-floor one sits under it."""
    reg = _reg(tmp_path, "mixed", MIXED)
    code, out, _ = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 1
    assert "GAP-500" in out and "GAP-501" in out, "both findings stay in the document"


def test_b2_the_weakest_class_above_the_floor_still_exits_1(tmp_path, hit, capsys):
    """Confidence 3 is the lowest reachable value above the floor of 2."""
    reg = _reg(tmp_path, "near_floor", NEAR_FLOOR)
    code, _, _ = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 1


@pytest.mark.parametrize("name, records, target_name", [
    ("above", ABOVE, "hit"),
    ("near_floor", NEAR_FLOOR, "hit"),
    ("mixed", MIXED, "hit"),
    ("weak_zero", WEAK_ZERO, "hit"),
    ("weak_nonzero", WEAK_NONZERO, "hit"),
    ("above_unfired", ABOVE_UNFIRED, "hit"),
    ("above_clean", ABOVE, "clean"),
    ("mixed_clean", MIXED, "clean"),
])
def test_b2_the_code_agrees_with_the_json_documents_own_below_floor_flags(
        tmp_path, hit, clean, capsys, name, records, target_name):
    """The oracle the spec names: `>= 1 PRESENT finding whose below_floor is false`.

    Recomputed from the published `--json` payload rather than restated as a literal, so
    the exit code and the document can never disagree about one target.
    """
    reg = _reg(tmp_path, name, records)
    target = hit if target_name == "hit" else clean
    argv = ["scan", str(target), "--gaps", str(reg), "--json", "--exit-code"]
    code, out, err = _run(argv, capsys)
    payload = json.loads(out)
    assert payload["confidence_floor"] == FLOOR
    expected = 1 if any(
        f["verdict"] == "PRESENT" and not f["below_floor"]
        for f in payload["findings"]) else 0
    assert code == expected, (
        f"{name}: code {code} contradicts the document's own findings "
        f"{[(f['gap_id'], f['verdict'], f['below_floor']) for f in payload['findings']]}")
    assert err == ""


# ---------------------------------------------------------------------------
# Behavior 3 -- with the flag, a target whose only PRESENT findings are below the floor
# exits 0, and those findings are still DISPLAYED.
# ---------------------------------------------------------------------------

def test_b3_a_model_output_only_present_finding_exits_0(tmp_path, hit, capsys):
    """A record whose only evidence is model output can never turn a build red."""
    reg = _reg(tmp_path, "weak_zero", WEAK_ZERO)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 0
    assert err == ""
    assert "GAP-700" in out, (
        "below-floor records are DISPLAYED, never silently dropped -- the 0 is only "
        "correct if the finding it declined to fail on is still in the document")


def test_b3_a_nonzero_but_below_floor_present_finding_exits_0(tmp_path, hit, capsys):
    """Confidence 1: below the floor and not zero, so `confidence > 0` is not the rule."""
    reg = _reg(tmp_path, "weak_nonzero", WEAK_NONZERO)
    code, out, _ = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 0
    assert "GAP-710" in out


def test_b3_an_above_floor_record_that_is_not_present_does_not_exit_1(
        tmp_path, hit, capsys):
    """Presence and confidence must BOTH hold on one finding, not one each on two."""
    reg = _reg(tmp_path, "above_unfired", ABOVE_UNFIRED)
    code, out, _ = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 0
    assert "GAP-300" in out and "GAP-301" in out


def test_b3_a_target_with_no_present_finding_at_all_exits_0(tmp_path, clean, capsys):
    reg = _reg(tmp_path, "above", ABOVE)
    code, out, err = _run(["scan", str(clean), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 0
    assert err == ""
    assert "| PRESENT | 0 |" in out, "the census must actually report zero PRESENT"
    assert "GAP-501" in out, "the record is still reported, as MANUAL"


def test_b3_records_that_verdict_nothing_still_exit_0(tmp_path, hit, capsys):
    """A register whose records carry no check applies a record but verdicts nothing.

    AMBIGUITY, carried to the PM report: the feature paragraph reserves 2 for "no verdict
    can be derived", and the contract row narrows that to "applied zero records". This
    register applies ONE record and derives NO verdict, so the two readings disagree. The
    contract's wording is the narrower and the more testable, so 0 is asserted here.
    """
    reg = _reg(tmp_path, "nocheck", NOCHECK)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 0
    assert err == ""
    assert "Gaps with no check yet: 1" in out, (
        "the record is not silently absent: the document counts what it could not check")
    payload = json.loads(_run(
        ["scan", str(hit), "--gaps", str(reg), "--json", "--exit-code"], capsys)[1])
    assert payload["records_applied"] == 1 and payload["findings"] == []


# ---------------------------------------------------------------------------
# Behavior 4 -- with the flag, stdout is byte-identical to the same invocation without it.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape", [[], ["--json"]])
@pytest.mark.parametrize("name, records, target_name", [
    ("above", ABOVE, "hit"),
    ("mixed", MIXED, "hit"),
    ("weak_zero", WEAK_ZERO, "hit"),
    ("weak_nonzero", WEAK_NONZERO, "hit"),
    ("above_unfired", ABOVE_UNFIRED, "hit"),
    ("nocheck", NOCHECK, "hit"),
    ("above_clean", ABOVE, "clean"),
])
def test_b4_the_flag_changes_the_code_and_not_one_byte_of_the_document(
        tmp_path, hit, clean, capsys, name, records, target_name, shape):
    """Equality, not a byte count: `scan` prints the target path into its own document."""
    reg = _reg(tmp_path, name, records)
    target = hit if target_name == "hit" else clean
    base = ["scan", str(target), "--gaps", str(reg), *shape]
    plain_code, plain_out, plain_err = _run(base, capsys)
    flag_code, flag_out, flag_err = _run([*base, "--exit-code"], capsys)
    assert plain_out != "", "an empty comparison would pass for the wrong reason"
    assert flag_out == plain_out, "the flag rewrote the document"
    assert flag_err == plain_err == ""
    assert plain_code == 0 and flag_code in (0, 1)
    assert flag_out.endswith("\n") and not flag_out.endswith("\n\n")


def test_b4_byte_identity_is_asserted_over_a_case_that_really_returns_1(
        tmp_path, hit, capsys):
    """Anti-vacuity: identity over 0-only cases would not test the interesting path."""
    reg = _reg(tmp_path, "above", ABOVE)
    base = ["scan", str(hit), "--gaps", str(reg)]
    plain_code, plain_out, _ = _run(base, capsys)
    flag_code, flag_out, _ = _run([*base, "--exit-code"], capsys)
    assert (plain_code, flag_code) == (0, 1)
    assert flag_out == plain_out


# ---------------------------------------------------------------------------
# The whole published table at once, plus the contract's two refusal rows.
# ---------------------------------------------------------------------------

def test_flag_returns_exactly_the_three_documented_codes(tmp_path, hit, clean, capsys):
    """One table, and it must produce ALL THREE codes.

    A flag that always returned 0, or always 1, passes any single-code test. This asserts
    the full mapping AND that the observed set is `{0, 1, 2}`.
    """
    cases = [
        ("above/hit", ABOVE, hit, 1),
        ("near_floor/hit", NEAR_FLOOR, hit, 1),
        ("mixed/hit", MIXED, hit, 1),
        ("weak_zero/hit", WEAK_ZERO, hit, 0),
        ("weak_nonzero/hit", WEAK_NONZERO, hit, 0),
        ("above_unfired/hit", ABOVE_UNFIRED, hit, 0),
        ("nocheck/hit", NOCHECK, hit, 0),
        ("above/clean", ABOVE, clean, 0),
        ("empty/hit", EMPTY, hit, 2),
    ]
    observed = {}
    for index, (label, records, target, _expected) in enumerate(cases):
        reg = _reg(tmp_path, f"table{index}", records)
        code, _, _ = _run(
            ["scan", str(target), "--gaps", str(reg), "--exit-code"], capsys)
        observed[label] = code
    assert observed == {label: expected for label, _r, _t, expected in cases}
    assert set(observed.values()) == {0, 1, 2}, (
        "the table must exercise every documented code, or a constant would pass")


def test_a_vacuous_census_refuses_rather_than_reporting_a_clean_target(
        tmp_path, hit, capsys):
    """Zero records applied is not evidence of health, so the flag refuses with 2."""
    reg = _reg(tmp_path, "empty", EMPTY)
    code, out, err = _run(["scan", str(hit), "--gaps", str(reg), "--exit-code"], capsys)
    assert code == 2
    assert out == "", "an error exit carries no half document"
    assert err.startswith("Error: ") and err.endswith("\n")
    assert err.count("\n") == 1, "one line on stderr"
    without, plain_out, plain_err = _run(["scan", str(hit), "--gaps", str(reg)], capsys)
    assert (without, plain_err) == (0, ""), "the refusal is opt-in with the flag"
    assert plain_out != ""


def test_prd_and_exit_code_cannot_be_combined(tmp_path, hit, capsys):
    """Both are floor-gated verdict surfaces answering one question with opposite codes."""
    reg = _reg(tmp_path, "above", ABOVE)
    code, out, err = _run(
        ["scan", str(hit), "--gaps", str(reg), "--prd", "--exit-code"], capsys)
    assert code == 2
    assert out == ""
    assert "--exit-code" in err and "--prd" in err
