"""Iteration 02 behaviors: `radar scan --prd` honours the register's confidence floor.

Black-box. Every assertion drives the public CLI entry point (`main`) or the public
`scan()` API and reads observable stdout / stderr / exit code. Nothing here reads the
implementation source, and no assertion encodes an implementation detail.

The floor is `2`, the register default that `radar prd` already enforces (pinned by
tests/test_scoring.py via `rank`, and by tests/test_cli.py's
`test_prd_exits_2_when_nothing_clears_the_floor`). It is spelled once here as `FLOOR`
and interpolated into every expected message, so a future change to the default breaks
one constant rather than nine string literals.

Priorities below are DERIVED, not copied from the tool: priority = (3*severity +
2*frequency + tractability) / 3, rounded to one decimal (pinned by
tests/test_scoring.py). Confidence is the strongest evidence class's ceiling, so a lone
`model-output` citation scores 0 -- below the floor -- and a lone `first-party-field`
citation scores 5.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main

#: The register default confidence floor. See module docstring.
FLOOR = 2

#: Planted in the target tree; the fixture checks fire on exactly this token, so
#: "PRESENT" is a property of the fixture and never of the published register.
MARKER = "GAPRADAR_ITER02_MARKER"


# ---------------------------------------------------------------------------
# Fixture builders. Registers and targets are built in `tmp_path`; no committed
# gap record is read or edited to make an assertion true.
# ---------------------------------------------------------------------------

def _record(gid, sev=3, freq=3, tract=3, classes=("first-party-field",), check_id=None):
    """A schema-valid record. `check_id=None` means no automated check at all."""
    rec = {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}
                     for c in classes],
    }
    if check_id is not None:
        rec["check"] = _check(check_id)
    return rec


def _check(cid):
    """Fires PRESENT iff MARKER appears in the target's tracked python files.

    `models.Check` requires two-sided fixtures whenever `present_when` is set, so
    the bad tree carries the marker and the good tree does not.
    """
    return {
        "id": cid,
        "rationale": "r",
        "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": MARKER},
        "fixtures": {"bad": {"a.py": MARKER + "\n"}, "good": {"a.py": "clean\n"}},
    }


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


def _note(gid, priority, confidence):
    return (f"Note: skipped {gid} (priority {priority}, confidence {confidence}) "
            f"-- below the confidence floor {FLOOR}.\n")


# --- registers -------------------------------------------------------------
#
# MIXED: two below-floor PRESENT findings ABOVE the first one that clears the floor,
# and one below-floor PRESENT finding BELOW it. The last one is the control for
# behavior 3's exclusion clause: the floor cost nothing there, so it earns no line.
MIXED = [
    _record("GAP-500", 5, 5, 5, ("model-output",), "CHK-500"),      # p 10.0  c0
    _record("GAP-503", 5, 4, 4, ("model-output",), "CHK-503"),      # p  9.0  c0
    _record("GAP-501", 5, 3, 5, ("first-party-field",), "CHK-501"),  # p  8.7  c5  <- pick
    _record("GAP-502", 1, 1, 1, ("model-output",), "CHK-502"),      # p  2.0  c0
]
MIXED_ORDER = ["GAP-500", "GAP-503", "GAP-501", "GAP-502"]

#: Three findings at one priority: the tie-break must be gap id ascending among the
#: findings that CLEAR the floor, not "first in PRESENT order".
TIED = [
    _record("GAP-600", 4, 4, 4, ("model-output",), "CHK-600"),       # p 8.0  c0
    _record("GAP-602", 4, 4, 4, ("first-party-field",), "CHK-602"),  # p 8.0  c5
    _record("GAP-601", 4, 4, 4, ("first-party-field",), "CHK-601"),  # p 8.0  c5  <- pick
    _record("GAP-603", 4, 4, 4, ("model-output",), "CHK-603"),       # p 8.0  c0
]
TIED_ORDER = ["GAP-600", "GAP-601", "GAP-602", "GAP-603"]

#: The highest-priority record is below the floor AND carries no check, so it is not
#: a PRESENT finding at all. Behavior 3 says one line per below-floor PRESENT finding,
#: so this one must earn no line: it was never a candidate the floor took away.
MANUAL_TOP = [
    _record("GAP-400", 5, 5, 5, ("model-output",), None),            # p 10.0  c0  no check
    _record("GAP-401", 5, 4, 4, ("model-output",), "CHK-401"),       # p  9.0  c0  PRESENT
    _record("GAP-402", 5, 3, 5, ("first-party-field",), "CHK-402"),  # p  8.7  c5  <- pick
]

#: Nothing clears the floor. Two records, so the id list's separator is exercised.
WEAK = [
    _record("GAP-700", 5, 5, 5, ("model-output",), "CHK-700"),  # p 10.0  c0
    _record("GAP-701", 5, 4, 4, ("model-output",), "CHK-701"),  # p  9.0  c0
]

#: The top PRESENT finding already clears the floor: the no-regression case.
CLEARS = [
    _record("GAP-800", 5, 3, 5, ("first-party-field",), "CHK-800"),  # p 8.7  c5
    _record("GAP-801", 1, 1, 1, ("first-party-field",), "CHK-801"),  # p 2.0  c5
]

#: Includes a below-floor record, so behavior 5 also proves the floor notice does
#: not leak into the no-PRESENT path.
UNFIRED = [
    _record("GAP-900", 5, 5, 5, ("model-output",), "CHK-900"),
    _record("GAP-901", 5, 3, 5, ("first-party-field",), "CHK-901"),
]


@pytest.fixture()
def target(tmp_path):
    """A target that trips every fixture check."""
    return _target(tmp_path / "hit")


@pytest.fixture()
def clean_target(tmp_path):
    """A target that trips none of them, so every finding is MANUAL."""
    return _target(tmp_path / "miss", "nothing interesting")


def _reg(tmp_path, name, records):
    return _write_register(tmp_path / name, records)


# ---------------------------------------------------------------------------
# Behavior 1 -- no regression when the top PRESENT finding already clears the floor.
# ---------------------------------------------------------------------------

def test_b1_top_finding_above_floor_is_selected_and_stderr_stays_silent(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "clears", CLEARS)
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == "", "nothing was passed over, so nothing may be announced"
    doc = json.loads(captured.out)
    assert doc["sourceGap"]["id"] == "GAP-800"
    assert doc["sourceGap"]["confidence"] >= FLOOR


def test_b1_stdout_carries_only_the_document(tmp_path, target, capsys):
    reg = _reg(tmp_path, "clears", CLEARS)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    out = capsys.readouterr().out
    assert "Note:" not in out and "Error:" not in out
    assert out.endswith("}\n") and not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# Behavior 2 -- a below-floor top finding is passed over, not built against.
# ---------------------------------------------------------------------------

def test_b2_below_floor_top_finding_is_not_the_prd_source(tmp_path, target, capsys):
    """The shipped defect: the PRD named a `model-output`-only record at confidence 0."""
    reg = _reg(tmp_path, "mixed", MIXED)
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert rc == 0
    doc = json.loads(captured.out)
    assert doc["sourceGap"]["id"] == "GAP-501"
    assert doc["sourceGap"]["confidence"] == 5
    assert doc["sourceGap"]["id"] != "GAP-500", "built against a below-floor finding"


def test_b2_selection_breaks_priority_ties_by_gap_id_ascending(
        tmp_path, target, capsys):
    """Among findings that CLEAR the floor -- not merely the first PRESENT one."""
    reg = _reg(tmp_path, "tied", TIED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sourceGap"]["id"] == "GAP-601"


def test_b2_stdout_is_only_the_document_when_a_finding_was_skipped(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    out = capsys.readouterr().out
    assert "Note:" not in out, "the notice belongs on stderr; a consumer parses stdout"
    assert out.endswith("}\n") and not out.endswith("\n\n")
    json.loads(out)


# ---------------------------------------------------------------------------
# Behavior 3 -- the pass-over is announced, never silent.
# ---------------------------------------------------------------------------

def test_b3_stderr_names_every_skipped_finding_ranked_above_the_selection(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    err = capsys.readouterr().err
    assert err == _note("GAP-500", "10.0", 0) + _note("GAP-503", "9.0", 0)


def test_b3_a_below_floor_finding_ranked_under_the_selection_earns_no_line(
        tmp_path, target, capsys):
    """GAP-502 is below the floor too, but the floor cost nothing there."""
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    err = capsys.readouterr().err
    assert "GAP-502" not in err
    assert err.count("Note: skipped") == 2


def test_b3_a_below_floor_finding_tying_the_selection_by_priority_earns_no_line(
        tmp_path, target, capsys):
    """The boundary a naive `priority >= selected.priority` test would get wrong.

    GAP-603 is below the floor and has the SAME priority as the selected GAP-601, but
    it sorts after it by id, so in PRESENT ordering it ranks BELOW the selection and
    the floor cost nothing there. Only GAP-600 earns a line.
    """
    reg = _reg(tmp_path, "tied", TIED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    err = capsys.readouterr().err
    assert err == _note("GAP-600", "8.0", 0)
    assert "GAP-603" not in err


def test_b3_one_line_per_skipped_finding_in_present_order(tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    lines = capsys.readouterr().err.splitlines()
    assert [ln.split()[2] for ln in lines] == ["GAP-500", "GAP-503"]


def test_b3_priority_is_shown_to_one_decimal(tmp_path, target, capsys):
    """`10` or `10.00` would break a consumer that greps the notice."""
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    assert "(priority 10.0, confidence 0)" in capsys.readouterr().err


def test_b3_a_below_floor_finding_that_is_not_present_earns_no_line(
        tmp_path, target, capsys):
    """The clause is "below-floor PRESENT finding", not "below-floor record".

    GAP-400 outranks everything and is below the floor, but it carries no check, so it
    is not a PRESENT finding and the floor never took it away. An implementation that
    walked the REGISTER instead of the findings would name it here. The verdicts are
    read from `--json` in the same test rather than assumed, so the premise is measured.
    """
    reg = _reg(tmp_path, "manual_top", MANUAL_TOP)
    assert main(["scan", str(target), "--gaps", str(reg), "--json"]) == 0
    verdicts = {f["gap_id"]: f["verdict"]
                for f in json.loads(capsys.readouterr().out)["findings"]}
    # Measured, not assumed: a checkless record yields no finding AT ALL here, so it is
    # absent from this mapping rather than carrying a non-PRESENT verdict. Either way it
    # is not a PRESENT finding, which is the only property behavior 3 turns on.
    assert verdicts.get("GAP-400") != "PRESENT", "premise: the top record is no finding"
    assert verdicts["GAP-401"] == "PRESENT" and verdicts["GAP-402"] == "PRESENT"

    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["sourceGap"]["id"] == "GAP-402"
    assert captured.err == _note("GAP-401", "9.0", 0)
    assert "GAP-400" not in captured.err


# ---------------------------------------------------------------------------
# Behavior 4 -- refusal when nothing clears the floor.
# ---------------------------------------------------------------------------

def test_b4_refusal_exits_2_with_the_exact_message(tmp_path, target, capsys):
    reg = _reg(tmp_path, "weak", WEAK)
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert captured.out == "", "a refusal must not emit a PRD for a build loop to run"
    assert rc == 2
    assert captured.err == (
        f"Error: no PRESENT finding clears the confidence floor {FLOOR}: "
        "GAP-700 (confidence 0), GAP-701 (confidence 0). Strengthen the evidence, "
        "or name it explicitly with 'radar prd --gap GAP-700'.\n"
    )


def test_b4_the_suggestion_names_the_highest_ranked_below_floor_finding(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "weak", WEAK)
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("Error: ")
    assert err.endswith("'radar prd --gap GAP-700'.\n")
    assert err.index("GAP-700 (confidence 0)") < err.index("GAP-701 (confidence 0)")


def test_b4_a_single_below_floor_finding_needs_no_separator(tmp_path, target, capsys):
    reg = _reg(tmp_path, "one", [WEAK[0]])
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 2
    assert capsys.readouterr().err == (
        f"Error: no PRESENT finding clears the confidence floor {FLOOR}: "
        "GAP-700 (confidence 0). Strengthen the evidence, or name it explicitly "
        "with 'radar prd --gap GAP-700'.\n"
    )


# ---------------------------------------------------------------------------
# Behavior 5 -- the no-PRESENT-finding message is untouched.
# ---------------------------------------------------------------------------

def test_b5_no_present_finding_keeps_its_own_message(tmp_path, clean_target, capsys):
    reg = _reg(tmp_path, "unfired", UNFIRED)
    rc = main(["scan", str(clean_target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert rc == 2
    assert captured.err == (
        "Error: no PRESENT finding to build against; run without --prd to see "
        "MANUAL questions\n"
    )


def test_b5_the_floor_notice_does_not_leak_into_the_no_present_path(
        tmp_path, clean_target, capsys):
    """The register here holds a below-floor record, and it is still not the story."""
    reg = _reg(tmp_path, "unfired", UNFIRED)
    assert main(["scan", str(clean_target), "--gaps", str(reg), "--prd"]) == 2
    err = capsys.readouterr().err
    assert "Note:" not in err
    assert "confidence floor" not in err


# ---------------------------------------------------------------------------
# Behavior 6 -- the scan report is unchanged, including its below-floor rows.
# Filtering the REPORT would re-create the silent drop VISION.md forbids.
# ---------------------------------------------------------------------------

def test_b6_markdown_report_still_lists_the_below_floor_present_finding(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    rc = main(["scan", str(target), "--gaps", str(reg)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    for gid in MIXED_ORDER:
        assert gid in captured.out, f"{gid} vanished from the report"
    assert "evidence confidence 0" in captured.out, "confidence is not shown"


def test_b6_json_report_still_carries_every_present_finding_with_confidence(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    rc = main(["scan", str(target), "--gaps", str(reg), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    findings = json.loads(captured.out)["findings"]
    assert [f["gap_id"] for f in findings] == MIXED_ORDER
    by_id = {f["gap_id"]: f for f in findings}
    assert by_id["GAP-500"]["verdict"] == "PRESENT"
    assert by_id["GAP-500"]["confidence"] == 0
    assert by_id["GAP-500"]["priority"] == 10.0
    assert "score" not in by_id["GAP-500"], "a blended score would launder the invariant"


@pytest.mark.parametrize("argv_extra", [[], ["--json"]])
def test_b6_both_renderers_are_byte_stable_across_runs(
        argv_extra, tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), *argv_extra]) == 0
    first = capsys.readouterr().out
    assert main(["scan", str(target), "--gaps", str(reg), *argv_extra]) == 0
    assert capsys.readouterr().out == first


@pytest.mark.parametrize("argv_extra", [[], ["--json"]])
def test_b6_renderers_end_in_exactly_one_newline(
        argv_extra, tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    assert main(["scan", str(target), "--gaps", str(reg), *argv_extra]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# Behavior 7 -- `ScanResult.actionable` keeps its meaning. The floor governs
# SELECTION for `--prd`, never what the scan found.
# ---------------------------------------------------------------------------

def test_b7_actionable_still_returns_below_floor_present_findings(tmp_path, target):
    from agent_gap_radar.registry import load_all
    from agent_gap_radar.scan import scan

    reg = _reg(tmp_path, "mixed", MIXED)
    result = scan(load_all(reg), target)
    assert [f.gap.id for f in result.actionable] == MIXED_ORDER
    assert "GAP-500" in [f.gap.id for f in result.actionable]


def test_b7_actionable_is_ordered_by_priority_then_id(tmp_path, target):
    from agent_gap_radar.registry import load_all
    from agent_gap_radar.scan import scan

    reg = _reg(tmp_path, "tied", TIED)
    result = scan(load_all(reg), target)
    assert [f.gap.id for f in result.actionable] == TIED_ORDER


# ---------------------------------------------------------------------------
# Behavior 8 -- `radar prd` is untouched, including its explicit escape hatch.
# ---------------------------------------------------------------------------

def test_b8_prd_still_refuses_with_its_own_message(tmp_path, capsys):
    reg = _reg(tmp_path, "weak", WEAK)
    rc = main(["prd", str(reg)])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert rc == 2
    assert captured.err == "Error: no gap clears the confidence floor\n"


def test_b8_an_explicitly_named_below_floor_gap_still_yields_a_prd(tmp_path, capsys):
    """A human named it, so the floor steps aside. That escape hatch must survive."""
    reg = _reg(tmp_path, "weak", WEAK)
    rc = main(["prd", str(reg), "--gap", "GAP-700"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert json.loads(captured.out)["sourceGap"]["id"] == "GAP-700"


# ---------------------------------------------------------------------------
# Behavior 9 -- no new flag on `scan`. The floor here is the register default,
# matching the flagless `prd`, not the `--floor` of `list` / `report`.
# ---------------------------------------------------------------------------

def test_b9_scan_rejects_a_floor_flag(tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(target), "--gaps", str(reg), "--floor", "0"])
    assert exc.value.code == 2
    assert "unrecognized arguments: --floor 0" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Behavior 10 -- `--prd` help names the floor.
#
# Parametrised over terminal widths on purpose: argparse wraps help text on
# whitespace, so a phrase asserted mid-sentence survives at width 80 and breaks at
# 60. Asserting it at four widths makes the pin independent of the wrap point.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("columns", ["33", "60", "80", "120"])
def test_b10_scan_help_documents_that_prd_selection_is_gated(
        columns, monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", columns)
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--help"])
    assert exc.value.code == 0
    assert "confidence floor" in capsys.readouterr().out, f"at COLUMNS={columns}"


# ---------------------------------------------------------------------------
# Flag combination the spec does not decide: `--prd --json`. Rather than freeze an
# undecided design, this pins only what is spec-derived either way -- stdout is ONE
# document, and no below-floor finding may reach a PRD through the combination.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flags", [["--prd", "--json"], ["--json", "--prd"]])
def test_flag_combination_never_launders_a_below_floor_selection(
        flags, tmp_path, target, capsys):
    reg = _reg(tmp_path, "mixed", MIXED)
    rc = main(["scan", str(target), "--gaps", str(reg), *flags])
    out = capsys.readouterr().out
    assert rc == 0
    doc = json.loads(out)
    assert out.endswith("}\n") and not out.endswith("\n\n")
    if "sourceGap" in doc:
        assert doc["sourceGap"]["confidence"] >= FLOOR
        assert doc["sourceGap"]["id"] == "GAP-501"
