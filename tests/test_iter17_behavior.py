"""Iteration 17 behaviors: `radar report`'s `## By layer` table publishes the denominator.

The feature under test: the by-layer table renders one row per layer in the CLOSED
taxonomy, so a layer holding zero records renders an explicit `0` instead of vanishing,
under a one-line statement that a zero means unexamined rather than clean.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, the engineer's notes,
the reviewer's notes, or any diff. The oracles are

* `taxonomy.layer_names()`, obtained by CALLING it -- never a hand-copied list and never
  the literal `11`, so the file survives a taxonomy that legitimately grows;
* the document bytes that `render.radar_report` and `cli.main(["report", ...])` write,
  parsed by a section splitter written here from the spec's own words; and
* the spec's verbatim purpose line, quoted once as a module constant.

WHY EVERY REGISTER HERE IS SYNTHETIC
The repository's own `gaps/` register is grown by an unattended research pass, so an
assertion keyed on a live id, a live count, or on WHICH layers are empty today would go
red against a CORRECT register days from now. Every register in this module is built
under `tmp_path`. The one place a live number could leak in -- "how many layers are
there" -- is derived from `layer_names()` at assert time instead.

BEHAVIOR 8, AND WHAT THE COMMITTED LITERALS BUY
Behavior 8 says the ONLY byte change anywhere in the document is inside `## By layer`.
That is a claim about bytes, so `test_nothing_outside_the_by_layer_section_changed` pins
the two surrounding regions as verbatim literals for one fixed synthetic register: the
title, the `Records:` header line and the whole `## Ranked gaps` section before it, and
the whole `## Below confidence floor` section after it. A literal is the only oracle that
can fail if an unrelated line moves; a structural check would pass through a reworded
header. The literals also pin priority, confidence and the floor value, which the spec
declares untouched this iteration -- so a scoring change reds here, on purpose.

WHAT THIS FILE DOES NOT PROVE, STATED RATHER THAN IMPLIED
It does not read the renderer, so it cannot say the `if n` filter was deleted rather than
worked around; it asserts only the observable consequence. It says nothing about which
files the diff touched (outside this role's contract). No network is touched.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report

BY_LAYER = "## By layer"
BELOW_FLOOR = "## Below confidence floor"
RANKED = "## Ranked gaps"

#: Behavior 5 quotes this line verbatim. Kept as ONE constant so the test cannot drift
#: from the spec by a hyphen.
PURPOSE_LINE = (
    "Every layer in the closed taxonomy is listed on purpose: a zero means the layer "
    "is unexamined, not that it is clean -- it is not a target to fill."
)

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


def _register(root: pathlib.Path, records) -> pathlib.Path:
    """Write a synthetic register under `root/gaps` and return the REPO ROOT.

    The CLI accepts either a repo root or a gaps dir; returning the root exercises the
    same path a curator types.
    """
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
    end = rest.find("\n## ")
    return heading + (rest if end == -1 else rest[: end + 1])


def _data_rows(section: str) -> list[list[str]]:
    """Table cells per DATA row: pipe rows minus the header row and the alignment rule."""
    rows = []
    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells == ["Layer", "Records"] or set("".join(cells)) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def _header_record_count(out: str) -> int:
    """The N published in `Records: N | ranked: ... | below confidence floor (F): ...`."""
    for line in out.split("\n"):
        if line.startswith("Records: "):
            return int(line.removeprefix("Records: ").split(" |", 1)[0])
    raise AssertionError("no `Records: N` header line in the document")


# --- behavior 1: the table publishes the whole denominator ------------------

def test_by_layer_has_one_data_row_per_taxonomy_layer(tmp_path):
    """Behavior 1. One layer holds every record; the table still lists them all."""
    root = _register(tmp_path, [RECORD, {**RECORD, "id": "GAP-002"}])
    rows = _data_rows(_section(_render(root), BY_LAYER))
    assert len(rows) == len(taxonomy.layer_names())


def test_row_count_is_independent_of_how_many_layers_are_populated(tmp_path):
    """Behavior 1, second reading: spreading records over layers changes no row count."""
    layers = taxonomy.layer_names()
    spread = [{**RECORD, "id": f"GAP-00{i + 1}", "layer": layer}
              for i, layer in enumerate(layers[:3])]
    one = _data_rows(_section(_render(_register(tmp_path / "a", [RECORD])), BY_LAYER))
    many = _data_rows(_section(_render(_register(tmp_path / "b", spread)), BY_LAYER))
    assert len(one) == len(many) == len(layers)


# --- behavior 2: order and naming ------------------------------------------

def test_rows_are_in_taxonomy_order_with_bare_layer_names(tmp_path):
    """Behavior 2. First cell is exactly the layer name: no description, no decoration."""
    root = _register(tmp_path, [RECORD])
    rows = _data_rows(_section(_render(root), BY_LAYER))
    assert [cells[0] for cells in rows] == list(taxonomy.layer_names())


# --- behavior 3: an empty layer renders 0 ----------------------------------

def test_unpopulated_layers_render_zero_never_blank_or_dash(tmp_path):
    """Behavior 3. Every layer without a record shows the integer 0."""
    root = _register(tmp_path, [RECORD])
    rows = _data_rows(_section(_render(root), BY_LAYER))
    counts = {cells[0]: cells[1] for cells in rows}
    for layer in taxonomy.layer_names():
        if layer == RECORD["layer"]:
            continue
        assert counts[layer] == "0", layer
        assert counts[layer] not in ("", "-", "--"), layer


def test_populated_layers_render_their_true_count(tmp_path):
    """Behavior 3's other half: publishing zeros must not corrupt the real counts."""
    layers = taxonomy.layer_names()
    records = [{**RECORD, "id": "GAP-001", "layer": layers[0]},
               {**RECORD, "id": "GAP-002", "layer": layers[1]},
               {**RECORD, "id": "GAP-003", "layer": layers[1]}]
    rows = _data_rows(_section(_render(_register(tmp_path, records)), BY_LAYER))
    counts = {cells[0]: cells[1] for cells in rows}
    assert counts[layers[0]] == "1"
    assert counts[layers[1]] == "2"


