"""Iteration 83 behaviors: `radar report` publishes how old each record's newest citation is.

The feature under test: one additional level-2 section, `## Evidence age`, listing every
record whose newest citation is more than 365 days older than the register's own newest
citation date -- a DISPLAY, never an input to any score, and never a reason to drop a
record.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, `tools/*.py` text, the
engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. The oracles are

* the spec's own verbatim lines, quoted once each as a module constant, and
* the document bytes `render.radar_report` and `cli.main(["report", ...])` write, sliced by
  a section splitter written here from the spec's words.

WHY EVERY REGISTER HERE IS SYNTHETIC
The repository's own `gaps/` register is grown by an unattended research pass, so an
assertion keyed on a live id, a live count or a live citation date would go red against a
CORRECT register days from now. Every register in this module is built under pytest's
`tmp_path`, and every date is chosen here so the arithmetic has a fixed answer.

STRUCTURAL NOTES, so this file cannot lie later:

* **The anchor is proved DERIVED, not literal.** Behavior 2 renders two registers whose
  maximum citation dates differ and asserts the rendered anchor follows the data, and one
  fixture puts the newest citation LAST inside a three-citation record so a first-citation
  implementation reds.
* **The 365-day threshold is proved two-sided**: a record at exactly 365 days must be
  ABSENT from the table and a record at 366 days must be PRESENT, over the same fixture
  shape, so a `>=` comparison cannot pass.
* **Behavior 7 asserts its own premise.** The two renders it compares must differ SOMEWHERE
  (inside `## Evidence age`) before their `## Ranked gaps` sections being byte-identical is
  evidence of anything; a fixture that changed nothing would otherwise report a pass while
  measuring nothing.
* **Behavior 8 does not restate iteration 17's pins.** It imports that module's committed
  literals and re-measures them, so this file cannot silently re-baseline the very pin whose
  job is to catch unrelated movement.
* **No absolute machine path and no personal or employer identifier appears here**; every
  fixture is written under `tmp_path`.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report

RANKED = "## Ranked gaps"
BY_LAYER = "## By layer"
EVIDENCE_AGE = "## Evidence age"
BELOW_FLOOR = "## Below confidence floor"

#: Behavior 2 quotes this line verbatim except for the date. Kept as ONE template so the
#: test cannot drift from the spec by a hyphen.
ANCHOR_TEMPLATE = (
    "Ages are measured against {date}, the newest citation date in this register, "
    "so the same register always renders the same bytes; no clock is read."
)

#: Behavior 3 quotes this line verbatim.
PURPOSE_LINE = (
    "An old citation is not a closed gap: evidence for a durable property does not weaken "
    "with age. This says where to go and CHECK, not what to delete and not what to pad "
    "with a fresher link."
)

#: Behavior 4 fixes the table header.
TABLE_HEADER = "| ID | Newest citation | Age (days) | Title |"

#: Behaviors 5 and 6 reuse the convention `## Ranked gaps` already uses for an empty body.
NONE_FOUND = "None found."

#: The threshold behavior 4 states. Named here so the boundary test reads as a boundary.
THRESHOLD_DAYS = 365

#: Every fixture measures ages against this date by carrying one citation dated here.
ANCHOR = datetime.date(2026, 8, 28)

RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "the symptom text",
    "why_now": "w", "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"],
    "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _citation(n: int, day: datetime.date) -> dict:
    return {"source_class": "first-party-field", "title": f"INC-{n}",
            "locator": f"https://example.invalid/inc{n}", "date": day.isoformat(),
            "quote": f"the verbatim line {n}"}


def _rec(gap_id: str, *days: datetime.date, title: str | None = None) -> dict:
    """A valid record whose citations carry exactly the dates given, in the order given."""
    return {**RECORD, "id": gap_id,
            "title": title if title is not None else f"Record {gap_id}",
            "evidence": [_citation(i, day) for i, day in enumerate(days, start=1)]}


def _ago(days: int) -> datetime.date:
    return ANCHOR - datetime.timedelta(days=days)


def _register(root: pathlib.Path, records) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for record in records:
        (d / f"{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def _render(root: pathlib.Path) -> str:
    return radar_report(load_all(root / "gaps"))


def _section(out: str, heading: str) -> str:
    """The text of one level-2 section, heading line included, next `## ` excluded."""
    assert heading in out, f"missing section {heading!r}"
    rest = out.split(heading, 1)[1]
    body = rest.split("\n## ", 1)[0]
    return heading + body


def _body_lines(section: str) -> list[str]:
    """Non-blank lines of a section, heading excluded."""
    return [line for line in section.split("\n")[1:] if line.strip()]


def _data_rows(section: str) -> list[list[str]]:
    """Cells of every markdown data row (header and `| --- |` separator excluded)."""
    rows = [line for line in section.split("\n") if line.startswith("|")]
    return [[c.strip() for c in line.strip("|").split("|")] for line in rows[2:]]


# --- behavior 1: the section and its position ------------------------------

def test_b1_report_publishes_an_evidence_age_section(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", ANCHOR)]))
    assert EVIDENCE_AGE in out


def test_b1_section_order_is_ranked_by_layer_evidence_age_below_floor(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(900))]))
    order = [out.index(h) for h in (RANKED, BY_LAYER, EVIDENCE_AGE, BELOW_FLOOR)]
    assert order == sorted(order), out
    # And it is a level-2 heading on its own line, not an inline mention.
    assert f"\n{EVIDENCE_AGE}\n" in out


# --- behavior 2: the anchor line, derived from the register ----------------

def test_b2_anchor_line_names_the_registers_own_newest_citation_date(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", _ago(10), ANCHOR, _ago(400)),
                                       _rec("GAP-002", _ago(900))]))
    assert _body_lines(_section(out, EVIDENCE_AGE))[0] == ANCHOR_TEMPLATE.format(
        date=ANCHOR.isoformat())


def test_b2_the_anchor_follows_the_data_not_a_literal(tmp_path):
    """A second register with a different maximum date must render a different anchor."""
    other = datetime.date(2025, 3, 4)
    out = _render(_register(tmp_path, [_rec("GAP-001", other),
                                       _rec("GAP-002", other - datetime.timedelta(days=800))]))
    first = _body_lines(_section(out, EVIDENCE_AGE))[0]
    assert first == ANCHOR_TEMPLATE.format(date=other.isoformat())
    assert ANCHOR.isoformat() not in first


# --- behavior 3: the purpose line -----------------------------------------

def test_b3_purpose_line_is_verbatim_and_follows_the_anchor(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(900))]))
    body = _body_lines(_section(out, EVIDENCE_AGE))
    assert body[1] == PURPOSE_LINE


def test_b3_no_judgment_word_is_rendered_in_the_section(tmp_path):
    """Out of Scope: the word `stale` must not appear in any rendered line of the section."""
    section = _section(_render(_register(tmp_path, [_rec("GAP-001", ANCHOR),
                                                    _rec("GAP-002", _ago(900))])),
                       EVIDENCE_AGE)
    assert "stale" not in section.lower()


# --- behavior 4: the table, its membership, its order and its values ------

def test_b4_table_lists_only_past_threshold_records_newest_first_ties_by_id(tmp_path):
    records = [
        _rec("GAP-001", ANCHOR, title="The anchor record"),
        _rec("GAP-002", _ago(400), title="Four hundred"),
        _rec("GAP-003", _ago(1000), title="A thousand"),
        _rec("GAP-004", _ago(400), title="Four hundred too"),
        _rec("GAP-005", _ago(100), title="Recent enough"),
    ]
    section = _section(_render(_register(tmp_path, records)), EVIDENCE_AGE)
    assert TABLE_HEADER in section
    rows = _data_rows(section)
    assert [r[0] for r in rows] == ["GAP-003", "GAP-002", "GAP-004"], rows
    assert rows[0] == ["GAP-003", _ago(1000).isoformat(), "1000", "A thousand"]
    assert rows[1] == ["GAP-002", _ago(400).isoformat(), "400", "Four hundred"]
    assert rows[2] == ["GAP-004", _ago(400).isoformat(), "400", "Four hundred too"]


def test_b4_the_age_is_computed_from_a_records_newest_citation(tmp_path):
    """A record's own oldest citation must not decide its age."""
    records = [_rec("GAP-001", ANCHOR),
               _rec("GAP-002", _ago(2000), _ago(500), _ago(1200), title="Newest is 500")]
    rows = _data_rows(_section(_render(_register(tmp_path, records)), EVIDENCE_AGE))
    assert rows == [["GAP-002", _ago(500).isoformat(), "500", "Newest is 500"]]


