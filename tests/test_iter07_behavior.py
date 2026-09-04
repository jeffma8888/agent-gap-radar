"""Iteration 07 behaviors: the report's "Strongest source" cell comes from the evidence
ladder RUNG, never from an alphabetical sort of the class NAME.

Black-box. Nothing here reads the implementation source, the engineer's notes, or a
diff. Every assertion either calls the one public helper the spec names
(`scoring.strongest_source`), calls the renderer the existing suite already drives
(`render.radar_report`), or runs `agent_gap_radar.cli.main` and observes only the exit
code, stdout and stderr.

Three habits this file keeps on purpose:

* the LADDER -- class names, rung ORDER and weights -- is parsed out of the product's
  own `radar taxonomy` output, so it is OBSERVED rather than imported from the module
  the feature is built on (same reference iter 05 established);
* every register-facing assertion asserts its DOMAIN IS NON-EMPTY first. A green result
  over zero rows is the failure that looks like health;
* the two register invariants are deliberately built from DIFFERENT tables, and each
  names the case it cannot see. `test_b6_*` keys on WEIGHT, so it is blind to a
  disagreement between two classes of EQUAL weight; `test_b6_tied_*` keys on rung and
  covers exactly that blind spot. Neither is vacuous, and the proof is two-sided rather
  than asserted: driven through this same public interface against a ``git archive HEAD``
  export of the pre-change tree, the weight-keyed form reports 1 violation (a record
  printing a weight-1 class where its own maximum is 4) and the rung-keyed form reports 2,
  while both report 0 on the current tree. That run is recorded in the iteration's tester
  report, with the exit code and byte count of every capture beside it.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.models import Evidence, Gap
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report
from agent_gap_radar.scoring import confidence, priority, strongest_source

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

STRONGEST_COLUMN = "Strongest source"

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
RUNG = {name: index for index, name in enumerate(CLASSES)}
UNKNOWN_CLASS = "not-a-source-class"


def test_the_ladder_is_a_non_empty_domain_with_the_expected_shape():
    """A green result over an empty domain is the failure that looks like health."""
    assert len(LADDER) == 9, LADDER
    assert UNKNOWN_CLASS not in CLASSES
    assert WEIGHT["model-output"] == 0
    assert len(set(CLASSES)) == len(CLASSES), "ladder rungs must be distinct"


def test_the_ladder_has_weight_ties_so_rung_and_weight_are_different_keys():
    """The premise the whole iteration rests on: weight is NOT injective over classes.

    If every class had a distinct weight, "key on the rung" and "key on the weight"
    would be the same function and behavior 3 would be untestable.
    """
    tied = [w for w in set(WEIGHT.values()) if list(WEIGHT.values()).count(w) > 1]
    assert tied, WEIGHT
    assert WEIGHT["peer-reviewed"] == WEIGHT["maintainer-primary"] == 4


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _gap(gid="GAP-001", classes=("first-party-field",), sev=3, freq=3, tract=3):
    return Gap.model_validate({
        **RECORD, "id": gid, "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": f"t-{c}",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "q"} for c in classes],
    })


def _gap_with_no_evidence():
    """`min_length=1` blocks this through the loader, so build it by copy."""
    return _gap().model_copy(update={"evidence": []})


def _gap_with_classes_unvalidated(classes):
    """Bypass schema validation so an off-ladder class can be exercised at all."""
    evidence = [Evidence.model_construct(
        source_class=c, title=f"t-{c}", locator="https://example.invalid/x",
        date="2026-01-02", quote="q") for c in classes]
    return _gap().model_copy(update={"evidence": evidence})


def _classes_of(gap) -> tuple[str, ...]:
    return tuple(e.source_class for e in gap.evidence)


def _record(gap_id: str):
    matched = [g for g in load_all(GAPS_DIR) if g.id == gap_id]
    assert matched, f"{gap_id} is no longer in the register"
    return matched[0]


# ---------------------------------------------------------------------------
# report plumbing
# ---------------------------------------------------------------------------

def _report(capsys, *args: str, path: str | None = None) -> str:
    assert main(["report", path or str(REPO_ROOT), *args]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    out = captured.out
    assert out.startswith("# Agent infrastructure gap radar"), out[:80]
    return out


def _rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append([c.strip() for c in stripped.strip("|").split("|")])
    return rows


def _below_floor_section(out: str) -> str:
    assert "## Below confidence floor" in out
    return out.split("## Below confidence floor", 1)[1]


def _strongest_cells(out: str) -> dict[str, str]:
    """Map id -> "Strongest source" cell for every below-floor data row.

    The column is located BY NAME, never by a guessed index, so a future column
    insertion fails loudly here instead of silently reading the wrong cell.
    """
    rows = _rows(_below_floor_section(out))
    if not rows:
        return {}
    header = rows[0]
    assert STRONGEST_COLUMN in header, header
    column = header.index(STRONGEST_COLUMN)
    assert set(rows[1]) == {"---"}, rows[1]
    return {row[0]: row[column] for row in rows[2:]}


def _row_line(out: str, gap_id: str) -> str:
    """The raw below-floor line for one record, so a cell-splitting bug cannot hide text."""
    lines = [ln for ln in _below_floor_section(out).splitlines()
             if ln.strip().startswith(f"| {gap_id} ")]
    assert len(lines) == 1, lines
    return lines[0]


def _synthetic_register(tmp_path, classes, gid="GAP-999"):
    """A one-record register whose sole record holds exactly these classes."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    record = {**RECORD, "id": gid,
              "evidence": [{**RECORD["evidence"][0], "source_class": c,
                            "title": f"t-{c}"} for c in classes]}
    (gaps / f"{gid}.json").write_text(json.dumps(record), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# behavior 1 -- the ladder rung decides, and it decides for every pair
# ---------------------------------------------------------------------------

def test_b1_named_case_secondary_summary_then_vendor_primary(capsys):
    assert strongest_source(_gap(classes=("secondary-summary", "vendor-primary"))) == (
        "vendor-primary")


def test_b1_a_single_citation_returns_its_own_class():
    for name in CLASSES:
        assert strongest_source(_gap(classes=(name,))) == name


def test_b1_every_ordered_pair_returns_the_higher_rung_in_both_orders():
    checked = 0
    for first in CLASSES:
        for second in CLASSES:
            expected = first if RUNG[first] <= RUNG[second] else second
            assert strongest_source(_gap(classes=(first, second))) == expected, (
                first, second)
            checked += 1
    assert checked == len(CLASSES) ** 2 == 81


def test_b1_holds_across_the_whole_ladder_in_one_record_either_way_round():
    forward = _gap(classes=CLASSES)
    backward = _gap(classes=tuple(reversed(CLASSES)))
    assert strongest_source(forward) == CLASSES[0]
    assert strongest_source(backward) == CLASSES[0]


def test_b1_is_deterministic_and_reads_no_file(monkeypatch):
    gap = _gap(classes=("secondary-summary", "vendor-primary"))
    warm = strongest_source(gap)
    assert len({strongest_source(gap) for _ in range(50)}) == 1

    def _no_open(*args, **kwargs):  # pragma: no cover - the point is that it is unused
        raise AssertionError("strongest_source must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _no_open)
    monkeypatch.setattr(pathlib.Path, "read_text", _no_open)
    monkeypatch.setattr(pathlib.Path, "open", _no_open)
    with pytest.raises(AssertionError):
        open(__file__)  # the trap must actually bite, or this test proves nothing
    assert strongest_source(gap) == warm


# ---------------------------------------------------------------------------
# behavior 2 -- model-output never wins over a real citation
# ---------------------------------------------------------------------------

def test_b2_secondary_summary_beats_model_output_in_both_orders():
    assert strongest_source(_gap(classes=("secondary-summary", "model-output"))) == (
        "secondary-summary")
    assert strongest_source(_gap(classes=("model-output", "secondary-summary"))) == (
        "secondary-summary")


def test_b2_model_output_never_wins_against_any_real_class():
    real = [c for c in CLASSES if WEIGHT[c] > 0]
    assert real, CLASSES
    for name in real:
        for order in ((name, "model-output"), ("model-output", name)):
            assert strongest_source(_gap(classes=order)) == name, order


def test_b2_model_output_alone_is_still_reported_because_it_is_all_there_is():
    """Honest boundary: the helper reports the best AVAILABLE class, it does not censor.

    A record sourced only from model output prints `model-output` -- which is correct,
    and already flagged to the reader by its confidence of 0.
    """
    gap = _gap(classes=("model-output", "model-output"))
    assert strongest_source(gap) == "model-output"
    assert confidence(gap) == 0


# ---------------------------------------------------------------------------
# behavior 3 -- equal WEIGHTS resolve by RUNG, not by name
# ---------------------------------------------------------------------------

def test_b3_named_case_peer_reviewed_beats_maintainer_primary_both_orders():
    assert WEIGHT["peer-reviewed"] == WEIGHT["maintainer-primary"], (
        "premise: these two classes carry the SAME weight, so only the rung can decide")
    assert RUNG["peer-reviewed"] < RUNG["maintainer-primary"]
    for order in (("maintainer-primary", "peer-reviewed"),
                  ("peer-reviewed", "maintainer-primary")):
        assert strongest_source(_gap(classes=order)) == "peer-reviewed", order


def test_b3_the_named_case_is_not_the_alphabetical_answer():
    """Anti-vacuity for behavior 3: alphabetical and rung DISAGREE on this pair."""
    pair = ("maintainer-primary", "peer-reviewed")
    assert min(pair) == "maintainer-primary"
    assert strongest_source(_gap(classes=pair)) != min(pair)


def test_b3_every_equal_weight_pair_resolves_by_rung_and_is_order_independent():
    tied_pairs = [(a, b) for a in CLASSES for b in CLASSES
                  if a != b and WEIGHT[a] == WEIGHT[b]]
    assert len(tied_pairs) >= 6, tied_pairs
    for a, b in tied_pairs:
        expected = a if RUNG[a] < RUNG[b] else b
        assert strongest_source(_gap(classes=(a, b))) == expected, (a, b)
        assert strongest_source(_gap(classes=(b, a))) == expected, (b, a)


def test_b3_no_pair_anywhere_resolves_alphabetically_where_that_differs():
    """The whole-ladder form: wherever alphabet and rung disagree, rung must win."""
    disagreeing = 0
    for a in CLASSES:
        for b in CLASSES:
            if a == b:
                continue
            by_rung = a if RUNG[a] < RUNG[b] else b
            by_name = min(a, b)
            if by_rung != by_name:
                disagreeing += 1
                assert strongest_source(_gap(classes=(a, b))) == by_rung, (a, b)
    assert disagreeing >= 2, "no disagreeing pair exists, so this proves nothing"


def test_b3_a_tied_weight_pair_renders_the_higher_rung_through_the_report(tmp_path, capsys):
    """Behavior 3 at the RENDERED surface, built rather than borrowed from the register.

    `test_b6_tied_*` exercises the tied-weight case only for as long as some COMMITTED
    record happens to cite two classes of equal weight. A research pass could retire or
    re-source that record and the rendered tied case would vanish with it, silently --
    leaving behavior 3 pinned at the helper only, which is where an alphabetical read
    could be reintroduced in the renderer and go unseen. This one constructs the pair.
    """
    pair = ("maintainer-primary", "peer-reviewed")
    assert WEIGHT[pair[0]] == WEIGHT[pair[1]] == 4, WEIGHT
    assert min(pair) == "maintainer-primary", "premise: the alphabet picks the WRONG one"
    out = _report(capsys, "--floor", "6", path=str(_synthetic_register(tmp_path, pair)))
    assert _strongest_cells(out) == {"GAP-999": "peer-reviewed"}, _strongest_cells(out)
    assert "maintainer-primary" not in _row_line(out, "GAP-999")


# ---------------------------------------------------------------------------
# behavior 4 -- total, never raising
# ---------------------------------------------------------------------------

def test_b4_empty_evidence_returns_empty_string():
    assert strongest_source(_gap_with_no_evidence()) == ""


def test_b4_an_off_ladder_class_ranks_after_every_known_class():
    for name in CLASSES:
        for order in ((name, UNKNOWN_CLASS), (UNKNOWN_CLASS, name)):
            gap = _gap_with_classes_unvalidated(order)
            assert strongest_source(gap) == name, order


def test_b4_an_off_ladder_class_is_returned_only_when_it_is_the_sole_citation():
    gap = _gap_with_classes_unvalidated((UNKNOWN_CLASS,))
    assert strongest_source(gap) == UNKNOWN_CLASS


def test_b4_is_total_over_every_odd_shape_and_never_raises():
    shapes = (
        (),
        ("model-output",),
        (UNKNOWN_CLASS,),
        (UNKNOWN_CLASS, UNKNOWN_CLASS),
        (UNKNOWN_CLASS, "model-output"),
        ("model-output", UNKNOWN_CLASS),
        CLASSES,
    )
    for classes in shapes:
        gap = _gap_with_no_evidence() if not classes else (
            _gap_with_classes_unvalidated(classes))
        answer = strongest_source(gap)
        assert isinstance(answer, str), (classes, type(answer))
        if classes:
            assert answer in set(classes), (classes, answer)
        else:
            assert answer == ""


# ---------------------------------------------------------------------------
# behavior 5 -- the shipped defect, rendered
# ---------------------------------------------------------------------------

DEFECT_CLASSES = ("secondary-summary", "model-output")


def test_b5_default_floor_row_names_secondary_summary_via_the_cli(tmp_path, capsys):
    root = _synthetic_register(tmp_path, DEFECT_CLASSES)
    out = _report(capsys, path=str(root))
    cells = _strongest_cells(out)
    assert list(cells) == ["GAP-999"], cells
    assert cells["GAP-999"] == "secondary-summary"


def test_b5_model_output_appears_nowhere_in_that_row(tmp_path, capsys):
    root = _synthetic_register(tmp_path, DEFECT_CLASSES)
    line = _row_line(_report(capsys, path=str(root)), "GAP-999")
    assert "secondary-summary" in line, line
    assert "model-output" not in line, line


def test_b5_same_row_through_radar_report_directly(tmp_path):
    root = _synthetic_register(tmp_path, DEFECT_CLASSES)
    out = radar_report(load_all(root / "gaps"))
    cells = _strongest_cells(out)
    assert cells == {"GAP-999": "secondary-summary"}, cells


def test_b5_premise_the_record_really_is_below_the_default_floor(tmp_path):
    """Anti-vacuity: if this record ever cleared the floor the row would vanish."""
    gaps = load_all(_synthetic_register(tmp_path, DEFECT_CLASSES) / "gaps")
    assert len(gaps) == 1
    assert _classes_of(gaps[0]) == DEFECT_CLASSES
    assert confidence(gaps[0]) == 1


# ---------------------------------------------------------------------------
# behavior 6 -- the committed register, keyed on WEIGHT (not the ladder index)
# ---------------------------------------------------------------------------

def test_b6_every_below_floor_cell_names_a_maximum_weight_class(capsys):
    """Derived from SOURCE_WEIGHTS, deliberately NOT from the rung order.

    BLIND SPOT, stated rather than left to be discovered: two classes of equal weight
    satisfy this assertion equally, so it cannot see a rung disagreement inside a
    weight tie. `test_b6_tied_*` covers exactly that case.
    """
    cells = _strongest_cells(_report(capsys, "--floor", "6"))
    records = {g.id: g for g in load_all(GAPS_DIR)}
    assert records, "empty register: this assertion would pass vacuously"
    assert set(cells) == set(records), (sorted(cells), sorted(records))
    checked = 0
    for gap_id, cell in cells.items():
        assert cell in CLASSES, (gap_id, cell)
        best = max(WEIGHT[c] for c in _classes_of(records[gap_id]))
        assert WEIGHT[cell] == best, (gap_id, cell, WEIGHT[cell], best)
        checked += 1
    assert checked == len(records) >= 16, checked


def test_b6_tied_weights_still_resolve_by_rung_over_the_committed_register(capsys):
    """Closes the blind spot above: keyed on the OBSERVED rung order."""
    cells = _strongest_cells(_report(capsys, "--floor", "6"))
    records = {g.id: g for g in load_all(GAPS_DIR)}
    assert cells and set(cells) == set(records)
    for gap_id, cell in cells.items():
        best_rung = min(RUNG[c] for c in _classes_of(records[gap_id]))
        assert RUNG[cell] == best_rung, (gap_id, cell, RUNG[cell], best_rung)


def test_b6_no_below_floor_cell_names_model_output_while_a_real_source_exists(capsys):
    cells = _strongest_cells(_report(capsys, "--floor", "6"))
    records = {g.id: g for g in load_all(GAPS_DIR)}
    assert cells
    for gap_id, cell in cells.items():
        classes = _classes_of(records[gap_id])
        if any(WEIGHT[c] > 0 for c in classes):
            assert WEIGHT[cell] > 0, (gap_id, cell)


def test_b6_the_weight_key_is_only_sufficient_because_of_a_cross_table_relation():
    """Names WHY the weight-derived invariant is weaker than it looks.

    `SOURCE_WEIGHTS` is monotone non-increasing along the rung order, so the
    ladder-minimum always carries the maximum weight. That relation is what makes
    behavior 6 pass for a correct implementation -- and nothing else in the suite
    pinned it, so if it ever breaks, behavior 6 must be re-derived rather than relaxed.
    """
    weights = [WEIGHT[name] for name in CLASSES]
    assert weights == sorted(weights, reverse=True), weights
    for higher, lower in zip(CLASSES, CLASSES[1:]):
        assert WEIGHT[higher] >= WEIGHT[lower], (higher, lower)


# ---------------------------------------------------------------------------
# behavior 7 -- nothing else moves
# ---------------------------------------------------------------------------

RANKED_HEADER = "| Rank | ID | Priority | Confidence | Layer | Type | Title |"


def test_b7_default_floor_cells_are_unchanged_because_both_rules_agree_there(capsys):
    """The derived form of "byte-identical at the default floor".

    A cell can only have moved where the alphabetical rule and the ladder rule
    disagree. This asserts they agree for every record rendered at the DEFAULT floor,
    which is why the committed default-floor report cannot have changed.
    """
    cells = _strongest_cells(_report(capsys))
    records = {g.id: g for g in load_all(GAPS_DIR)}
    assert cells, "no below-floor rows at the default floor: nothing measured"
    for gap_id, cell in cells.items():
        classes = _classes_of(records[gap_id])
        by_rung = min(classes, key=lambda c: RUNG[c])
        assert cell == by_rung, (gap_id, cell, by_rung)
        assert cell == min(classes), (
            f"{gap_id}: the two rules disagree here, so the default-floor report "
            "DID move and behavior 7 needs re-measuring")


def test_b7_ranked_table_header_and_order_are_unchanged(capsys):
    out = _report(capsys)
    ranked = out.split("## Ranked gaps", 1)[1].split("## By layer", 1)[0]
    rows = _rows(ranked)
    assert "| " + " | ".join(rows[0]) + " |" == RANKED_HEADER
    assert STRONGEST_COLUMN not in ranked
    ids = [row[1] for row in rows[2:]]
    assert ids, ranked
    keyed = sorted(ids, key=lambda gid: (-priority(_record(gid)),
                                         -confidence(_record(gid)), gid))
    assert ids == keyed, (ids, keyed)


def test_b7_priority_and_confidence_cells_still_match_the_scorers(capsys):
    out = _report(capsys, "--floor", "6")
    rows = _rows(_below_floor_section(out))
    header = rows[0]
    records = {g.id: g for g in load_all(GAPS_DIR)}
    checked = 0
    for row in rows[2:]:
        gap = records[row[0]]
        assert row[header.index("Priority")] == f"{priority(gap):.1f}"
        assert row[header.index("Confidence")] == str(confidence(gap))
        checked += 1
    assert checked == len(records) >= 16, checked


def test_b7_needs_column_survives_next_to_the_strongest_source_column(capsys):
    out = _report(capsys, "--floor", "6")
    header = _rows(_below_floor_section(out))[0]
    assert header[-1] == "Needs", header
    assert header[-2] == STRONGEST_COLUMN, header
    cells = {row[0]: row[-1] for row in _rows(_below_floor_section(out))[2:]}
    assert cells and set(cells.values()) == {"no single citation reaches floor 6"}


def test_b7_the_other_verbs_are_unchanged_and_gained_no_strongest_source(capsys):
    """The helper must not leak into any other surface, and each verb stays stable."""
    root = str(REPO_ROOT)
    for args in (["list", root], ["list", root, "--json"], ["show", "GAP-003", root],
                 ["prd", root], ["validate", root], ["taxonomy"],
                 ["scan", root, "--gaps", root]):
        assert main(list(args)) == 0, args
        first = capsys.readouterr()
        assert first.err == "", (args, first.err)
        assert first.out, args
        assert STRONGEST_COLUMN not in first.out, args
        assert main(list(args)) == 0, args
        assert capsys.readouterr().out == first.out, args


#: Observed on the live tree; pins "gained no key" exactly rather than approximately.
#: Re-baselined 8 -> 10 in iteration 110, which APPENDED `strongest_source` and `needs`
#: to `list --json` record objects. Iteration 07 pinned this set to prove the report-only
#: helper had not LEAKED into the machine payload; iteration 110 publishes it there
#: deliberately, as roadmap row 21, so the leak claim is retired and the exact-set claim
#: is kept -- an unannounced ELEVENTH key, a rename or a removal still reds here.
LIST_JSON_RECORD_KEYS = {"gap_id", "title", "layer", "gap_type", "status", "priority",
                         "confidence", "below_floor", "strongest_source", "needs"}


def test_b7_list_json_stays_a_stable_object_with_no_new_key(capsys):
    """The payload's key set is EXACTLY the pinned one, top level and per record.

    RE-BASELINED BY ITERATION 110. The name still says what this test refuses: no key
    this set does not name. What changed is the set, not the rule.

    One retired line: `strongest_source not in row` could not fail while `set(row)` is
    pinned exactly, so it was proving nothing once the key joined the set. It is spent
    instead on the two claims the set genuinely cannot see -- that the appended
    `strongest_source` is a non-empty string on EVERY record, and that `needs` is the
    DECIDED `null` exactly above the floor rather than an omitted key. The key ORDER and
    the multi-floor biconditional belong to iteration 110's own behavior module; what
    stays here is a live-register witness for both, beside the pin it re-baselines.
    """
    assert main(["list", str(REPO_ROOT), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"confidence_floor", "counts", "records"}, sorted(payload)
    rows = payload["records"]
    assert rows, payload
    for row in rows:
        assert set(row) == LIST_JSON_RECORD_KEYS, sorted(row)
        assert isinstance(row["strongest_source"], str) and row["strongest_source"], row
        assert (row["needs"] is None) == (not row["below_floor"]), row


# ---------------------------------------------------------------------------
# behavior 8 -- contract pins on the changed verb
# ---------------------------------------------------------------------------

def test_b8_report_exits_zero_ends_in_one_newline_and_says_nothing_on_stderr(capsys):
    for args in ((), ("--floor", "6")):
        assert main(["report", str(REPO_ROOT), *args]) == 0
        captured = capsys.readouterr()
        assert captured.err == "", (args, captured.err)
        assert captured.out.endswith("\n"), args
        assert not captured.out.endswith("\n\n"), args


def test_b8_report_is_byte_stable_across_calls(capsys):
    for args in ((), ("--floor", "6")):
        first = _report(capsys, *args)
        assert _report(capsys, *args) == first, args
