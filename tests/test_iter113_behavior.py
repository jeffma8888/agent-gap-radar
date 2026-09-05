"""Iteration 113 behaviors: `radar report` publishes TAG COVERAGE.

The feature under test: one additional level-2 section, `## Tag coverage`, publishing the
census of the register's only cross-layer axis -- the `tags` field every record writes and
no shipped surface read -- as a DISPLAY that derives no penalty, drops no record, caps no
table and rewrites no register data.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, `tools/*.py` text, the
engineer's notes, the reviewer's notes, `fix_review.md`, `IMPLEMENTATION.patch`, or any
diff. The oracles are

* the spec's own verbatim census template, quoted once as a module constant, and
* the document bytes `render.radar_report` and `cli.main(["report", ...])` write, sliced by
  a section splitter written here from the spec's words, and
* two direct calls into the published `scoring` functions the spec names (behavior 10).

WHY EVERY REGISTER HERE IS SYNTHETIC
The repository's own `gaps/` register is grown by an unattended research pass, so an
assertion keyed on a live tag value, a live count, a live layer set or a live id would go
red against a CORRECT register days from now. Every register in this module is built under
pytest's `tmp_path`, every tag value is invented here, every layer name is taken from
`taxonomy.layer_names()` BY CALLING IT, and every locator is under the reserved
`example.test` domain. Nothing here reaches the network.

STRUCTURAL NOTES, so this file cannot lie later:

* **The census is proved DERIVED, not literal.** Behavior 2 renders two registers whose tag
  graphs differ and requires all four integers to move with the data, and every register in
  the file re-checks the two self-validating identities rather than pinning a number.
* **The row order is proved to be the TOTAL order the spec names, two-sided.** Behavior 5
  uses a register in which `Records` DESC and `Tag` ASC disagree, so an implementation that
  sorted on either key alone cannot pass.
* **The `Records` column is proved to count DISTINCT RECORDS, not mentions.** Behavior 7
  gives one record the same tag twice and requires the count to stay at what the records
  say, and its layer set to gain nothing.
* **The two no-data cases are proved DIFFERENT.** Behavior 9 asserts the empty-register body
  and the no-shared-tag body are not the same bytes, and that only the second carries a
  census, so "no record exists" and "no tag is shared" cannot collapse into one answer.
* **The byte pins are IMPORTED, never restated.** Behavior 11 imports iteration 17's
  committed literals and iteration 89's own section constant, so this file cannot silently
  re-baseline the pins whose job is to catch unrelated movement.
* **The live register is asserted on SHAPE and on SELF-CONSISTENCY only** -- the rendered
  `listed` must equal the number of rows and `cross` must equal the number of rows whose
  `Layers` cell holds more than one layer, both re-derived from the document at assert time.
* **No exact heading-SET or heading-COUNT for `radar report` is asserted anywhere here.**
* **No absolute machine path and no personal or employer identifier appears here.**
"""

from __future__ import annotations

import importlib
import json
import pathlib
import types

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report
from agent_gap_radar.taxonomy import layer_names

RANKED = "## Ranked gaps"
BY_LAYER = "## By layer"
EVIDENCE_AGE = "## Evidence age"
CONCENTRATION = "## Source concentration"
TAG_COVERAGE = "## Tag coverage"
BELOW_FLOOR = "## Below confidence floor"

#: Behavior 2 quotes this line verbatim except for the four counts. Kept as ONE template so
#: the test cannot drift from the spec by a separator or a preposition.
CENSUS_TEMPLATE = (
    "Distinct tag values: {distinct} | "
    "listed below (2 or more records): {listed} | "
    "of those, spanning more than one layer: {cross} | "
    "occurring on exactly one record and omitted: {omitted}"
)
CENSUS_PREFIX = "Distinct tag values: "

#: Behavior 4 fixes the table header.
TABLE_HEADER = "| Tag | Records | Layers |"

#: Behavior 9 reuses the convention `## Evidence age` and `## Source concentration` use.
NONE_FOUND = "None found."

#: Every locator in this module is built from this base, so no live locator is restated.
BASE = "https://example.test"

#: Layers are CALLED for, never retyped: a taxonomy that legitimately grows must not red
#: this file, and the closed taxonomy is the only source of a valid `layer`.
LAYERS = sorted(layer_names())
L0, L1, L2 = LAYERS[0], LAYERS[1], LAYERS[2]

_RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": L0,
    "gap_type": "missing-contract", "problem": "p", "symptom": "the symptom text",
    "why_now": "w", "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"],
    "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": f"{BASE}/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _rec(gap_id: str, layer: str, tags: list[str] | None = None) -> dict:
    """A valid record in `layer`. `tags=None` omits the key entirely (behavior 8)."""
    record = {**_RECORD, "id": gap_id, "title": f"Record {gap_id}", "layer": layer}
    if tags is not None:
        record["tags"] = list(tags)
    return record


def _register(root: pathlib.Path, records) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for record in records:
        (d / f"{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def _load(root: pathlib.Path):
    return load_all(root / "gaps")


def _render(root: pathlib.Path) -> str:
    return radar_report(_load(root))


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


def _census(section: str) -> str:
    return _body_lines(section)[0]


def _census_numbers(section: str) -> tuple[int, int, int, int]:
    """The four published integers, parsed PER SEGMENT so a threshold word in the prose
    (`2 or more records`) cannot be scraped as one of them."""
    segments = _census(section).split(" | ")
    assert len(segments) == 4, segments
    return tuple(int(seg.rsplit(": ", 1)[1]) for seg in segments)  # type: ignore[return-value]


def _tags_section(root: pathlib.Path) -> str:
    return _section(_render(root), TAG_COVERAGE)


def _assert_identities(section: str) -> tuple[int, int, int, int]:
    distinct, listed, cross, omitted = _census_numbers(section)
    assert distinct == listed + omitted, (distinct, listed, omitted)
    assert cross <= listed, (cross, listed)
    return distinct, listed, cross, omitted


# --- behavior 1: the section exists once, in one fixed position -------------


def test_b1_report_publishes_a_tag_coverage_section(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", L0, ["alpha"])]))
    assert TAG_COVERAGE in out


def test_b1_the_heading_is_a_whole_line_and_occurs_exactly_once(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                       _rec("GAP-002", L1, ["alpha"])]))
    assert [line for line in out.split("\n") if line == TAG_COVERAGE] == [TAG_COVERAGE]
    assert out.count(TAG_COVERAGE) == 1


def test_b1_it_sits_after_source_concentration_and_before_the_below_floor_section(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                       _rec("GAP-002", L1, ["alpha"])]))
    order = [out.index(h) for h in (RANKED, BY_LAYER, EVIDENCE_AGE, CONCENTRATION,
                                    TAG_COVERAGE, BELOW_FLOOR)]
    assert order == sorted(order), out


def test_b1_the_cli_exits_zero_with_empty_stderr_and_the_section_present(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["alpha"])])
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"\n{TAG_COVERAGE}\n" in captured.out


# --- behavior 2: the census line, derived from the register -----------------

#: alpha: GAP-001+GAP-002, layers L0+L1 -> listed and CROSS. beta: GAP-001+GAP-003, both
#: L0 -> listed, NOT cross. gamma, delta: one record each -> omitted.
_CENSUS_A = [_rec("GAP-001", L0, ["alpha", "beta"]),
             _rec("GAP-002", L1, ["alpha"]),
             _rec("GAP-003", L0, ["beta", "gamma"]),
             _rec("GAP-004", L2, ["delta"])]

#: x: 3 records over L0+L1 -> cross. y: 2 records over L1+L2 -> cross. z: 1 -> omitted.
_CENSUS_B = [_rec("GAP-001", L0, ["x"]),
             _rec("GAP-002", L0, ["x"]),
             _rec("GAP-003", L1, ["x", "y"]),
             _rec("GAP-004", L2, ["y"]),
             _rec("GAP-005", L2, ["z"])]


def test_b2_census_line_is_the_specs_template_with_the_four_counts_substituted(tmp_path):
    section = _tags_section(_register(tmp_path, _CENSUS_A))
    assert _census(section) == CENSUS_TEMPLATE.format(distinct=4, listed=2, cross=1,
                                                      omitted=2)


def test_b2_all_four_counts_follow_the_data_not_a_literal(tmp_path):
    """A second, differently shaped tag graph must publish four different numbers."""
    first = _census(_tags_section(_register(tmp_path / "a", _CENSUS_A)))
    second = _census(_tags_section(_register(tmp_path / "b", _CENSUS_B)))
    assert second == CENSUS_TEMPLATE.format(distinct=3, listed=2, cross=2, omitted=1)
    assert first != second


def test_b2_both_identities_hold_on_both_registers(tmp_path):
    for name, records in (("a", _CENSUS_A), ("b", _CENSUS_B)):
        section = _tags_section(_register(tmp_path / name, records))
        distinct, listed, cross, omitted = _assert_identities(section)
        assert (distinct, listed, cross, omitted) != (0, 0, 0, 0), name


