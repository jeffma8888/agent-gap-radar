"""Iteration 70 behaviors: ONE canonical `UNKNOWN` gloss, true of BOTH its causes.

Iteration 63 gave `UNKNOWN` a second cause that inverts on the safety axis: cause one is
"the check could not run at all", cause two is "the check DID run, over a domain
`MAX_SCAN_FILES` cut, and will not vouch for the part it never read". Four non-test
surfaces still published only the first cause, two of them in bytes `radar scan` emits on
every run. This iteration makes `checks.UNKNOWN_MEANING` the single published copy of a
gloss true of both, has the rendered legend and the README cell read it, and retires the
section heading that positively asserted the half iteration 63 falsified.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors and from the published README; nothing here reads the
implementation source to DERIVE an expectation, and nothing reads the engineer's notes,
the reviewer's notes, a diff or a patch. Every behavioral claim is measured by CALLING a
public interface -- `checks.UNKNOWN_MEANING`, `checks.Verdict`, `cli.main`,
`scan.scan`/`render_scan`/`scan_json`, `registry.load_all` -- over fixtures this file
writes under pytest's `tmp_path`, or by reading a PUBLISHED document (`README.md`).

Behavior 4 is a SOURCE CENSUS, which the spec asks for by name. It reads
`src/agent_gap_radar/*.py` as DATA, counting two retired strings and one surviving one; no
expectation in this file was copied out of that source, and the census reports its own
domain size so an empty walk can never read as clean.

Structural notes, so this file cannot lie later:

* **Every wording pin points at ONE constant.** `UNKNOWN_MEANING` is the only verbatim new
  string asserted; the rendered cell, the README cell and `test_iter14`'s meaning table are
  all compared to THAT object, never to a second copy of its text. A literal here would
  reintroduce exactly the fifth copy this iteration removes.
* **The section heading is derived from the enum**, `f"## No verdict ({Verdict.UNKNOWN.value})"`,
  so a rename cannot leave the heading and the enum disagreeing with the suite still green.
* **The row ORDER of the legend is derived from `list(Verdict)`** rather than written down;
  only the four Meaning cells this iteration must NOT move are pinned as literals, because
  their being unchanged is the claim.
* **The truncation fixture asserts its own premise**: at a cap that admits the whole tree the
  tail marker IS found, so "not matched" at the small cap is attributable to the cut.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every fixture lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from _surface_contract import gfm_table
from agent_gap_radar import checks
from agent_gap_radar.checks import UNKNOWN_MEANING, Verdict
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import (CheckOutcome, Finding, ScanResult, render_scan,
                                 scan, scan_json)

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"
README_PATH = REPO_ROOT / "README.md"
CONTRACT_PATH = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: Markers carry the iteration number so no other fixture in the suite can collide.
MARK = "GAPMARK70"
MITIG = "MITIGMARK70"

#: Behavior 2 -- the two fixed lines of the rendered legend.
LEGEND_HEADER = "| Verdict | Count | Meaning |"
LEGEND_RULE = "| --- | --- | --- |"

#: Behavior 2 -- the four Meaning cells this iteration must leave byte-unchanged.
#: UNKNOWN is deliberately ABSENT: it is asserted equal to `UNKNOWN_MEANING`, never to a
#: literal, because a literal here would be the fifth copy this iteration removes.
UNMOVED_MEANINGS = {
    "PRESENT": "gap signature found in this target",
    "ABSENT": "a mitigation was positively identified",
    "NOT_APPLICABLE": "this gap cannot apply to this target",
    "MANUAL": "static analysis cannot decide; a human must answer",
}

#: Behavior 3 -- the README heading the pre-table prose line became, so `gfm_table` can
#: address a table that was previously unreachable ("no table follows heading").
README_VERDICT_HEADING = (
    "### Five verdicts, never collapsed -- collapsing them is how a tool starts lying")

#: Behavior 3 -- the prose line that heading replaced, one line for one line.
RETIRED_README_PROSE = (
    "Five verdicts, never collapsed, because collapsing them is how a tool starts lying:")

#: Behavior 4 -- the two retired strings and the one that must survive exactly once.
RETIRED_LOWER = "could not be run"
RETIRED_HEADING = "Could not run"
SURVIVING = "could not run"

#: Behavior 5 -- derived from the enum so the heading and the value cannot drift.
NO_VERDICT_HEADING = f"## No verdict ({Verdict.UNKNOWN.value})"


# ---------------------------------------------------------------------------
# Fixture builders. Registers and targets live under `tmp_path`; nothing under `gaps/`
# is read or edited to make an assertion true.
# ---------------------------------------------------------------------------

def _two_sided_record(gid: str, cid: str) -> dict:
    """A schema-valid record whose check carries BOTH signatures.

    `mitigated_when` is what makes the truncation route reachable: iteration 63 converts
    exactly the ABSENT verdict (mitigation found, `present_when` non-match over a CUT
    domain) into UNKNOWN, so a check with only `present_when` can never exercise cause (a).
    """
    return {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 5, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
        "check": {
            "id": cid, "rationale": "r", "manual_question": "q",
            "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                             "pattern": MARK},
            "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                               "pattern": MITIG},
            "fixtures": {"bad": {"a.py": MARK + "\n"}, "good": {"a.py": MITIG + "\n"}},
        },
    }


def _register(root: pathlib.Path, records: list[dict]) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return d


def _split_target(root: pathlib.Path, n: int = 7) -> pathlib.Path:
    """`n` python files: the MITIGATION inside any cap, the SIGNATURE in the last file.

    Names sort in creation order, so "the first MAX_SCAN_FILES in the existing order" is
    observable: `f01.py`'s mitigation is inside a cap of three, `f07.py`'s signature is not.
    """
    t = root / "target"
    t.mkdir(parents=True)
    for i in range(1, n + 1):
        body = MITIG if i == 1 else (MARK if i == n else "a clean line")
        (t / f"f{i:02d}.py").write_text(body + "\n", encoding="utf-8")
    return t


def _cli_scan(tmp_path, capsys, cap: int | None, monkeypatch) -> str:
    """`radar scan` stdout over the split target. Asserts rc 0 and a silent stderr."""
    reg = _register(tmp_path, [_two_sided_record("GAP-700", "CHK-700")])
    target = _split_target(tmp_path)
    if cap is not None:
        monkeypatch.setattr(checks, "MAX_SCAN_FILES", cap)
    rc = main(["scan", str(target), "--gaps", str(reg)])
    cap_out = capsys.readouterr()
    assert rc == 0, cap_out.err
    assert cap_out.err == "", "stdout carries only the document; stderr stays silent"
    return cap_out.out


def _legend_block(doc: str) -> list[str]:
    """The contiguous pipe-delimited block that begins at the legend header line."""
    lines = doc.split("\n")
    at = [i for i, line in enumerate(lines) if line == LEGEND_HEADER]
    assert len(at) == 1, (
        f"the verdict legend header must occur exactly once; found {len(at)}")
    block: list[str] = []
    cursor = at[0]
    while cursor < len(lines) and lines[cursor].startswith("|"):
        block.append(lines[cursor])
        cursor += 1
    return block


def _legend_meanings(doc: str) -> dict[str, str]:
    """`{verdict: meaning}` read out of the rendered legend, cells stripped."""
    rows = [[c.strip() for c in row.strip().strip("|").split("|")]
            for row in _legend_block(doc)[2:]]
    return {row[0]: row[2] for row in rows}


def _section(doc: str, heading: str) -> list[str]:
    """The lines under `heading`, up to the next `## ` heading. Heading must be unique."""
    lines = doc.split("\n")
    at = [i for i, line in enumerate(lines) if line == heading]
    assert len(at) == 1, f"heading {heading!r} occurs {len(at)} time(s), expected 1"
    out: list[str] = []
    for line in lines[at[0] + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    return out


# --- behavior 1: the canonical gloss exists, once ----------------------------------------

def test_b1_the_canonical_gloss_is_a_module_level_string_with_the_specified_wording():
    assert isinstance(UNKNOWN_MEANING, str)
    assert UNKNOWN_MEANING == (
        "no verdict: the check could not run, or its search was incomplete")


def test_b1_the_gloss_is_one_object_wherever_the_product_publishes_it():
    """`is`, not `==`: one shared object is the runtime form of "the literal lives once"."""
    from agent_gap_radar import scan as scan_module
    assert scan_module.UNKNOWN_MEANING is checks.UNKNOWN_MEANING


# --- behavior 2: the rendered legend derives from it, nothing else in the table moves ----

@pytest.mark.parametrize("cap,label", [(3, "cut"), (7, "whole"), (None, "uncapped")])
def test_b2_the_legend_is_seven_lines_in_verdict_declaration_order(
        tmp_path, capsys, monkeypatch, cap, label):
    doc = _cli_scan(tmp_path, capsys, cap, monkeypatch)
    block = _legend_block(doc)
    assert len(block) == 7, (
        f"{label}: header, separator and exactly 5 verdict rows -- no 8th row; got {block}")
    assert block[0] == LEGEND_HEADER
    assert block[1] == LEGEND_RULE
    rows = [[c.strip() for c in row.strip().strip("|").split("|")] for row in block[2:]]
    assert [row[0] for row in rows] == [v.value for v in Verdict], (
        f"{label}: rows follow `Verdict` declaration order")
    assert all(len(row) == 3 for row in rows), f"{label}: every row has three cells"


@pytest.mark.parametrize("cap,label", [(3, "cut"), (7, "whole"), (None, "uncapped")])
def test_b2_the_unknown_meaning_cell_equals_the_constant(
        tmp_path, capsys, monkeypatch, cap, label):
    meanings = _legend_meanings(_cli_scan(tmp_path, capsys, cap, monkeypatch))
    assert meanings[Verdict.UNKNOWN.value] == UNKNOWN_MEANING, (
        f"{label}: the rendered cell must READ the constant, not a copy of its text")


@pytest.mark.parametrize("cap", [3, 7, None])
def test_b2_the_other_four_meaning_cells_are_byte_unchanged(tmp_path, capsys, monkeypatch, cap):
    meanings = _legend_meanings(_cli_scan(tmp_path, capsys, cap, monkeypatch))
    for verdict, text in UNMOVED_MEANINGS.items():
        assert meanings[verdict] == text, f"{verdict}'s gloss is out of scope this iteration"
    assert set(meanings) == {v.value for v in Verdict} and len(meanings) == 5, (
        "two-sided: nothing missing from the legend and nothing invented")


# --- behavior 3: the front door derives from the same constant, and is addressable -------

def _readme_table():
    return gfm_table(README_PATH.read_text(encoding="utf-8"), README_VERDICT_HEADING)


def test_b3_the_readme_verdict_table_is_addressable_by_the_shipped_reader():
    """Before this iteration `gfm_table` raised "no table follows heading" here."""
    table = _readme_table()
    assert table.header == ("Verdict", "Meaning")
    assert len(table.rows) == 5, f"five verdicts, five rows; got {table.rows}"


def test_b3_the_readme_unknown_cell_equals_the_constant():
    table = _readme_table()
    cells = {row[0]: row[1] for row in table.rows}
    assert cells[f"`{Verdict.UNKNOWN.value}`"] == UNKNOWN_MEANING, (
        "the front door must publish the constant's value, not a hand-copy")


def test_b3_the_readme_verdict_column_is_exactly_the_enum_two_sided():
    table = _readme_table()
    assert set(table.column("Verdict")) == {f"`{v.value}`" for v in Verdict}, (
        "as a SET: nothing missing and nothing invented, with no row order pinned")


def test_b3_the_replaced_prose_line_is_gone_from_the_readme():
    text = README_PATH.read_text(encoding="utf-8")
    assert text.count(RETIRED_README_PROSE) == 0, (
        "one line for one line: the prose line BECAME the heading, it was not duplicated")
    assert text.count(README_VERDICT_HEADING) == 1


# --- behavior 4: the retired phrase is gone; the new wording lives in one place ----------

def _census(needle: str, paths: list[pathlib.Path]) -> tuple[int, int]:
    """`(occurrences, files_examined)`. Whole-file counts, never per line.

    A per-line scan over a hard-wrapped document is blind to any phrase a newline splits,
    which is how a green census can be run over a document that carries the very defect.
    The file count is returned so an empty domain can never be reported as clean.
    """
    total = 0
    for path in paths:
        total += path.read_text(encoding="utf-8").count(needle)
    return total, len(paths)


def _src_files() -> list[pathlib.Path]:
    return sorted(SRC_DIR.glob("*.py"))


def _wide_domain() -> list[pathlib.Path]:
    """`src/` plus the two published documents. `tests/` is EXCLUDED on purpose: this file
    must be free to spell the retired phrases in order to search for them."""
    return _src_files() + [README_PATH, CONTRACT_PATH]


def test_b4_the_census_helper_is_two_sided(tmp_path):
    """The brake proved on a known-bad sample before its silence is credited anywhere."""
    planted = tmp_path / "planted.py"
    planted.write_text(f"# a gloss saying the check {RETIRED_LOWER} here\n", encoding="utf-8")
    assert _census(RETIRED_LOWER, [planted]) == (1, 1)
    clean = tmp_path / "clean.py"
    clean.write_text("# nothing of the sort\n", encoding="utf-8")
    assert _census(RETIRED_LOWER, [clean]) == (0, 1)


@pytest.mark.parametrize("needle", [RETIRED_LOWER, RETIRED_HEADING])
def test_b4_both_retired_strings_are_gone_from_src_and_from_both_documents(needle):
    count, files = _census(needle, _wide_domain())
    assert files >= 3, f"anti-vacuity: the census examined only {files} file(s)"
    assert count == 0, f"{needle!r} still occurs {count} time(s) in the published domain"


def test_b4_the_surviving_wording_occurs_exactly_once_under_src():
    count, files = _census(SURVIVING, _src_files())
    assert files >= 1, "anti-vacuity: no source file was examined"
    assert count == 1, (
        f"{SURVIVING!r} must live at exactly ONE source line under src/; found {count}")


def test_b4_that_one_occurrence_is_the_line_that_defines_the_constant():
    hits = [(path.name, i, line)
            for path in _src_files()
            for i, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1)
            if SURVIVING in line]
    assert len(hits) == 1, f"expected one line, got {hits}"
    name, lineno, line = hits[0]
    assert "UNKNOWN_MEANING" in line, (
        f"{name}:{lineno} spells the gloss without defining the constant: {line!r}")


def test_b4_the_constant_is_the_only_copy_anywhere_in_the_wide_domain():
    """The value itself, not just the retired wording: a fifth copy is the failure mode."""
    count, _files = _census(UNKNOWN_MEANING, _src_files())
    assert count == 1, f"the gloss's full text occurs {count} time(s) under src/"


# --- behavior 5: the section heading names no cause --------------------------------------

def test_b5_the_unknown_section_heading_is_derived_and_names_no_cause(
        tmp_path, capsys, monkeypatch):
    doc = _cli_scan(tmp_path, capsys, 3, monkeypatch)
    assert doc.count(NO_VERDICT_HEADING) == 1, (
        f"the document must carry {NO_VERDICT_HEADING!r} exactly once")
    assert doc.count(f"## {RETIRED_HEADING}") == 0, (
        "the retired heading asserted the one cause iteration 63 falsified")


def test_b5_every_unknown_finding_carries_its_own_reason_verbatim(
        tmp_path, capsys, monkeypatch):
    reg = _register(tmp_path, [_two_sided_record("GAP-700", "CHK-700")])
    target = _split_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 3)
    result = scan(load_all(reg), target)
    doc = render_scan(result)
    unknown = [f for f in result.findings if f.outcome.verdict is Verdict.UNKNOWN]
    assert unknown, "anti-vacuity: the fixture produced no UNKNOWN finding at all"
    section = "\n".join(_section(doc, NO_VERDICT_HEADING))
    for finding in unknown:
        assert finding.outcome.reason, "premise: an UNKNOWN verdict carries a reason"
        assert finding.outcome.reason in section, (
            f"{finding.gap.id}'s reason is not rendered verbatim: "
            f"{finding.outcome.reason!r}")


# --- behavior 6: BOTH causes reach that section, distinguished by their reason -----------

def test_b6a_an_incomplete_search_reaches_the_section_naming_the_cap_and_both_counts(
        tmp_path, capsys, monkeypatch):
    doc = _cli_scan(tmp_path, capsys, 3, monkeypatch)
    section = "\n".join(_section(doc, NO_VERDICT_HEADING))
    assert "GAP-700" in section, "the cut record must be reported under the section"
    assert "MAX_SCAN_FILES" in section, "the reason must name the cap that cut the domain"
    assert "3" in section and "7" in section, (
        f"the reason must name the cap applied and the total the domain held: {section!r}")


def test_b6a_the_premise_holds_the_marker_is_findable_once_the_domain_is_whole(
        tmp_path, capsys, monkeypatch):
    """The control: identical fixture, cap EQUAL to the tree, so the cut is what hid it.

    MEASURED here rather than assumed: the renderer OMITS the no-verdict section entirely
    when no finding is UNKNOWN, so the control asserts its ABSENCE plus the escalation that
    replaced it. The legend row, by contrast, is published on every run at a count of zero,
    which is why behavior 2 is parametrized over this cap as well.
    """
    doc = _cli_scan(tmp_path, capsys, 7, monkeypatch)
    assert NO_VERDICT_HEADING not in doc, (
        "whole, nothing is UNKNOWN, so the section has nothing to report")
    manual = "\n".join(_section(doc, "## Needs a human answer (MANUAL)"))
    assert "GAP-700" in manual, "premise: the tail signature IS findable at a cap of 7"


def test_b6b_a_check_that_could_not_run_reaches_the_same_section_with_its_own_reason(
        tmp_path):
    """The in-memory route, and it is the HONEST one rather than a convenience: a malformed
    pattern is rejected at load time, so cause (b) is unreachable through a register file.
    """
    reg = _register(tmp_path, [_two_sided_record("GAP-701", "CHK-701")])
    gap = load_all(reg)[0]
    reason = "invalid pattern '(': missing )"
    result = ScanResult(tmp_path / "target", [Finding(gap, CheckOutcome(
        Verdict.UNKNOWN, reason=reason))], [])
    doc = render_scan(result)
    section = "\n".join(_section(doc, NO_VERDICT_HEADING))
    assert "GAP-701" in section
    assert reason in section, f"the reason must render verbatim; section was {section!r}"
    assert _legend_meanings(doc)[Verdict.UNKNOWN.value] == UNKNOWN_MEANING, (
        "the shortened legend delegates the CAUSE to the reason, so both routes share it")


def test_b6_the_two_causes_are_distinguishable_only_by_their_reason(tmp_path, capsys,
                                                                   monkeypatch):
    """Same heading, same legend cell, different reason -- which is the delegation working."""
    cut = _cli_scan(tmp_path, capsys, 3, monkeypatch)
    reg = _register(tmp_path / "second", [_two_sided_record("GAP-702", "CHK-702")])
    gap = load_all(reg)[0]
    broken = render_scan(ScanResult(tmp_path / "target", [Finding(
        gap, CheckOutcome(Verdict.UNKNOWN, reason="invalid pattern '(': missing )"))], []))
    for doc in (cut, broken):
        assert NO_VERDICT_HEADING in doc
        assert _legend_meanings(doc)[Verdict.UNKNOWN.value] == UNKNOWN_MEANING
    assert "MAX_SCAN_FILES" in cut and "MAX_SCAN_FILES" not in broken


# --- behavior 7: the one-newline and determinism contracts hold --------------------------

def test_b7_the_document_ends_in_exactly_one_newline(tmp_path, capsys, monkeypatch):
    doc = _cli_scan(tmp_path, capsys, 3, monkeypatch)
    assert doc.endswith("\n") and not doc.endswith("\n\n"), repr(doc[-30:])
    assert doc.split("\n")[-2].strip() != "", "the last line before the tail is non-blank"


def test_b7_two_identical_invocations_are_byte_identical(tmp_path, capsys, monkeypatch):
    reg = _register(tmp_path, [_two_sided_record("GAP-700", "CHK-700")])
    target = _split_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 3)
    gaps = load_all(reg)
    first = render_scan(scan(gaps, target))
    assert render_scan(scan(gaps, target)) == first, "the scan document must be reproducible"


# --- acceptance criterion: `scan --json` is untouched by this iteration -----------------

def test_the_json_payload_carries_neither_the_retired_phrase_nor_the_new_constant(
        tmp_path, monkeypatch):
    reg = _register(tmp_path, [_two_sided_record("GAP-700", "CHK-700")])
    target = _split_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 3)
    payload = scan_json(scan(load_all(reg), target))
    assert json.loads(payload)["findings"], "anti-vacuity: the payload has no findings"
    for needle in (RETIRED_LOWER, RETIRED_HEADING, UNKNOWN_MEANING):
        assert needle not in payload, (
            f"the gloss is markdown-only; {needle!r} must not reach the JSON payload")
    assert Verdict.UNKNOWN.value in payload, "premise: the payload does report the verdict"


# --- behavior 2, widened: the legend is bytes the tool emits on EVERY scan ---------------

def test_b2_the_legend_carries_the_constant_over_the_committed_register_too():
    """The spec's claim is about bytes emitted on EVERY scan, so one live invocation is
    part of the claim. Drift-proof: the legend is fixed no matter which records exist, so a
    register grown by an unattended research pass cannot red this."""
    from agent_gap_radar.registry import load_all as _load_all
    doc = render_scan(scan(_load_all(REPO_ROOT / "gaps"), REPO_ROOT))
    assert len(_legend_block(doc)) == 7
    meanings = _legend_meanings(doc)
    assert meanings[Verdict.UNKNOWN.value] == UNKNOWN_MEANING
    for verdict, text in UNMOVED_MEANINGS.items():
        assert meanings[verdict] == text


# --- behavior 5, widened: EACH bullet carries ITS OWN reason -----------------------------

def test_b5_two_unknown_findings_each_carry_their_own_reason_not_one_shared_gloss(tmp_path):
    """Plural, because a single-finding fixture cannot tell "the reason is rendered" from
    "some reason is rendered": with two, a shared or swapped gloss is visible."""
    reg = _register(tmp_path, [_two_sided_record("GAP-703", "CHK-703"),
                               _two_sided_record("GAP-704", "CHK-704")])
    gaps = load_all(reg)
    reasons = {"GAP-703": "invalid pattern '(': missing )",
               "GAP-704": "present_when read only the first 3 of 7 files (MAX_SCAN_FILES)"}
    findings = [Finding(g, CheckOutcome(Verdict.UNKNOWN, reason=reasons[g.id])) for g in gaps]
    section = _section(render_scan(ScanResult(tmp_path / "target", findings, [])),
                       NO_VERDICT_HEADING)
    body = "\n".join(section)
    for gid, reason in reasons.items():
        assert gid in body, f"{gid} is missing from the no-verdict section"
        assert reason in body, f"{gid}'s own reason is not rendered verbatim"
    bullets = [line for line in section if line.startswith("- ")]
    assert len(bullets) == 2, f"one bullet per UNKNOWN finding; got {bullets}"
    for gid, reason in reasons.items():
        owner = [b for b in bullets if gid in b]
        assert len(owner) == 1 and reason in owner[0], (
            f"{gid}'s bullet must carry ITS OWN reason, not a neighbour's: {owner}")


# --- behavior 6, the routing PREMISE, verified rather than inherited from the spec --------

def test_b6b_a_malformed_pattern_cannot_enter_a_register_which_is_why_b_is_in_memory(
        tmp_path):
    """The spec says cause (b) is unreachable through a register file because patterns are
    compiled at load time. Measured here rather than taken on trust: if this ever stopped
    raising, the in-memory route above would silently become a convenience instead of the
    only honest route, and behavior 6(b) would be testable end to end. The MESSAGE is
    deliberately not pinned -- only the refusal and the fact that it names the pattern.
    """
    from agent_gap_radar.registry import RegistryError
    record = _two_sided_record("GAP-798", "CHK-798")
    record["check"]["present_when"]["pattern"] = "("
    reg = _register(tmp_path, [record])
    with pytest.raises(RegistryError) as excinfo:
        load_all(reg)
    assert "(" in str(excinfo.value), (
        f"the refusal must name the offending pattern; got {excinfo.value}")