def test_b4_exactly_365_days_is_not_listed_and_366_is(tmp_path):
    """Two-sided boundary: a `>=` comparison fails the first half."""
    at = tmp_path / "at"
    past = tmp_path / "past"
    at_rows = _data_rows(_section(_render(_register(at, [
        _rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(THRESHOLD_DAYS))])), EVIDENCE_AGE))
    past_rows = _data_rows(_section(_render(_register(past, [
        _rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(THRESHOLD_DAYS + 1))])), EVIDENCE_AGE))
    assert at_rows == []
    assert [r[0] for r in past_rows] == ["GAP-002"]
    assert past_rows[0][2] == str(THRESHOLD_DAYS + 1)


# --- behavior 5: records, but none past the threshold ---------------------

def test_b5_nothing_past_the_threshold_prints_none_found_and_no_table(tmp_path):
    section = _section(_render(_register(tmp_path, [_rec("GAP-001", ANCHOR),
                                                    _rec("GAP-002", _ago(30))])),
                       EVIDENCE_AGE)
    body = _body_lines(section)
    assert body == [ANCHOR_TEMPLATE.format(date=ANCHOR.isoformat()), PURPOSE_LINE, NONE_FOUND]
    assert TABLE_HEADER not in section
    assert not any(line.startswith("|") for line in section.split("\n"))