def test_b2_the_census_is_the_first_non_blank_line_under_the_heading(tmp_path):
    section = _tags_section(_register(tmp_path, _CENSUS_A))
    assert _body_lines(section)[0].startswith(CENSUS_PREFIX)


def test_b2_listed_equals_the_number_of_rendered_rows(tmp_path):
    """The census cannot claim a row count the table does not render."""
    for name, records in (("a", _CENSUS_A), ("b", _CENSUS_B)):
        section = _tags_section(_register(tmp_path / name, records))
        _distinct, listed, _cross, _omitted = _census_numbers(section)
        assert listed == len(_data_rows(section)), name


def test_b2_cross_equals_the_rows_whose_layer_cell_names_more_than_one_layer(tmp_path):
    for name, records in (("a", _CENSUS_A), ("b", _CENSUS_B)):
        section = _tags_section(_register(tmp_path / name, records))
        _distinct, _listed, cross, _omitted = _census_numbers(section)
        multi = [row for row in _data_rows(section) if ", " in row[2]]
        assert cross == len(multi), (name, cross, multi)


# --- behavior 3: the purpose line states all three claims ------------------

#: Behavior 3 names three CLAIMS but quotes no verbatim string, so this file tests the
#: most reasonable reading: one line, immediately under the census, carrying every claim.
#: The token list is the ambiguity, and it is reported as PM feedback in `tester.md`.
_PURPOSE_TOKENS = ("free label", "closed vocabulary", "priority", "confidence",
                   "one record", "one layer", "omitted", "spelling", "curation")


def test_b3_the_purpose_region_is_exactly_one_line_under_the_census(tmp_path):
    section = _tags_section(_register(tmp_path, _CENSUS_A))
    body = _body_lines(section)
    header_at = body.index(TABLE_HEADER)
    assert header_at == 2, body[:header_at]


def test_b3_the_purpose_line_states_all_three_claims(tmp_path):
    section = _tags_section(_register(tmp_path, _CENSUS_A))
    purpose = _body_lines(section)[1].lower()
    missing = [token for token in _PURPOSE_TOKENS if token not in purpose]
    assert not missing, (missing, purpose)


def test_b3_the_purpose_line_disclaims_the_ranking_and_the_floor(tmp_path):
    purpose = _body_lines(_tags_section(_register(tmp_path, _CENSUS_A)))[1].lower()
    assert "rank" in purpose
    assert "floor" in purpose


# --- behavior 4: the table, its headers and its three columns ---------------


def test_b4_the_table_headers_are_exactly_tag_records_layers(tmp_path):
    section = _tags_section(_register(tmp_path, _CENSUS_A))
    lines = [line for line in section.split("\n") if line.startswith("|")]
    assert lines[0] == TABLE_HEADER
    assert set(lines[1].strip("|").replace(" ", "")) == {"-", "|"}
    assert lines[1].count("|") == lines[0].count("|")


def test_b4_one_row_per_tag_reaching_two_distinct_records(tmp_path):
    rows = _data_rows(_tags_section(_register(tmp_path, _CENSUS_A)))
    assert [row[0] for row in rows] == ["alpha", "beta"]
    assert "gamma" not in {row[0] for row in rows}
    assert "delta" not in {row[0] for row in rows}


def test_b4_records_is_the_count_of_distinct_records_carrying_the_tag(tmp_path):
    rows = {row[0]: row[1] for row in _data_rows(_tags_section(
        _register(tmp_path, _CENSUS_B)))}
    assert rows == {"x": "3", "y": "2"}


def test_b4_layers_are_the_distinct_layers_ascending_joined_by_comma_space(tmp_path):
    rows = {row[0]: row[2] for row in _data_rows(_tags_section(
        _register(tmp_path, _CENSUS_B)))}
    assert rows["x"] == ", ".join(sorted({L0, L1}))
    assert rows["y"] == ", ".join(sorted({L1, L2}))


def test_b4_a_layer_carrying_the_tag_twice_is_named_once(tmp_path):
    """GAP-001 and GAP-002 both sit in L0, so `dup`'s layer cell must not repeat it."""
    root = _register(tmp_path, [_rec("GAP-001", L0, ["dup"]),
                                _rec("GAP-002", L0, ["dup"])])
    rows = _data_rows(_tags_section(root))
    assert [row[0] for row in rows] == ["dup"]
    assert rows[0][1] == "2"
    assert rows[0][2] == L0


