"""Iteration 05 behaviors: the below-floor research queue states, per record, the
cheapest citation class whose addition would lift that record to the confidence floor.

Black-box. Nothing here reads the implementation source, the engineer's notes, or a
diff. Two independent references stand in for the source:

* the LADDER -- class names, weights, and rung ORDER -- is parsed out of the product's
  own `radar taxonomy` output, so ladder order is OBSERVED rather than imported from
  the module the feature is built on;
* `_oracle_confidence` re-implements the scoring rule from the description the existing
  suite already pins (ceiling from the strongest class, +1 when two DISTINCT real
  classes corroborate, capped at 5, `model-output` weighing nothing and never
  corroborating). It earns the right to be believed by being cross-checked against the
  shipped `confidence()` on every record in the register before any test uses it.

Expected cell strings for named records are stated literally from the spec. Each such
test asserts its PREMISE about that record's evidence first, because promoting a
below-floor record is the entire point of this feature: when GAP-010 finally gains a
primary source, these tests must fail with a message that says so, not with an
unexplained string mismatch.

WHICH records the below-floor table holds is a different question from WHAT their
cells say, and it is deliberately not stated here as a closed list of ids. The
register grows on a schedule, so an id census fails on newly added data while the
renderer it claims to test is untouched -- and it fails naming a data file, which
reads as a broken register rather than as a fragile test. A named record's presence
is asserted by MEMBERSHIP; the full set is DERIVED from `confidence()` -- at the
product's own default floor below, and exhaustively at every floor in
`test_iter09_behavior.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import (CONFIDENCE_FLOOR_DEFAULT, confidence,
                                     promotion_options)

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: Measured from the tree as committed BEFORE this iteration, by rendering the report
#: from `git archive HEAD` in a temp dir. Behavior 8: the ranked table gains nothing.
RANKED_HEADER = "| Rank | ID | Priority | Confidence | Layer | Type | Title |"

NEEDS_COLUMN = "Needs"

RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


# ---------------------------------------------------------------------------
# the ladder, observed by running the product
# ---------------------------------------------------------------------------

def _observed_ladder() -> tuple[tuple[str, int], ...]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert main(["taxonomy"]) == 0
    parts = buffer.getvalue().split("## Evidence source classes", 1)
    assert len(parts) == 2, "taxonomy must publish the evidence ladder"
    rows: list[tuple[str, int]] = []
    for line in parts[1].splitlines():
        found = re.match(r"^-\s+`([a-z-]+)`\s+\(weight (\d+)\)", line.strip())
        if found:
            rows.append((found.group(1), int(found.group(2))))
    assert rows, "no ladder rungs parsed from taxonomy output"
    return tuple(rows)


LADDER = _observed_ladder()
CLASSES = tuple(name for name, _ in LADDER)
WEIGHT = dict(LADDER)
LIFTING_CLASSES = tuple(name for name, weight in LADDER if weight > 0)
FLOORS = tuple(range(0, 7))


def test_the_ladder_is_a_non_empty_domain_with_the_expected_shape():
    """A green result over an empty domain is the failure that looks like health."""
    assert len(LADDER) == 9, LADDER
    assert WEIGHT["model-output"] == 0
    assert [w for _, w in LADDER] == sorted((w for _, w in LADDER), reverse=True)
    assert LIFTING_CLASSES and "model-output" not in LIFTING_CLASSES


# ---------------------------------------------------------------------------
# independent oracle for the scoring rule and the prescription
# ---------------------------------------------------------------------------

def _oracle_confidence(classes) -> int:
    real = {c for c in classes if WEIGHT[c] > 0}
    if not real:
        return 0
    return min(5, max(WEIGHT[c] for c in real) + (1 if len(real) >= 2 else 0))


def _oracle_needs(classes, floor: int) -> tuple[str, ...]:
    reaching = [c for c in LIFTING_CLASSES
                if _oracle_confidence(tuple(classes) + (c,)) >= floor]
    if not reaching:
        return ()
    cheapest = min(WEIGHT[c] for c in reaching)
    return tuple(c for c in reaching if WEIGHT[c] == cheapest)


def _oracle_cell(classes, floor: int) -> str:
    needs = _oracle_needs(classes, floor)
    if not needs:
        return f"no single citation reaches floor {floor}"
    return f"weight >= {WEIGHT[needs[0]]}: " + ", ".join(needs)


def _gap(gid="GAP-001", classes=("first-party-field",), sev=3, freq=3, tract=3):
    return Gap.model_validate({
        **RECORD, "id": gid, "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "q"} for c in classes],
    })


def _classes_of(gap) -> tuple[str, ...]:
    return tuple(e.source_class for e in gap.evidence)


def test_the_oracle_agrees_with_the_shipped_scorer_on_every_real_record():
    records = load_all(GAPS_DIR)
    assert len(records) >= 16, f"register unexpectedly small: {len(records)}"
    checked = 0
    for gap in records:
        assert _oracle_confidence(_classes_of(gap)) == confidence(gap), gap.id
        checked += 1
    assert checked == len(records)


# ---------------------------------------------------------------------------
# behavior 1 -- promotion_options is pure, total, and ladder-ordered
# ---------------------------------------------------------------------------

CLASS_SETS = (
    (),
    ("secondary-summary",),
    ("vendor-primary",),
    ("first-party-field",),
    ("model-output",),
    ("model-output", "model-output"),
    ("secondary-summary", "model-output"),
    ("peer-reviewed", "practitioner-report"),
    ("vendor-primary", "vendor-primary"),
    ("survey-aggregate",),
)


def _gap_with(classes):
    """A gap holding exactly these classes; the empty case bypasses min_length=1."""
    if classes:
        return _gap(classes=classes)
    return _gap().model_copy(update={"evidence": []})


def test_b1_matches_the_independent_oracle_for_every_class_set_and_floor():
    checked = 0
    for classes in CLASS_SETS:
        gap = _gap_with(classes)
        for floor in FLOORS:
            assert promotion_options(gap, floor) == _oracle_needs(classes, floor), (
                classes, floor)
            checked += 1
    assert checked == len(CLASS_SETS) * len(FLOORS) == 70


def test_b1_returns_a_tuple_of_known_classes_and_never_model_output():
    for classes in CLASS_SETS:
        gap = _gap_with(classes)
        for floor in FLOORS:
            options = promotion_options(gap, floor)
            assert isinstance(options, tuple), type(options)
            assert all(isinstance(o, str) for o in options)
            assert set(options) <= set(CLASSES)
            assert "model-output" not in options, (classes, floor)
            assert len(set(options)) == len(options), "no duplicate prescriptions"
            weights = [WEIGHT[o] for o in options]
            assert len(set(weights)) <= 1, "one cheapest rung only"
            rungs = [CLASSES.index(o) for o in options]
            assert rungs == sorted(rungs), "ladder order, not alphabetical"


def test_b1_never_prescribes_a_class_the_record_already_holds_alone():
    """A repeat citation of the same class is not corroboration, so it cannot lift."""
    gap = _gap(classes=("secondary-summary",))
    for floor in (2, 3, 4, 5):
        assert "secondary-summary" not in promotion_options(gap, floor)


def test_b1_returns_empty_when_no_single_class_reaches_the_floor():
    for classes in CLASS_SETS:
        assert promotion_options(_gap_with(classes), 6) == ()


def test_b1_is_total_and_deterministic():
    gap = _gap(classes=("secondary-summary",))
    assert len({promotion_options(gap, 2) for _ in range(50)}) == 1
    for floor in (-5, 0, 6, 7, 99):
        assert isinstance(promotion_options(gap, floor), tuple)
    assert isinstance(promotion_options(_gap_with(()), 2), tuple)
    assert promotion_options(gap, confidence_floor=5) == promotion_options(gap, 5)


def test_b1_reads_no_file(monkeypatch):
    gap = _gap(classes=("secondary-summary",))
    warm = promotion_options(gap, 5)  # warm any lazy import before the trap is set

    def _no_open(*args, **kwargs):  # pragma: no cover - the point is that it is unused
        raise AssertionError("promotion_options must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _no_open)
    monkeypatch.setattr(pathlib.Path, "read_text", _no_open)
    monkeypatch.setattr(pathlib.Path, "open", _no_open)
    with pytest.raises(AssertionError):
        open(__file__)  # the trap must actually bite, or this test proves nothing
    assert promotion_options(gap, 5) == warm


# ---------------------------------------------------------------------------
# report plumbing
# ---------------------------------------------------------------------------

def _report(capsys, *args: str, path: str | None = None) -> str:
    assert main(["report", path or str(REPO_ROOT), *args]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Agent infrastructure gap radar"), out[:80]
    return out


def _rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append([c.strip() for c in stripped.strip("|").split("|")])
    return rows


def _below_floor_rows(out: str) -> list[list[str]]:
    assert "## Below confidence floor" in out
    return _rows(out.split("## Below confidence floor", 1)[1])


def _needs_cells(out: str) -> dict[str, str]:
    """Map id -> last cell for every below-floor data row; {} when the table is empty."""
    rows = _below_floor_rows(out)
    if not rows:
        return {}
    assert rows[0][-1] == NEEDS_COLUMN, rows[0]
    assert set(rows[1]) == {"---"}, rows[1]
    return {row[0]: row[-1] for row in rows[2:]}


# ---------------------------------------------------------------------------
# behaviors 2-6 -- the rendered prescription
# ---------------------------------------------------------------------------

GAP_010_PREMISE = (
    "GAP-010 holds exactly one secondary-summary citation. Promoting it is the POINT "
    "of this feature, so when it gains a primary source, re-derive the expected cell "
    "from the ladder rather than loosening this assertion."
)


def _record(gap_id: str):
    matched = [g for g in load_all(GAPS_DIR) if g.id == gap_id]
    assert matched, f"{gap_id} is no longer in the register"
    return matched[0]


def _ids_below_floor(floor: int) -> set[str]:
    """The register's own answer to which of its records sit under `floor`.

    An ORACLE, not a restatement: it reads `confidence()`, the one rule the
    vision protects, so the claim under test stays "a record is rendered on the
    correct side of the floor" while staying independent of how many records the
    register happens to hold today.
    """
    return {gap.id for gap in load_all(GAPS_DIR) if confidence(gap) < floor}


def test_b2_default_floor_names_the_cheapest_lifting_classes_for_gap_010(capsys):
    assert _classes_of(_record("GAP-010")) == ("secondary-summary",), GAP_010_PREMISE
    cells = _needs_cells(_report(capsys))
    # Derived, and read at the product's NAMED default rather than at a fourth
    # literal 2. That makes this a PARTIAL guard on the three separate spellings
    # of the default floor, not a complete one: it bites only when the rendered
    # floor and the constant partition the register differently, and adjacent
    # floors routinely partition it identically (measured -- see the iteration's
    # engineer notes). The complete check is to read the floor the document
    # itself echoes; that is a separate bite and is not made here.
    assert set(cells) == _ids_below_floor(CONFIDENCE_FLOOR_DEFAULT), cells
    assert "GAP-010" in cells, cells
    assert cells["GAP-010"] == "weight >= 3: practitioner-report, survey-aggregate"


def test_b3_two_below_floor_records_get_DIFFERENT_prescriptions(capsys):
    """Anti-vacuity: a template sentence cannot produce two different cells."""
    assert _classes_of(_record("GAP-008")) == ("vendor-primary",)
    assert _classes_of(_record("GAP-010")) == ("secondary-summary",), GAP_010_PREMISE
    cells = _needs_cells(_report(capsys, "--floor", "5"))
    # Membership, not a closed set: this test's subject is that two records get
    # DIFFERENT cells, and a third below-floor record arriving is not evidence
    # against that. The exhaustive set claim lives in test_iter09_behavior.py.
    assert "GAP-008" in cells, cells
    assert "GAP-010" in cells, cells
    assert cells["GAP-008"] == "weight >= 1: secondary-summary"
    assert cells["GAP-010"] == "weight >= 4: peer-reviewed, maintainer-primary, vendor-primary"
    assert cells["GAP-008"] != cells["GAP-010"]


def test_b4_classes_are_ordered_by_ladder_rung_never_alphabetically(capsys):
    out = _report(capsys, "--floor", "5")
    assert "maintainer-primary, peer-reviewed" not in out
    listed = [c for c in _needs_cells(out).values() if ": " in c]
    assert listed, "no prescription cells to check"
    multi = [c.split(": ", 1)[1].split(", ") for c in listed]
    multi = [names for names in multi if len(names) > 1]
    assert multi, "expected at least one multi-class cell at floor 5"
    for names in multi:
        rungs = [CLASSES.index(n) for n in names]
        assert rungs == sorted(rungs), names
    assert any(names != sorted(names) for names in multi), (
        "every cell happened to be alphabetical, so this proves nothing about order")


def test_b5_an_unreachable_floor_says_so_for_every_record(capsys):
    out = _report(capsys, "--floor", "6")
    cells = _needs_cells(out)
    assert len(cells) == len(load_all(GAPS_DIR)) >= 16, len(cells)
    assert set(cells.values()) == {"no single citation reaches floor 6"}
    assert "" not in cells.values()


def test_b6_no_cell_names_a_class_that_cannot_move_the_record(capsys):
    seen_cells = 0
    for floor in FLOORS:
        cells = _needs_cells(_report(capsys, "--floor", str(floor)))
        for gap_id, cell in cells.items():
            seen_cells += 1
            assert "model-output" not in cell, (floor, gap_id, cell)
            if gap_id == "GAP-010":
                assert "secondary-summary" not in cell, (floor, cell)
    assert seen_cells >= 18, seen_cells


def test_every_rendered_cell_is_derived_not_asserted(capsys):
    """Durable form of behaviors 2, 3 and 5: survives the register growing."""
    checked = 0
    for floor in FLOORS:
        cells = _needs_cells(_report(capsys, "--floor", str(floor)))
        for gap_id, cell in cells.items():
            expected = _oracle_cell(_classes_of(_record(gap_id)), floor)
            assert cell == expected, (floor, gap_id, cell, expected)
            checked += 1
    assert checked >= 18, checked


def test_divergent_prescriptions_on_a_synthetic_register(tmp_path, capsys):
    """The same divergence as behavior 3, independent of the published register."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for gid, source_class in (("GAP-001", "vendor-primary"),
                              ("GAP-002", "secondary-summary")):
        record = {**RECORD, "id": gid,
                  "evidence": [{**RECORD["evidence"][0],
                                "source_class": source_class}]}
        (gaps / f"{gid}.json").write_text(json.dumps(record), encoding="utf-8")
    cells = _needs_cells(_report(capsys, "--floor", "5", path=str(tmp_path)))
    assert sorted(cells) == ["GAP-001", "GAP-002"], cells
    assert cells["GAP-001"] == "weight >= 1: secondary-summary"
    assert cells["GAP-002"] == "weight >= 4: peer-reviewed, maintainer-primary, vendor-primary"
    assert cells["GAP-001"] != cells["GAP-002"]


