"""Iteration 89 behaviors: `radar report` publishes SOURCE CONCENTRATION.

The feature under test: one additional level-2 section, `## Source concentration`,
publishing which sources several records rest on and which records rest on exactly ONE
distinct source -- a DISPLAY that derives no penalty, drops no record, and caps no table.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, `tools/*.py` text, the
engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. The oracles are

* the spec's own verbatim lines, quoted once each as a module constant, and
* the document bytes `render.radar_report` and `cli.main(["report", ...])` write, sliced by
  a section splitter written here from the spec's words.

WHY EVERY REGISTER HERE IS SYNTHETIC
The repository's own `gaps/` register is grown by an unattended research pass, so an
assertion keyed on a live id, a live count or a live locator would go red against a CORRECT
register days from now. Every register in this module is built under pytest's `tmp_path` and
every locator is under the reserved `example.test` domain, so no live locator is restated
and nothing here reaches the network.

STRUCTURAL NOTES, so this file cannot lie later:

* **Every published count is proved DERIVED, not literal.** Behavior 2 renders two registers
  whose source graphs differ and asserts all four census numbers move with the data.
* **The keying is proved to be the scorer's own, two-sided.** Behavior 4 renders a fragment,
  a trailing slash and a host-case difference of ONE source and requires a SINGLE row; a
  companion asserts that two genuinely different paths do NOT collapse, so a normalisation
  that lowercases everything into one bucket cannot pass.
* **The sole-source list is proved to count DISTINCT sources, not citations.** A record with
  two citations to the same locator must appear in it, and a record with two citations to
  two locators must not.
* **Behavior 8 asserts its own premise.** The two documents it compares must differ SOMEWHERE
  (inside `## Source concentration`) before their other sections being byte-identical is
  evidence of anything.
* **Behavior 8 does not restate iteration 17's pins.** It imports that module's committed
  literals and re-measures them, so this file cannot silently re-baseline the very pin whose
  job is to catch unrelated movement.
* **No exact heading-SET or heading-COUNT for `radar report` is asserted anywhere here** --
  the spec forbids it, because that shape makes every future section a false failure.
* **No absolute machine path and no personal or employer identifier appears here.**
"""

from __future__ import annotations

import json
import pathlib

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report

RANKED = "## Ranked gaps"
BY_LAYER = "## By layer"
EVIDENCE_AGE = "## Evidence age"
CONCENTRATION = "## Source concentration"
BELOW_FLOOR = "## Below confidence floor"

#: Behavior 2 quotes this line verbatim except for the four counts. Kept as ONE template so
#: the test cannot drift from the spec by a separator or a preposition.
CENSUS_TEMPLATE = (
    "Sources cited by more than one record: {a} of {b} | "
    "records resting on a shared source: {c} of {d}"
)

#: Behavior 3 fixes the table header.
TABLE_HEADER = "| Source | Records | IDs |"

#: Behaviors 6 and 7 reuse the convention `## Ranked gaps` already uses for an empty body.
NONE_FOUND = "None found."

#: Behavior 5 quotes this prefix verbatim; the ids follow it.
SOLE_PREFIX = (
    "Records resting on exactly one distinct source (a single retraction voids the whole "
    "evidentiary basis of each): "
)
SOLE_NONE = SOLE_PREFIX + "none."

#: Every locator in this module is built from this base, so no live locator is restated.
BASE = "https://example.test"

RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "the symptom text",
    "why_now": "w", "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"],
    "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": f"{BASE}/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _citation(locator: str, n: int) -> dict:
    return {"source_class": "first-party-field", "title": f"INC-{n}",
            "locator": locator, "date": "2026-01-02",
            "quote": f"the verbatim line {n}"}


def _rec(gap_id: str, *locators: str, title: str | None = None) -> dict:
    """A valid record citing exactly the locators given, in the order given."""
    return {**RECORD, "id": gap_id,
            "title": title if title is not None else f"Record {gap_id}",
            "evidence": [_citation(loc, i) for i, loc in enumerate(locators, start=1)]}


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


def _census(section: str) -> str:
    return _body_lines(section)[0]


def _sole_line(section: str) -> str:
    return _body_lines(section)[-1]


# --- behavior 1: the section exists once, in one fixed position -------------