# --- behavior 5: the row order is a total order ----------------------------

#: `zeta` has 3 records, `alpha` and `beta` have 2 each: count DESC and tag ASC disagree,
#: so sorting on either key alone cannot pass.
_ORDER = [_rec("GAP-001", L0, ["zeta", "alpha"]),
          _rec("GAP-002", L1, ["zeta", "alpha"]),
          _rec("GAP-003", L2, ["zeta", "beta"]),
          _rec("GAP-004", L0, ["beta"])]


def test_b5_rows_are_records_descending_then_tag_ascending(tmp_path):
    rows = _data_rows(_tags_section(_register(tmp_path, _ORDER)))
    assert [row[0] for row in rows] == ["zeta", "alpha", "beta"]
    assert [row[1] for row in rows] == ["3", "2", "2"]


def test_b5_the_order_is_not_merely_alphabetical(tmp_path):
    """Two-sided companion: a tag-ascending sort would put `alpha` first."""
    rows = _data_rows(_tags_section(_register(tmp_path, _ORDER)))
    assert [row[0] for row in rows] != sorted(row[0] for row in rows)


def test_b5_two_renders_are_byte_identical_and_end_in_exactly_one_newline(tmp_path, capsys):
    root = _register(tmp_path, _ORDER)
    assert main(["report", str(root)]) == 0
    first = capsys.readouterr().out
    assert main(["report", str(root)]) == 0
    assert capsys.readouterr().out == first == _render(root)
    assert first.endswith("\n") and not first.endswith("\n\n")


# --- behavior 6: the table is uncapped -------------------------------------


def test_b6_every_tag_reaching_two_records_appears_however_long_the_tail(tmp_path):
    tags = [f"tag-{i:02d}" for i in range(25)]
    records = [_rec("GAP-001", L0, tags), _rec("GAP-002", L1, tags)]
    section = _tags_section(_register(tmp_path, records))
    rows = _data_rows(section)
    assert [row[0] for row in rows] == sorted(tags)
    assert len(rows) == 25
    distinct, listed, cross, omitted = _assert_identities(section)
    assert (distinct, listed, cross, omitted) == (25, 25, 25, 0)


# --- behavior 7: a repeated tag on one record counts once ------------------


def test_b7_a_record_naming_a_tag_twice_contributes_one_record_and_one_layer(tmp_path):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["dup", "dup"]),
                                _rec("GAP-002", L1, ["dup"])])
    section = _tags_section(root)
    rows = _data_rows(section)
    assert rows == [["dup", "2", ", ".join(sorted({L0, L1}))]]
    assert _census_numbers(section) == (1, 1, 1, 0)


def test_b7_a_tag_repeated_on_one_record_alone_does_not_reach_two_records(tmp_path):
    """The count is of RECORDS, so one record naming a tag twice stays omitted."""
    section = _tags_section(_register(tmp_path, [_rec("GAP-001", L0, ["dup", "dup"])]))
    assert _census_numbers(section) == (1, 0, 0, 1)
    assert TABLE_HEADER not in section
    assert NONE_FOUND in section


# --- behavior 8: missing and empty tag lists are silent --------------------


def test_b8_a_record_with_no_tags_key_or_an_empty_list_contributes_nothing(tmp_path):
    root = _register(tmp_path, [_rec("GAP-001", L0), _rec("GAP-002", L1, [])])
    section = _tags_section(root)
    assert _census_numbers(section) == (0, 0, 0, 0)
    _assert_identities(section)
    assert TABLE_HEADER not in section


def test_b8_untagged_records_do_not_disturb_the_census_of_tagged_ones(tmp_path):
    root = _register(tmp_path, [_rec("GAP-001", L0),
                                _rec("GAP-002", L1, []),
                                _rec("GAP-003", L0, ["shared"]),
                                _rec("GAP-004", L2, ["shared"])])
    section = _tags_section(root)
    assert _census_numbers(section) == (1, 1, 1, 0)
    assert _data_rows(section) == [["shared", "2", ", ".join(sorted({L0, L2}))]]