# --- behavior 6: the zero-record register --------------------------------

def test_b6_zero_record_register_prints_the_heading_and_none_found_only(tmp_path, capsys):
    root = _register(tmp_path, [])
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _section(captured.out, EVIDENCE_AGE)
    assert _body_lines(section) == [NONE_FOUND]
    assert "Ages are measured against" not in section
    assert _section(radar_report([]), EVIDENCE_AGE) == section


# --- behavior 7: age is a display and never a score input -----------------

def test_b7_changing_only_a_citation_date_moves_no_score_and_drops_no_record(tmp_path):
    weak = {"source_class": "model-output", "title": "M-1",
            "locator": "https://example.invalid/m1", "date": "", "quote": "a model line"}

    def build(root: pathlib.Path, age_days: int) -> str:
        # GAP-002 carries the anchor date and never changes, so the ONLY difference
        # between the two documents is GAP-001's citation date.
        ranked = _rec("GAP-001", _ago(age_days), title="A ranked thing")
        below = {**_rec("GAP-002", ANCHOR, title="A weakly evidenced thing"),
                 "evidence": [{**weak, "date": ANCHOR.isoformat()}]}
        return _render(_register(root, [ranked, below]))

    old = build(tmp_path / "old", 3000)
    new = build(tmp_path / "new", 1)

    # premise: the two documents DO differ, and only inside `## Evidence age`
    assert old != new
    assert _section(old, EVIDENCE_AGE) != _section(new, EVIDENCE_AGE)

    assert _section(old, RANKED) == _section(new, RANKED)
    assert _section(old, BY_LAYER) == _section(new, BY_LAYER)
    assert _section(old, BELOW_FLOOR) == _section(new, BELOW_FLOOR)
    assert old.split(RANKED, 1)[0] == new.split(RANKED, 1)[0]

    # never-drop: an aged record keeps its row in the ranked table and its below-floor row
    assert "GAP-001" in _section(old, RANKED)
    assert "GAP-002" in _section(old, BELOW_FLOOR)
    assert [r[0] for r in _data_rows(_section(old, EVIDENCE_AGE))] == ["GAP-001"]
    assert _data_rows(_section(new, EVIDENCE_AGE)) == []


# --- behavior 8: no committed byte-pin is re-baselined -------------------

def test_b8_iteration_17_byte_pins_still_hold_unedited(tmp_path):
    """Imported, not restated: this file must not be able to re-baseline that pin."""
    import test_iter17_behavior as it17

    out = _render(_register(tmp_path, [it17.RECORD, it17._B8_WEAK]))
    before, rest = out.split(BY_LAYER, 1)
    _by_layer, after = rest.split(BELOW_FLOOR, 1)
    assert before == it17._B8_BEFORE
    assert BELOW_FLOOR + after == it17._B8_AFTER
    # the new section lives strictly between `## By layer` and `## Below confidence floor`
    assert EVIDENCE_AGE not in before
    assert EVIDENCE_AGE not in BELOW_FLOOR + after
    assert EVIDENCE_AGE in rest.split(BELOW_FLOOR, 1)[0]


# --- behavior 9: determinism and exactly one trailing newline ------------

def test_b9_two_renders_of_the_same_register_are_byte_identical(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(900)),
                                _rec("GAP-003", _ago(900))])
    assert main(["report", str(root)]) == 0
    first = capsys.readouterr().out
    assert main(["report", str(root)]) == 0
    assert capsys.readouterr().out == first == _render(root)
    assert first.endswith("\n") and not first.endswith("\n\n")


# --- behavior 10: one surface only --------------------------------------

def test_b10_no_other_verb_publishes_an_age(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", ANCHOR), _rec("GAP-002", _ago(900))])
    for argv in (["list", str(root)], ["show", "GAP-002", str(root)],
                 ["taxonomy"], ["validate", str(root)]):
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        assert captured.err == ""
        assert "Evidence age" not in captured.out, argv
        assert "Age (days)" not in captured.out, argv