def test_b1_report_publishes_a_source_concentration_section(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", f"{BASE}/a")]))
    assert CONCENTRATION in out


def test_b1_the_heading_is_a_whole_line_and_occurs_exactly_once(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", f"{BASE}/a"),
                                       _rec("GAP-002", f"{BASE}/a")]))
    assert [line for line in out.split("\n") if line == CONCENTRATION] == [CONCENTRATION]
    assert out.count(CONCENTRATION) == 1


def test_b1_it_sits_after_evidence_age_and_before_the_below_floor_section(tmp_path):
    out = _render(_register(tmp_path, [_rec("GAP-001", f"{BASE}/a"),
                                       _rec("GAP-002", f"{BASE}/a")]))
    order = [out.index(h) for h in (RANKED, BY_LAYER, EVIDENCE_AGE, CONCENTRATION,
                                    BELOW_FLOOR)]
    assert order == sorted(order), out


def test_b1_the_cli_exits_zero_with_empty_stderr_and_the_section_present(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", f"{BASE}/a")])
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"\n{CONCENTRATION}\n" in captured.out


# --- behavior 2: the census line, derived from the register -----------------

def test_b2_census_line_matches_the_specs_own_three_record_example(tmp_path):
    """Records 1 and 2 share one source; record 3 has its own -> `1 of 2 | 2 of 3`."""
    records = [_rec("GAP-001", f"{BASE}/shared"),
               _rec("GAP-002", f"{BASE}/shared"),
               _rec("GAP-003", f"{BASE}/own")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _census(section) == CENSUS_TEMPLATE.format(a=1, b=2, c=2, d=3)


def test_b2_all_four_counts_follow_the_data_not_a_literal(tmp_path):
    """A second, denser source graph must publish four different numbers.

    GAP-001 cites a+b, GAP-002 cites a, GAP-003 cites b+c, GAP-004 cites d.
    distinct keys = 4; shared keys = a, b -> 2; records on a shared key = 001, 002, 003 -> 3.
    """
    records = [_rec("GAP-001", f"{BASE}/a", f"{BASE}/b"),
               _rec("GAP-002", f"{BASE}/a"),
               _rec("GAP-003", f"{BASE}/b", f"{BASE}/c"),
               _rec("GAP-004", f"{BASE}/d")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _census(section) == CENSUS_TEMPLATE.format(a=2, b=4, c=3, d=4)


def test_b2_the_census_is_the_first_non_blank_line_under_the_heading(tmp_path):
    section = _section(_render(_register(tmp_path, [_rec("GAP-001", f"{BASE}/a")])),
                       CONCENTRATION)
    assert _body_lines(section)[0].startswith("Sources cited by more than one record: ")


def test_b2_the_line_is_plural_free_at_a_count_of_one(tmp_path):
    """One record, one source: no count may change the line's grammar."""
    section = _section(_render(_register(tmp_path, [_rec("GAP-001", f"{BASE}/a")])),
                       CONCENTRATION)
    assert _census(section) == CENSUS_TEMPLATE.format(a=0, b=1, c=0, d=1)


# --- behavior 3: the shared-source table, its order and its completeness ---

def test_b3_table_lists_one_row_per_shared_source_by_count_then_key(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a"),
               _rec("GAP-002", f"{BASE}/a", f"{BASE}/b"),
               _rec("GAP-003", f"{BASE}/a", f"{BASE}/c"),
               _rec("GAP-004", f"{BASE}/b", f"{BASE}/c"),
               _rec("GAP-005", f"{BASE}/z")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert TABLE_HEADER in section
    rows = _data_rows(section)
    assert rows == [
        [f"{BASE}/a", "3", "GAP-001, GAP-002, GAP-003"],
        [f"{BASE}/b", "2", "GAP-002, GAP-004"],
        [f"{BASE}/c", "2", "GAP-003, GAP-004"],
    ], rows
    # a source cited by exactly one record is not a row
    assert f"{BASE}/z" not in section


def test_b3_ids_are_ascending_regardless_of_the_order_records_are_written(tmp_path):
    """`GAP-010` is written first; the cell must still read `GAP-002, GAP-010`."""
    records = [_rec("GAP-010", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/a")]
    rows = _data_rows(_section(_render(_register(tmp_path, records)), CONCENTRATION))
    assert rows == [[f"{BASE}/a", "2", "GAP-002, GAP-010"]], rows


def test_b3_every_qualifying_source_is_listed_with_no_cap_and_no_truncation(tmp_path):
    """Twelve shared sources -> twelve rows. Omitting rows is the silent-drop shape."""
    pairs = [(f"{BASE}/s{i:02d}") for i in range(12)]
    records = [_rec(f"GAP-{i:03d}", *pairs) for i in (1, 2)]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    rows = _data_rows(section)
    assert [r[0] for r in rows] == sorted(pairs), rows
    assert all(r[1] == "2" for r in rows), rows
    assert len(rows) == 12
    for word in ("truncat", "... ", "and 1 more", "omitted"):
        assert word not in section.lower(), word


def test_b3_the_table_follows_the_census_and_a_purpose_line(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/a")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    body = _body_lines(section)
    assert body[0].startswith("Sources cited by more than one record: ")
    assert not body[1].startswith("|"), body
    assert body[2] == TABLE_HEADER, body


def test_b3_the_purpose_line_states_a_fact_and_not_a_target(tmp_path):
    """Acceptance criterion: a display deriving no penalty, and a shared source is no fault.

    Asserted as a set of CLAIMS, never as a byte pin: the spec fixes what the purpose line
    must state, not the words it states it in, so pinning a phrase here would re-baseline
    prose the spec left free. The criterion names four things, and each gets its own
    assertion with an OR-set of the honest ways to say it.

    This test was WRONG on its first run and the correction is recorded here, because the
    original form could not be satisfied by any natural phrasing: it demanded the literal
    token `display` AND banned the substring `penalt`, while the criterion it enforces
    requires the line to say the figure derives no PENALTY. A ban list must not forbid the
    vocabulary the requirement compels.
    """
    records = [_rec("GAP-001", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/a")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    body = _body_lines(section)
    purpose = body[1]
    low = purpose.lower()

    # (a) a shared source is not a fault, with the young-field rationale the spec names
    assert "not a fault" in low or "no fault" in low, purpose
    assert "young field" in low or "few primary sources" in low, purpose

    # (b) it derives NO penalty, and says so against the values it must never reach
    assert "penalty" in low or "penalise" in low or "penalize" in low, purpose
    assert any(neg in low for neg in ("nothing", "never", "no penalty", "not")), purpose
    named = [v for v in ("priority", "confidence", "ranking", "rank", "floor") if v in low]
    assert len(named) >= 2, (named, purpose)

    # (c) the actionable case is a record resting on ONE source
    assert "one source" in low or "single source" in low, purpose

    # (d) it reads as a fact, not as a number to drive down
    assert any(phrase in low for phrase in ("to drive down", "not a target",
                                            "no target", "not a goal")), purpose
    for verdict in ("must reduce", "should reduce", "must be reduced", "should be reduced",
                    "too concentrated", "violation", "unacceptable"):
        assert verdict not in low, (verdict, purpose)


# --- behavior 4: keyed through the scorer's own normalisation --------------

def test_b4_a_fragment_a_trailing_slash_and_host_case_are_one_source(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/p#s2"),
               _rec("GAP-002", "https://EXAMPLE.test/p/")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _data_rows(section) == [[f"{BASE}/p", "2", "GAP-001, GAP-002"]], section
    assert _census(section) == CENSUS_TEMPLATE.format(a=1, b=1, c=2, d=2)
    assert "#s2" not in section
    assert "EXAMPLE" not in section


def test_b4_three_spellings_of_one_source_collapse_to_one_row(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/p"),
               _rec("GAP-002", f"{BASE}/p/"),
               _rec("GAP-003", f"{BASE}/p#anchor")]
    rows = _data_rows(_section(_render(_register(tmp_path, records)), CONCENTRATION))
    assert rows == [[f"{BASE}/p", "3", "GAP-001, GAP-002, GAP-003"]], rows


def test_b4_two_genuinely_different_sources_do_not_collapse(tmp_path):
    """The other side of the normalisation: no second, looser definition of `same`."""
    records = [_rec("GAP-001", f"{BASE}/p", f"{BASE}/q"),
               _rec("GAP-002", f"{BASE}/p", f"{BASE}/q")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    rows = _data_rows(section)
    assert rows == [[f"{BASE}/p", "2", "GAP-001, GAP-002"],
                    [f"{BASE}/q", "2", "GAP-001, GAP-002"]], rows
    assert _census(section) == CENSUS_TEMPLATE.format(a=2, b=2, c=2, d=2)


def test_b4_one_source_cited_twice_by_one_record_is_not_a_shared_source(tmp_path):
    """Two citations, one key, one record: nothing is shared with anybody."""
    records = [_rec("GAP-001", f"{BASE}/p", f"{BASE}/p#two")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _census(section) == CENSUS_TEMPLATE.format(a=0, b=1, c=0, d=1)
    assert NONE_FOUND in section
    assert TABLE_HEADER not in section


# --- behavior 5: the sole-source line -------------------------------------

def test_b5_sole_source_line_is_the_sections_last_non_blank_line(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a"),
               _rec("GAP-002", f"{BASE}/a", f"{BASE}/b"),
               _rec("GAP-003", f"{BASE}/a")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _sole_line(section) == SOLE_PREFIX + "GAP-001, GAP-003"


def test_b5_ids_are_ascending_and_comma_space_joined(tmp_path):
    records = [_rec("GAP-010", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/a"),
               _rec("GAP-007", f"{BASE}/a")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _sole_line(section) == SOLE_PREFIX + "GAP-002, GAP-007, GAP-010"


def test_b5_a_record_citing_one_source_twice_rests_on_exactly_one_source(tmp_path):
    """DISTINCT sources decide membership, never the citation count."""
    records = [_rec("GAP-001", f"{BASE}/p", f"{BASE}/p/"),
               _rec("GAP-002", f"{BASE}/q", f"{BASE}/r")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _sole_line(section) == SOLE_PREFIX + "GAP-001"


def test_b5_no_qualifying_record_renders_the_none_form(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a", f"{BASE}/b"),
               _rec("GAP-002", f"{BASE}/b", f"{BASE}/c")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _sole_line(section) == SOLE_NONE


def test_b5_the_line_is_plural_free_at_one_and_at_many(tmp_path):
    one = _section(_render(_register(tmp_path / "one", [_rec("GAP-001", f"{BASE}/a")])),
                   CONCENTRATION)
    many = _section(_render(_register(tmp_path / "many",
                                      [_rec("GAP-001", f"{BASE}/a"),
                                       _rec("GAP-002", f"{BASE}/b")])), CONCENTRATION)
    assert _sole_line(one).startswith(SOLE_PREFIX)
    assert _sole_line(many).startswith(SOLE_PREFIX)


# --- behavior 6: records, but no shared source ----------------------------

def test_b6_no_shared_source_renders_census_purpose_none_found_and_the_sole_line(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/b")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    body = _body_lines(section)
    assert body[0] == CENSUS_TEMPLATE.format(a=0, b=2, c=0, d=2)
    assert body[2] == NONE_FOUND, body
    assert body[3] == SOLE_PREFIX + "GAP-001, GAP-002", body
    assert len(body) == 4, body
    assert TABLE_HEADER not in section
    assert not any(line.startswith("|") for line in section.split("\n"))


def test_b6_the_heading_is_never_followed_by_nothing(tmp_path):
    records = [_rec("GAP-001", f"{BASE}/a"), _rec("GAP-002", f"{BASE}/b")]
    section = _section(_render(_register(tmp_path, records)), CONCENTRATION)
    assert _body_lines(section), section


# --- behavior 7: the empty register --------------------------------------

def test_b7_zero_record_register_prints_the_heading_and_none_found_only(tmp_path, capsys):
    root = _register(tmp_path, [])
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _section(captured.out, CONCENTRATION)
    assert _body_lines(section) == [NONE_FOUND], section
    assert "Sources cited by more than one record" not in section
    assert SOLE_PREFIX not in section
    assert TABLE_HEADER not in section


def test_b7_the_renderer_and_the_cli_agree_on_the_empty_case(tmp_path, capsys):
    root = _register(tmp_path, [])
    assert main(["report", str(root)]) == 0
    from_cli = _section(capsys.readouterr().out, CONCENTRATION)
    assert _section(radar_report([]), CONCENTRATION) == from_cli


# --- behavior 8: a display, nothing more ---------------------------------

def _pair(tmp_path: pathlib.Path) -> tuple[str, str]:
    """Two documents whose ONLY difference is which source each record cites.

    Both records carry exactly one citation of the same class and date in both registers,
    so every per-record score is identical by construction and only the ACROSS-record
    source graph moves.
    """
    shared = _render(_register(tmp_path / "shared",
                               [_rec("GAP-001", f"{BASE}/same"),
                                _rec("GAP-002", f"{BASE}/same")]))
    apart = _render(_register(tmp_path / "apart",
                              [_rec("GAP-001", f"{BASE}/one"),
                               _rec("GAP-002", f"{BASE}/two")]))
    return shared, apart


def test_b8_concentration_moves_no_score_and_drops_no_record(tmp_path):
    shared, apart = _pair(tmp_path)
    # premise: the two documents DO differ, and only inside `## Source concentration`
    assert shared != apart
    assert _section(shared, CONCENTRATION) != _section(apart, CONCENTRATION)

    assert shared.split(RANKED, 1)[0] == apart.split(RANKED, 1)[0]
    for heading in (RANKED, BY_LAYER, EVIDENCE_AGE, BELOW_FLOOR):
        assert _section(shared, heading) == _section(apart, heading), heading
    for gap_id in ("GAP-001", "GAP-002"):
        assert gap_id in _section(shared, RANKED)
        assert gap_id in _section(apart, RANKED)


def test_b8_no_other_verb_publishes_a_concentration(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", f"{BASE}/a"),
                                _rec("GAP-002", f"{BASE}/a")])
    other = _register(tmp_path / "other", [_rec("GAP-001", f"{BASE}/a")])
    argvs = [["list", str(root)], ["list", "--json", str(root)],
             ["show", "GAP-001", str(root)], ["prd", "--gap", "GAP-001", str(root)],
             ["validate", str(root)], ["taxonomy"],
             ["diff", str(other), str(root)]]
    for argv in argvs:
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        assert captured.err == "", argv
        assert "Source concentration" not in captured.out, argv
        assert TABLE_HEADER not in captured.out, argv
        assert "resting on a shared source" not in captured.out, argv
        assert SOLE_PREFIX not in captured.out, argv


def test_b8_list_json_carries_no_concentration_key(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", f"{BASE}/a"),
                                _rec("GAP-002", f"{BASE}/a")])
    assert main(["list", "--json", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    blob = json.dumps(payload)
    for token in ("concentration", "shared_source", "sole_source", "shared"):
        assert token not in blob, token


def test_b8_iteration_17_byte_pins_still_hold_unedited(tmp_path):
    """Imported, not restated: this file must not be able to re-baseline that pin."""
    import test_iter17_behavior as it17

    out = _render(_register(tmp_path, [it17.RECORD, it17._B8_WEAK]))
    before, rest = out.split(BY_LAYER, 1)
    _by_layer, after = rest.split(BELOW_FLOOR, 1)
    assert before == it17._B8_BEFORE
    assert BELOW_FLOOR + after == it17._B8_AFTER
    # the new section lives strictly between `## By layer` and `## Below confidence floor`
    assert CONCENTRATION not in before
    assert CONCENTRATION not in BELOW_FLOOR + after
    assert CONCENTRATION in rest.split(BELOW_FLOOR, 1)[0]


def test_b8_two_renders_are_byte_identical_and_end_in_exactly_one_newline(tmp_path, capsys):
    root = _register(tmp_path, [_rec("GAP-001", f"{BASE}/a"),
                                _rec("GAP-002", f"{BASE}/a", f"{BASE}/b"),
                                _rec("GAP-003", f"{BASE}/b")])
    assert main(["report", str(root)]) == 0
    first = capsys.readouterr().out
    assert main(["report", str(root)]) == 0
    assert capsys.readouterr().out == first == _render(root)
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_b8_the_section_renders_over_the_live_register_without_network(tmp_path, capsys):
    """The shipped register must render too -- keyed on shape only, never on a live id.

    No live count, id or locator is asserted: those move under the research pass. What is
    asserted is that the section is present, structurally complete and internally
    consistent (the census denominators equal the register's own record and source counts
    as the table itself reports them).
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    if not (root / "gaps").is_dir():  # pragma: no cover - the register always ships
        return
    assert main(["report", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _section(captured.out, CONCENTRATION)
    census = _census(section)
    assert census.startswith("Sources cited by more than one record: ")
    assert _sole_line(section).startswith(SOLE_PREFIX)
    head, tail = census.split(" | ", 1)
    shared_count, distinct = (int(x) for x in head.rsplit(": ", 1)[1].split(" of "))
    on_shared, records = (int(x) for x in tail.rsplit(": ", 1)[1].split(" of "))
    rows = _data_rows(section)
    assert len(rows) == shared_count, (len(rows), shared_count)
    assert shared_count <= distinct
    assert on_shared <= records
    assert len({r[0] for r in rows}) == len(rows), "a source key is rendered twice"
    assert all(int(r[1]) > 1 for r in rows), rows