def test_b8_a_register_of_only_untagged_records_still_exits_zero(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", L0), _rec("GAP-002", L1, [])])
    assert main(["report", str(root)]) == 0
    assert capsys.readouterr().err == ""


# --- behavior 9: the two no-data cases are different answers ---------------


def test_b9_an_empty_register_renders_the_heading_and_none_found_and_nothing_else(tmp_path):
    section = _tags_section(_register(tmp_path, []))
    assert _body_lines(section) == [NONE_FOUND]
    assert CENSUS_PREFIX not in section
    assert TABLE_HEADER not in section


def test_b9_a_register_with_no_shared_tag_keeps_the_census_and_the_purpose_line(tmp_path):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["solo-a"]),
                                _rec("GAP-002", L1, ["solo-b"])])
    section = _tags_section(root)
    body = _body_lines(section)
    assert len(body) == 3, body
    assert body[0] == CENSUS_TEMPLATE.format(distinct=2, listed=0, cross=0, omitted=2)
    assert body[2] == NONE_FOUND
    assert TABLE_HEADER not in section


def test_b9_the_two_no_data_bodies_do_not_share_prose(tmp_path):
    empty = _tags_section(_register(tmp_path / "empty", []))
    unshared = _tags_section(_register(tmp_path / "unshared",
                                       [_rec("GAP-001", L0, ["solo-a"]),
                                        _rec("GAP-002", L1, ["solo-b"])]))
    assert empty != unshared
    assert CENSUS_PREFIX in unshared
    assert CENSUS_PREFIX not in empty
    assert len(_body_lines(unshared)) > len(_body_lines(empty))


# --- behavior 10: the derivation is published in `scoring` -----------------


def _duck(layer: str, tags):
    """A record exposing ONLY the two attributes behavior 10 allows the functions to read."""
    return types.SimpleNamespace(layer=layer, tags=tags)


_DUCK_SET = [_duck(L0, ["alpha", "beta"]), _duck(L1, ["alpha"]),
             _duck(L0, ["beta", "gamma"]), _duck(L2, ["delta"])]


def test_b10_scoring_publishes_distinct_tags_and_tag_coverage(tmp_path):
    scoring = importlib.import_module("agent_gap_radar.scoring")
    gaps = _load(_register(tmp_path, _CENSUS_A))
    assert scoring.distinct_tags(gaps) == 4
    rows = scoring.tag_coverage(gaps)
    assert rows == [("alpha", 2, sorted({L0, L1})), ("beta", 2, [L0])]


def test_b10_tag_coverage_returns_the_rendered_rows_in_the_rendered_order(tmp_path):
    scoring = importlib.import_module("agent_gap_radar.scoring")
    root = _register(tmp_path, _ORDER)
    rows = scoring.tag_coverage(_load(root))
    rendered = _data_rows(_tags_section(root))
    assert [tag for tag, _n, _layers in rows] == [row[0] for row in rendered]
    assert [str(n) for _tag, n, _layers in rows] == [row[1] for row in rendered]
    assert [", ".join(layers) for _tag, _n, layers in rows] == [row[2] for row in rendered]


def test_b10_omitted_is_derived_as_distinct_minus_listed(tmp_path):
    """Identity 1 of behavior 2 must hold BY CONSTRUCTION, not by a second count."""
    scoring = importlib.import_module("agent_gap_radar.scoring")
    for name, records in (("a", _CENSUS_A), ("b", _CENSUS_B), ("o", _ORDER)):
        root = _register(tmp_path / name, records)
        gaps = _load(root)
        distinct, listed, _cross, omitted = _census_numbers(_tags_section(root))
        assert distinct == scoring.distinct_tags(gaps), name
        assert listed == len(scoring.tag_coverage(gaps)), name
        assert omitted == scoring.distinct_tags(gaps) - len(scoring.tag_coverage(gaps)), name


def test_b10_both_functions_run_on_objects_exposing_only_layer_and_tags():
    scoring = importlib.import_module("agent_gap_radar.scoring")
    assert scoring.distinct_tags(_DUCK_SET) == 4
    assert scoring.tag_coverage(_DUCK_SET) == [("alpha", 2, sorted({L0, L1})),
                                               ("beta", 2, [L0])]


def test_b10_both_functions_are_total_on_records_with_no_tags_attribute_value():
    scoring = importlib.import_module("agent_gap_radar.scoring")
    gaps = [_duck(L0, []), _duck(L1, [])]
    assert scoring.distinct_tags(gaps) == 0
    assert scoring.tag_coverage(gaps) == []
    assert scoring.distinct_tags([]) == 0
    assert scoring.tag_coverage([]) == []