# --- behavior 4: the column sums to the published record count -------------

def test_records_column_sums_to_the_header_record_count(tmp_path):
    """Behavior 4. Includes a below-floor record, which counts toward the total."""
    weak = {**RECORD, "id": "GAP-002", "layer": taxonomy.layer_names()[4],
            "evidence": [{**RECORD["evidence"][0], "source_class": "model-output"}]}
    out = _render(_register(tmp_path, [RECORD, weak]))
    rows = _data_rows(_section(out, BY_LAYER))
    assert sum(int(cells[1]) for cells in rows) == _header_record_count(out) == 2


# --- behavior 5: the purpose line ------------------------------------------

def test_purpose_line_appears_exactly_once_verbatim(tmp_path):
    out = _render(_register(tmp_path, [RECORD]))
    assert out.count(PURPOSE_LINE) == 1


def test_purpose_line_sits_between_heading_and_table_with_one_blank_each_side(tmp_path):
    """Behavior 5's blank-line shape, asserted positionally rather than by substring."""
    section = _section(_render(_register(tmp_path, [RECORD])), BY_LAYER)
    lines = section.split("\n")
    assert lines[0] == BY_LAYER
    assert lines[1] == ""
    assert lines[2] == PURPOSE_LINE
    assert lines[3] == ""
    assert lines[4] == "| Layer | Records |"


def test_by_layer_section_shape_matches_the_below_floor_section(tmp_path):
    """Behavior 5's parity clause: same heading/blank/prose/blank/table shape."""
    weak = {**RECORD, "id": "GAP-002",
            "evidence": [{**RECORD["evidence"][0], "source_class": "model-output"}]}
    out = _render(_register(tmp_path, [RECORD, weak]))

    def shape(section: str) -> list[str]:
        lines = section.split("\n")
        return ["heading" if i == 0 else
                "blank" if line == "" else
                "table" if line.startswith("|") else "prose"
                for i, line in enumerate(lines[:5])]

    assert shape(_section(out, BY_LAYER)) == ["heading", "blank", "prose", "blank", "table"]
    assert shape(_section(out, BELOW_FLOOR)) == shape(_section(out, BY_LAYER))


# --- behavior 6: the empty register ---------------------------------------

