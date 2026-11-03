"""Iteration 384 (tester): black-box pins for `scan --exit-code` refusing an unclearable floor.

`--floor N` with N above the highest confidence the evidence ladder can derive turns
`--exit-code` into an always-green gate, so that combination is now refused (exit 2,
empty stdout, one fixed `Error:` sentence). This module drives only the public CLI and
does not trust a hand-written expectation where an oracle exists:

- behavior 1: a sweep of unclearable floors (6, 7, 10, 99, 1000) over registers whose
  ONLY finding is PRESENT at confidence 5 -- the strongest finding the ladder can make
  still cannot clear them -- checked in-process and in a FRESH `python -m` process;
- behavior 2: every unreadable-input variant (missing register, missing target, both,
  a FILE as target) still yields the floor sentence, not a path error;
- behavior 3: every subset of the `--gap/--layer/--json/--baseline` modifiers keeps the
  refusal byte-identical;
- behavior 4: a floor sweep -1..5 where the same scan's `--json` document is the
  oracle: exit 1 iff some PRESENT finding has `below_floor == false`, else 0, and the
  stdout is the plain (no `--exit-code`) document either way;
- behaviors 5, 6: floors without `--exit-code` stay accepted, `--prd` and
  `--baseline`-without-`--exit-code` keep their own refusal sentences;
- behavior 7: the published ceiling equals what the live register derives;
- behavior 8: the contract rows carry the phrase.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import CONFIDENCE_MAX, confidence
from test_iter02_behavior import _record, _target, _write_register

REPO = pathlib.Path(__file__).resolve().parents[1]
LIVE = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
PHRASE = "exceeds the highest confidence the evidence ladder can derive"
UNCLEARABLE = (6, 7, 10, 99, 1000)
CLEARABLE = (-1, 0, 1, 2, 3, 4, 5)


def _sentence(floor: int) -> str:
    # Spelled with the literal 5 on purpose: behavior 1 pins the published text, and
    # behavior 7 separately pins that the constant is 5.
    return (f"Error: --floor {floor} exceeds the highest confidence the evidence ladder "
            f"can derive (5), so --exit-code could never fail; use a floor of 5 or less")


def _run(*argv: object) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as exc:  # argparse-level refusals
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _last(err: str) -> str:
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "stderr is empty"
    return lines[-1]


def _assert_floor_refusal(result: tuple[int, str, str], floor: int) -> None:
    code, out, err = result
    assert code == 2, (code, err[-400:])
    assert out == "", "a refusal must leave stdout empty"
    assert _last(err) == _sentence(floor), err


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("iter384t")
    target = _target(root / "hit")
    c5 = _write_register(root / "c5", [
        _record("GAP-841", 4, 4, 4, ("first-party-field",), "CHK-841")])
    c3 = _write_register(root / "c3", [
        _record("GAP-843", 4, 4, 4, ("survey-aggregate",), "CHK-843")])
    # PRESENT at c5, c3, c1, c0 plus one record with no automated check (MANUAL).
    mix = _write_register(root / "mix", [
        _record("GAP-851", 5, 3, 5, ("first-party-field",), "CHK-851"),
        _record("GAP-852", 5, 5, 5, ("secondary-summary",), "CHK-852"),
        _record("GAP-853", 4, 4, 4, ("survey-aggregate",), "CHK-853"),
        _record("GAP-854", 3, 3, 3, ("model-output",), "CHK-854"),
        _record("GAP-855", 2, 2, 2, ("first-party-field",), None),
    ])
    baseline = root / "baseline.json"
    code, out, err = _run("scan", target, "--gaps", mix, "--json")
    assert code == 0, err
    baseline.write_text(out, encoding="utf-8")
    return {"root": root, "target": target, "c5": c5, "c3": c3, "mix": mix, "baseline": baseline}


# --- behavior 1 ------------------------------------------------------------


def test_b0_the_c5_fixture_is_present_at_the_ceiling(bed):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["c5"], "--json", "--floor", "0")
    assert code == 0, err
    findings = json.loads(out)["findings"]
    assert [(f["gap_id"], f["verdict"], f["confidence"]) for f in findings] == [
        ("GAP-841", "PRESENT", 5)]


@pytest.mark.parametrize("floor", UNCLEARABLE)
@pytest.mark.parametrize("reg", ["c5", "mix"])
def test_b1_an_unclearable_floor_is_refused(bed, reg, floor):
    _assert_floor_refusal(
        _run("scan", bed["target"], "--gaps", bed[reg], "--exit-code", "--floor", floor), floor)


@pytest.mark.parametrize("floor", UNCLEARABLE)
def test_b1_the_floor_may_come_before_the_flag(bed, floor):
    _assert_floor_refusal(
        _run("scan", "--floor", floor, bed["target"], "--exit-code", "--gaps", bed["c5"]), floor)


def test_b1_the_live_register_over_this_repo_is_refused(bed):
    # At the default floor this real scan fails the gate (exit 1); floor 6 used to pass it.
    code, _, _ = _run("scan", REPO, "--gaps", LIVE, "--exit-code")
    assert code == 1
    _assert_floor_refusal(_run("scan", REPO, "--gaps", LIVE, "--exit-code", "--floor", 6), 6)


@pytest.mark.parametrize("floor", (6, 99))
def test_b1_a_fresh_process_refuses_identically(bed, floor):
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "scan", str(bed["target"]),
         "--gaps", str(bed["c5"]), "--exit-code", "--floor", str(floor)],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2, proc.stderr
    assert proc.stdout == ""
    assert _last(proc.stderr) == _sentence(floor)
    assert "Traceback" not in proc.stderr


def test_b1_the_refusal_is_deterministic(bed):
    runs = {_run("scan", bed["target"], "--gaps", bed["mix"], "--exit-code", "--floor", 6)
            for _ in range(3)}
    assert len(runs) == 1


# --- behavior 2 ------------------------------------------------------------


@pytest.mark.parametrize("variant", ["no-register", "no-target", "neither", "file-target"])
def test_b2_the_floor_is_decided_before_any_path(bed, variant):
    root = bed["root"]
    missing = root / "does-not-exist"
    a_file = bed["baseline"]
    target, gaps = {
        "no-register": (bed["target"], missing),
        "no-target": (missing, bed["mix"]),
        "neither": (missing, root / "also-missing"),
        "file-target": (a_file, bed["mix"]),
    }[variant]
    _assert_floor_refusal(_run("scan", target, "--gaps", gaps, "--exit-code", "--floor", 7), 7)


def test_b2_the_controls_do_refuse_on_the_path_at_a_clearable_floor(bed):
    # Proves the variants above would have produced a DIFFERENT error had the floor
    # check not come first.
    missing = bed["root"] / "does-not-exist"
    for argv in ((bed["target"], "--gaps", missing), (missing, "--gaps", bed["mix"])):
        code, out, err = _run("scan", *argv, "--exit-code", "--floor", 5)
        assert code == 2 and out == ""
        line = _last(err)
        assert line.startswith("Error: ") and PHRASE not in line, line


# --- behavior 3 ------------------------------------------------------------

MODIFIERS = ("gap", "layer", "json", "baseline")


def _modifier_argv(bed, names):
    argv = []
    for name in names:
        argv += {"gap": ["--gap", "GAP-851"], "layer": ["--layer", "orchestration"],
                 "json": ["--json"], "baseline": ["--baseline", str(bed["baseline"])]}[name]
    return argv


@pytest.mark.parametrize(
    "names",
    [c for n in range(1, len(MODIFIERS) + 1) for c in itertools.combinations(MODIFIERS, n)],
    ids=lambda c: "+".join(c),
)
def test_b3_every_modifier_subset_keeps_the_refusal(bed, names):
    _assert_floor_refusal(
        _run("scan", bed["target"], "--gaps", bed["mix"], "--exit-code", "--floor", 6,
             *_modifier_argv(bed, names)), 6)


@pytest.mark.parametrize("names", [("gap",), ("layer",), ("json",), ("baseline",)],
                         ids=lambda c: c[0])
def test_b3_the_same_modifiers_are_accepted_at_floor_5(bed, names):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["mix"], "--exit-code",
                          "--floor", 5, *_modifier_argv(bed, names))
    assert code in (0, 1), err
    assert PHRASE not in err
    assert out.endswith("\n") and not out.endswith("\n\n")


# --- behavior 4 ------------------------------------------------------------


@pytest.mark.parametrize("floor", CLEARABLE)
@pytest.mark.parametrize("reg", ["c5", "c3", "mix"])
@pytest.mark.parametrize("fmt", [(), ("--json",)], ids=["markdown", "json"])
def test_b4_clearable_floors_follow_the_json_oracle(bed, reg, floor, fmt):
    base = ("scan", bed["target"], "--gaps", bed[reg], "--floor", floor)
    oc, oracle, oerr = _run(*base, "--json")
    assert oc == 0, oerr
    gating = [f for f in json.loads(oracle)["findings"]
              if f["verdict"] == "PRESENT" and not f["below_floor"]]
    pc, plain, perr = _run(*base, *fmt)
    assert pc == 0, perr
    code, out, err = _run(*base, *fmt, "--exit-code")
    assert code == (1 if gating else 0), (floor, err)
    assert out == plain, "the gate prints the same document it gates on"
    assert err == perr
    assert PHRASE not in err


def test_b4_both_outcomes_are_reached_by_the_sweep(bed):
    # The c3 register's only PRESENT finding clears floors <= 3 and nothing above.
    codes = {f: _run("scan", bed["target"], "--gaps", bed["c3"], "--exit-code", "--floor", f)[0]
             for f in CLEARABLE}
    assert codes == {-1: 1, 0: 1, 1: 1, 2: 1, 3: 1, 4: 0, 5: 0}


def test_b4_a_confidence_5_present_finding_fails_the_gate_at_floor_5(bed):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["c5"], "--exit-code", "--floor", 5)
    assert code == 1, err
    assert out != "" and PHRASE not in err


# --- behavior 5 ------------------------------------------------------------


@pytest.mark.parametrize("floor", UNCLEARABLE)
def test_b5_scan_markdown_without_the_gate_accepts_any_floor(bed, floor):
    ref = _run("scan", bed["target"], "--gaps", bed["mix"], "--floor", 5)
    got = _run("scan", bed["target"], "--gaps", bed["mix"], "--floor", floor)
    assert got[0] == 0 and got[2] == "", got[2]
    assert got[1] == ref[1], "the markdown document is floor-independent"


@pytest.mark.parametrize("floor", UNCLEARABLE)
def test_b5_scan_json_without_the_gate_accepts_any_floor(bed, floor):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["mix"], "--json", "--floor", floor)
    assert code == 0 and err == "", err
    doc = json.loads(out)
    assert doc["findings"], "every finding is still displayed"
    assert all(f["below_floor"] is True for f in doc["findings"])
    assert all(f["below_floor"] == (f["confidence"] < floor) for f in doc["findings"])


@pytest.mark.parametrize("verb", ["list", "report"])
def test_b5_list_and_report_accept_floor_99(verb):
    code, out, err = _run(verb, LIVE, "--floor", 99)
    assert code == 0, err
    assert PHRASE not in err
    assert out.endswith("\n") and not out.endswith("\n\n")
    again = _run(verb, LIVE, "--floor", 99)
    assert again == (code, out, err)


def test_b5_prd_keeps_its_own_refusal(bed):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["c5"], "--prd", "--floor", 6)
    assert code == 2 and out == ""
    line = _last(err)
    assert line.startswith("Error: no PRESENT finding clears the confidence floor 6"), line
    assert PHRASE not in err


# --- behavior 6 ------------------------------------------------------------


@pytest.mark.parametrize("floor", (9, 5))
def test_b6_baseline_without_the_gate_keeps_its_refusal(bed, floor):
    code, out, err = _run("scan", bed["target"], "--gaps", bed["mix"],
                          "--baseline", bed["baseline"], "--floor", floor)
    assert code == 2 and out == ""
    line = _last(err)
    assert line.startswith("Error: --baseline requires --exit-code"), line
    assert PHRASE not in err


# --- behavior 7 ------------------------------------------------------------


def test_b7_the_published_ceiling_is_5_and_the_live_register_reaches_it():
    assert CONFIDENCE_MAX == 5
    derived = [confidence(g) for g in load_all(LIVE)]
    assert derived and max(derived) <= CONFIDENCE_MAX
    # The ceiling is reachable, so floor 5 is a real gate and not another off switch.
    assert max(derived) == CONFIDENCE_MAX


def test_b7_the_list_json_confidences_never_exceed_the_ceiling():
    code, out, err = _run("list", LIVE, "--json", "--floor", 0)
    assert code == 0, err
    confs = [r["confidence"] for r in json.loads(out)["records"]]
    assert confs and max(confs) == CONFIDENCE_MAX


def test_b7_the_refusal_numbers_follow_the_constant(bed):
    _, _, err = _run("scan", bed["target"], "--gaps", bed["c5"], "--exit-code",
                     "--floor", CONFIDENCE_MAX + 1)
    assert f"({CONFIDENCE_MAX})" in err and f"a floor of {CONFIDENCE_MAX} or less" in err
    code, _, _ = _run("scan", bed["target"], "--gaps", bed["c5"], "--exit-code",
                      "--floor", CONFIDENCE_MAX)
    assert code == 1


# --- behavior 8 ------------------------------------------------------------


def _table_rows(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("|")]


def test_b8_the_scan_row_states_the_refusal():
    rows = [r for r in _table_rows(CONTRACT.read_text(encoding="utf-8"))
            if r.startswith("| `radar scan ")]
    assert len(rows) == 1, rows
    assert PHRASE in rows[0]


def test_b8_the_exit_2_row_states_the_refusal():
    rows = [r for r in _table_rows(CONTRACT.read_text(encoding="utf-8"))
            if r.startswith("| `2` |")]
    assert len(rows) == 1, rows
    assert PHRASE in rows[0]