def test_b10_scoring_still_imports_with_pydantic_absent():
    """Proved the way the committed test proves it -- the blocker is IMPORTED, not rewritten."""
    import test_iter73_behavior as it73

    with it73.pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        assert callable(module.distinct_tags)
        assert callable(module.tag_coverage)
        assert module.distinct_tags(_DUCK_SET) == 4
        assert module.tag_coverage(_DUCK_SET) == [("alpha", 2, sorted({L0, L1})),
                                                 ("beta", 2, [L0])]


# --- behavior 11: no other byte of the report, and no other verb, moves ----


def test_b11_iteration_17_byte_pins_still_hold_unedited(tmp_path):
    """Imported, not restated: this file must not be able to re-baseline that pin."""
    import test_iter17_behavior as it17

    out = _render(_register(tmp_path, [it17.RECORD, it17._B8_WEAK]))
    before, rest = out.split(BY_LAYER, 1)
    _by_layer, after = rest.split(BELOW_FLOOR, 1)
    assert before == it17._B8_BEFORE
    assert BELOW_FLOOR + after == it17._B8_AFTER


def test_b11_the_new_section_lives_strictly_between_concentration_and_below_floor(tmp_path):
    import test_iter17_behavior as it17

    out = _render(_register(tmp_path, [it17.RECORD, it17._B8_WEAK]))
    head, tail = out.split(CONCENTRATION, 1)
    assert TAG_COVERAGE not in head
    middle, after_floor = tail.split(BELOW_FLOOR, 1)
    assert TAG_COVERAGE in middle
    assert TAG_COVERAGE not in after_floor


def test_b11_iteration_89s_own_section_constant_is_unchanged(tmp_path):
    """Imported so a reworded neighbour reds here rather than passing silently."""
    import test_iter89_behavior as it89

    assert it89.CONCENTRATION == CONCENTRATION
    out = _render(_register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                       _rec("GAP-002", L1, ["alpha"])]))
    assert it89.CONCENTRATION in out
    assert out.index(it89.CONCENTRATION) < out.index(TAG_COVERAGE)


def test_b11_no_other_verb_prints_the_section_or_its_prose(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                _rec("GAP-002", L1, ["alpha"])])
    other = _register(tmp_path / "other", [_rec("GAP-001", L0, ["alpha"])])
    argvs = [["list", str(root)], ["list", "--json", str(root)],
             ["show", "GAP-001", str(root)], ["prd", "--gap", "GAP-001", str(root)],
             ["validate", str(root)], ["taxonomy"],
             ["diff", str(other), str(root)]]
    for argv in argvs:
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        assert captured.err == "", argv
        assert "Tag coverage" not in captured.out, argv
        assert TABLE_HEADER not in captured.out, argv
        assert CENSUS_PREFIX not in captured.out, argv


def test_b11_list_json_carries_no_tag_coverage_key(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                _rec("GAP-002", L1, ["alpha"])])
    assert main(["list", "--json", str(root)]) == 0
    blob = json.dumps(json.loads(capsys.readouterr().out))
    for token in ("tag_coverage", "distinct_tags", "tagcoverage", "Tag coverage"):
        assert token not in blob, token


# --- the live register: shape and self-consistency only -------------------


def test_live_register_renders_the_section_and_validates_its_own_census(capsys):
    """No live tag, count, layer set or id is pinned: every number is RE-DERIVED here."""
    root = pathlib.Path(__file__).resolve().parent.parent
    if not (root / "gaps").is_dir():  # pragma: no cover - the register always ships
        return
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")
    section = _section(captured.out, TAG_COVERAGE)
    distinct, listed, cross, omitted = _assert_identities(section)
    rows = _data_rows(section)
    # Non-vacuity guard: every loop assertion below is over `rows`, so an empty table would
    # let them all pass silently. This is a SHAPE claim ("the live register shares at least
    # one tag"), not a pinned count -- no live number appears in this module.
    assert rows, "the live register renders no shared tag; the loop assertions are vacuous"
    assert listed == len(rows), (listed, len(rows))
    assert cross == len([row for row in rows if ", " in row[2]])
    assert len({row[0] for row in rows}) == len(rows), "a tag is rendered twice"
    assert all(int(row[1]) >= 2 for row in rows), rows
    counts = [int(row[1]) for row in rows]
    assert list(zip([-c for c in counts], [row[0] for row in rows])) == sorted(
        zip([-c for c in counts], [row[0] for row in rows])), "row order is not total"
    for row in rows:
        layers = row[2].split(", ")
        assert layers == sorted(set(layers)), row
        assert set(layers) <= set(LAYERS), row
    assert omitted == distinct - listed