def test_empty_register_still_publishes_every_layer_at_zero():
    """Behavior 6, through the renderer with zero records."""
    out = radar_report([])
    rows = _data_rows(_section(out, BY_LAYER))
    assert [cells[0] for cells in rows] == list(taxonomy.layer_names())
    assert {cells[1] for cells in rows} == {"0"}
    assert _header_record_count(out) == 0
    assert PURPOSE_LINE in out


# --- behavior 7: the CLI contract ----------------------------------------

def test_cli_report_exits_zero_with_stdout_only_and_one_trailing_newline(tmp_path, capsys):
    root = _register(tmp_path, [RECORD])
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("# Agent infrastructure gap radar\n")
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")
    rows = _data_rows(_section(captured.out, BY_LAYER))
    assert len(rows) == len(taxonomy.layer_names())


def test_cli_report_is_byte_identical_across_runs_and_to_the_renderer(tmp_path, capsys):
    """Determinism: the published surface must not depend on dict or filesystem order."""
    root = _register(tmp_path, [RECORD, {**RECORD, "id": "GAP-002",
                                         "layer": taxonomy.layer_names()[-1]}])
    assert main(["report", str(root)]) == 0
    first = capsys.readouterr().out
    assert main(["report", str(root)]) == 0
    assert capsys.readouterr().out == first == _render(root)


# --- behavior 8: the blast radius ----------------------------------------

#: The fixed register behavior 8 is measured over: one ranked record, one below-floor
#: record. Ids, titles and layers are chosen here, so these literals are stable.
_B8_WEAK = {**RECORD, "id": "GAP-002", "title": "A weakly evidenced thing",
            "evidence": [{**RECORD["evidence"][0], "source_class": "model-output"}]}

_B8_BEFORE = (
    "# Agent infrastructure gap radar\n"
    "\n"
    "Records: 2 | ranked: 1 | below confidence floor (2): 1\n"
    "\n"
    "## Ranked gaps\n"
    "\n"
    "| Rank | ID | Priority | Confidence | Layer | Type | Title |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| 1 | GAP-001 | 8.7 | 5 | orchestration | missing-contract | A thing is broken |\n"
    "\n"
)

_B8_AFTER = (
    "## Below confidence floor\n"
    "\n"
    "Kept visible on purpose: a weakly-sourced gap is a research task, not a deletion.\n"
    "\n"
    "| ID | Priority | Confidence | Title | Strongest source | Needs |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| GAP-002 | 8.7 | 0 | A weakly evidenced thing | model-output "
    "| weight >= 3: practitioner-report, survey-aggregate |\n"
)


def test_nothing_outside_the_by_layer_section_changed(tmp_path):
    """Behavior 8. The regions before and after `## By layer` are pinned as bytes."""
    out = _render(_register(tmp_path, [RECORD, _B8_WEAK]))
    before, rest = out.split(BY_LAYER, 1)
    by_layer, after = rest.split(BELOW_FLOOR, 1)
    assert before == _B8_BEFORE
    assert BELOW_FLOOR + after == _B8_AFTER
    assert PURPOSE_LINE in by_layer
    assert PURPOSE_LINE not in before and PURPOSE_LINE not in after


def test_the_ranked_section_is_unaffected_by_empty_layers(tmp_path):
    """Behavior 8, narrowed: a zero-record layer never reaches ranking or the floor."""
    out = _render(_register(tmp_path, [RECORD, _B8_WEAK]))
    ranked = _section(out, RANKED)
    below = _section(out, BELOW_FLOOR)
    for layer in taxonomy.layer_names():
        if layer == RECORD["layer"]:
            continue
        assert layer not in ranked, layer
        assert layer not in below, layer
    assert "GAP-002" not in ranked and "GAP-002" in below


@pytest.mark.parametrize("count", [0, 1, 3])
def test_row_count_holds_across_register_sizes(tmp_path, count):
    """Behaviors 1 and 6 together: the denominator is published at any size."""
    records = [{**RECORD, "id": f"GAP-00{i + 1}"} for i in range(count)]
    out = radar_report([]) if count == 0 else _render(_register(tmp_path, records))
    assert len(_data_rows(_section(out, BY_LAYER))) == len(taxonomy.layer_names())
    assert _header_record_count(out) == count