# ---------------------------------------------------------------------------
# behaviors 7-8 -- nothing is asserted, nothing else moved
# ---------------------------------------------------------------------------

def test_b7_a_record_asserting_its_own_needs_key_is_rejected(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    (gaps / "GAP-001.json").write_text(
        json.dumps({**RECORD, "needs": ["peer-reviewed"]}), encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: "), captured.err
    assert captured.out == ""


def test_b7_the_same_record_without_the_extra_key_still_validates(tmp_path, capsys):
    """The rejection above must be caused by the key, not by a broken fixture."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    (gaps / "GAP-001.json").write_text(json.dumps(RECORD), encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 0
    assert "1 gap record(s) valid" in capsys.readouterr().out


def test_b8_ranked_table_header_is_byte_identical_and_gains_no_needs_column(capsys):
    out = _report(capsys)
    ranked = out.split("## Ranked gaps", 1)[1].split("## By layer", 1)[0]
    header = [row for row in _rows(ranked)][0]
    assert "| " + " | ".join(header) + " |" == RANKED_HEADER
    assert NEEDS_COLUMN not in ranked
    assert out.count("| " + NEEDS_COLUMN + " |") == 1


def test_b8_report_ends_in_exactly_one_newline_and_is_byte_stable(capsys):
    first = _report(capsys)
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert _report(capsys) == first
    at_five = _report(capsys, "--floor", "5")
    assert at_five.endswith("\n") and not at_five.endswith("\n\n")
    assert _report(capsys, "--floor", "5") == at_five