def test_live_register_scoring_functions_agree_with_the_rendered_document(capsys):
    scoring = importlib.import_module("agent_gap_radar.scoring")
    root = pathlib.Path(__file__).resolve().parent.parent
    if not (root / "gaps").is_dir():  # pragma: no cover - the register always ships
        return
    gaps = load_all(root / "gaps")
    assert main(["report", str(root)]) == 0
    section = _section(capsys.readouterr().out, TAG_COVERAGE)
    distinct, listed, _cross, _omitted = _census_numbers(section)
    assert distinct == scoring.distinct_tags(gaps)
    assert listed == len(scoring.tag_coverage(gaps))


# --- additions made in THIS round (not inherited from the preserved module) -------------
#
# Every test below was written in this round against the spec's own words: the preserved
# starting-point module did not cover the named threshold constant, the parser-surface half
# of behavior 11, the "no tag term reaches the ranking" acceptance criterion, or an
# INDEPENDENT recount of the live register's rows.


# --- behavior 10 (cont.): the threshold is a NAMED constant, and it drives the table ----


def test_b10_tag_coverage_min_records_is_a_named_module_constant():
    scoring = importlib.import_module("agent_gap_radar.scoring")
    minimum = scoring.TAG_COVERAGE_MIN_RECORDS
    assert isinstance(minimum, int) and not isinstance(minimum, bool)
    assert minimum >= 2


def test_b10_the_named_constant_is_the_threshold_the_table_actually_applies(tmp_path):
    """Fixtures are sized FROM the constant, so a change to it moves this test's oracle."""
    scoring = importlib.import_module("agent_gap_radar.scoring")
    minimum = scoring.TAG_COVERAGE_MIN_RECORDS
    below = [_rec(f"GAP-{i:03d}", LAYERS[i % len(LAYERS)], ["under"])
             for i in range(1, minimum)]
    at = [_rec(f"GAP-{i:03d}", LAYERS[i % len(LAYERS)], ["under", "over"])
          for i in range(1, minimum + 1)]
    under_section = _tags_section(_register(tmp_path / "under", below))
    assert [row[0] for row in _data_rows(under_section)] == []
    assert NONE_FOUND in under_section
    at_section = _tags_section(_register(tmp_path / "at", at))
    assert [row[0] for row in _data_rows(at_section)] == ["over", "under"]
    assert all(int(row[1]) == minimum for row in _data_rows(at_section))


def test_b10_the_withheld_population_is_announced_and_never_truncated(tmp_path):
    """Acceptance: the count the threshold withholds is PUBLISHED, not silently dropped."""
    singletons = [_rec(f"GAP-{i:03d}", LAYERS[i % len(LAYERS)], [f"solo-{i:03d}"])
                  for i in range(1, 13)]
    shared = [_rec("GAP-900", L0, ["shared"]), _rec("GAP-901", L1, ["shared"])]
    section = _tags_section(_register(tmp_path, singletons + shared))
    distinct, listed, cross, omitted = _assert_identities(section)
    assert omitted == len(singletons)
    assert listed == len(_data_rows(section)) == 1
    assert distinct == len(singletons) + 1
    assert cross == 1


# --- behavior 11 (cont.): the parser surface is unchanged ------------------------------


def test_b11_the_verb_surface_is_still_the_shipped_eight_and_gains_no_tags_verb():
    """The pin is IMPORTED from iteration 16, never restated here."""
    import test_iter16_behavior as it16

    choices = it16.parser_choices()
    assert len(choices) == 8, sorted(choices)
    for absent in ("tags", "tag", "coverage"):
        assert absent not in choices, absent


def test_b11_no_verb_accepts_a_tag_selector(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", L0, ["alpha"]),
                                _rec("GAP-002", L1, ["alpha"])])
    for argv in (["list", "--tag", "alpha", str(root)],
                 ["report", "--tag", "alpha", str(root)],
                 ["show", "GAP-001", "--tag", "alpha", str(root)],
                 ["tags", str(root)]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2, argv
        captured = capsys.readouterr()
        assert TAG_COVERAGE not in captured.out, argv
        assert CENSUS_PREFIX not in captured.out, argv


# --- acceptance: no tag term reaches priority, confidence, rank or the floor ------------


_SCORED = [_rec("GAP-001", L0), _rec("GAP-002", L1), _rec("GAP-003", L2)]


def _retagged(records, tags_by_index):
    out = []
    for index, record in enumerate(records):
        clone = dict(record)
        clone["tags"] = list(tags_by_index[index])
        out.append(clone)
    return out


def test_acceptance_tags_change_only_the_new_section_and_nothing_else(tmp_path):
    """Two registers differing ONLY in their tag lists must render an identical document
    outside `## Tag coverage` -- so no tag term can reach priority, confidence, the
    ranking or the below-floor partition."""
    plain = _render(_register(tmp_path / "plain", _retagged(
        _SCORED, [["a", "b"], ["a"], ["c"]])))
    other = _render(_register(tmp_path / "other", _retagged(
        _SCORED, [["z"], ["z", "y"], ["y", "x", "w"]])))
    assert plain != other, "the fixtures must differ somewhere"
    head_plain, rest_plain = plain.split(TAG_COVERAGE, 1)
    head_other, rest_other = other.split(TAG_COVERAGE, 1)
    assert head_plain == head_other
    assert (BELOW_FLOOR + rest_plain.split(BELOW_FLOOR, 1)[1]
            == BELOW_FLOOR + rest_other.split(BELOW_FLOOR, 1)[1])


def test_acceptance_the_list_verb_is_byte_identical_under_different_tags(tmp_path, capsys):
    assert main(["list", str(_register(tmp_path / "plain", _retagged(
        _SCORED, [["a", "b"], ["a"], ["c"]])))]) == 0
    first = capsys.readouterr().out
    assert main(["list", str(_register(tmp_path / "other", _retagged(
        _SCORED, [["z"], ["z", "y"], ["y", "x", "w"]])))]) == 0
    assert capsys.readouterr().out == first


# --- an INDEPENDENT recount of the live register's rows --------------------------------


def test_live_register_rows_match_a_second_oracle_built_here(capsys):
    """The rendered table is checked against a counter written in THIS file from the
    spec's words (distinct records per tag; distinct layers ascending; count DESC then
    tag ASC), not against the function that produced it. No live value is pinned."""
    root = pathlib.Path(__file__).resolve().parent.parent
    if not (root / "gaps").is_dir():  # pragma: no cover - the register always ships
        return
    gaps = load_all(root / "gaps")
    counts: dict[str, int] = {}
    layers: dict[str, set[str]] = {}
    for gap in gaps:
        for tag in sorted(set(getattr(gap, "tags", []) or [])):
            counts[tag] = counts.get(tag, 0) + 1
            layers.setdefault(tag, set()).add(gap.layer)
    scoring = importlib.import_module("agent_gap_radar.scoring")
    minimum = scoring.TAG_COVERAGE_MIN_RECORDS
    expected = [[tag, str(count), ", ".join(sorted(layers[tag]))]
                for tag, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                if count >= minimum]
    assert main(["report", str(root)]) == 0
    section = _section(capsys.readouterr().out, TAG_COVERAGE)
    assert _data_rows(section) == expected
    distinct, listed, cross, omitted = _census_numbers(section)
    assert distinct == len(counts)
    assert listed == len(expected)
    assert cross == len([row for row in expected if ", " in row[2]])
    assert omitted == len(counts) - len(expected)


# --- behavior 11 (cont.): every --json payload, not only `list --json` -----------------

#: The three verbs that accept `--json`, read off `radar <verb> --help` in this round.
_TAG_KEYS = ("tag_coverage", "distinct_tags", "tagcoverage", "Tag coverage", "tags")


def test_b11_diff_json_carries_no_tag_key(tmp_path, capsys):
    before = _register(tmp_path / "before", [_rec("GAP-001", L0, ["alpha"])])
    after = _register(tmp_path / "after", [_rec("GAP-001", L0, ["alpha", "beta"]),
                                          _rec("GAP-002", L1, ["alpha"])])
    assert main(["diff", "--json", str(before), str(after)]) == 0
    blob = json.dumps(json.loads(capsys.readouterr().out))
    for token in _TAG_KEYS:
        assert token not in blob, token


def test_b11_scan_json_carries_no_tag_key(tmp_path, capsys):
    root = _register(tmp_path / "reg", [_rec("GAP-001", L0, ["alpha"]),
                                        _rec("GAP-002", L1, ["alpha"])])
    target = tmp_path / "target"
    (target / "src").mkdir(parents=True)
    (target / "src" / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    assert main(["scan", "--json", "--gaps", str(root / "gaps"), str(target)]) == 0
    out = capsys.readouterr().out
    blob = json.dumps(json.loads(out))
    for token in _TAG_KEYS:
        assert token not in blob, token
    assert TAG_COVERAGE not in out
    assert CENSUS_PREFIX not in out
