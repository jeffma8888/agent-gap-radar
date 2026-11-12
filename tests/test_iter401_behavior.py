"""Iteration 401 behaviors: `radar report` publishes IDENTICAL EVIDENCE SETS.

The feature under test: one level-2 section, `## Identical evidence sets`, between
`## Tag coverage` and `## Below confidence floor`, listing every group of 2+ records
whose cited DOCUMENT SETS are exactly equal -- a display that merges, hides and
de-ranks nothing.

Every register here is synthetic and built under `tmp_path` with locators on reserved
`.example` hosts, so a correct register growing tomorrow cannot red this file; the one
exception is behavior 8's census over the committed register, which the spec pins.
Everything is in-process: no scan, no self-scan, no subprocess, no network.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import radar_report
from agent_gap_radar.taxonomy import LAYERS

HEADING = "## Identical evidence sets"
TAG_COVERAGE = "## Tag coverage"
BELOW_FLOOR = "## Below confidence floor"
CENSUS = ("Records whose cited document set exactly matches another record's: "
          "{r} of {n} | groups: {g}")
TABLE_HEADER = "| IDs | Layers | Documents |"
NONE_FOUND = "None found."
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

_LAYERS = list(LAYERS)
L0, L1 = _LAYERS[0], _LAYERS[1]


def _rec(gap_id: str, locators: list[str], layer: str = L0,
         source_class: str = "first-party-field") -> dict:
    """A valid record citing each of `locators` once, all of one `source_class`."""
    return {
        "id": gap_id, "title": f"Record {gap_id}", "layer": layer,
        "gap_type": "missing-contract", "problem": "p", "symptom": "the symptom text",
        "why_now": "w", "severity": 5, "frequency": 4, "tractability": 3,
        "existing": ["partial fix one"], "build_hypothesis": "build a small wrapper",
        "evidence": [{"source_class": source_class, "title": f"S{i}",
                      "locator": loc, "date": "2026-01-02",
                      "quote": "the verbatim line"}
                     for i, loc in enumerate(locators)],
    }


#: Behavior 4's fixture, verbatim from the spec.
FIXTURE = [
    _rec("GAP-001", ["https://a.example/p", "https://b.example/q"]),
    _rec("GAP-002", ["https://A.example/p/", "https://b.example/q#s2"], layer=L1),
    _rec("GAP-003", ["https://a.example/p"]),
    _rec("GAP-004", ["https://c.example/r"]),
]


def _register(root: pathlib.Path, records: list[dict]) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for record in records:
        (d / f"{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def _section(out: str) -> list[str]:
    """The section's lines, heading included, up to (excluding) the next `## `."""
    body = out.split(HEADING + "\n", 1)[1].split("\n## ", 1)[0]
    return [HEADING] + body.split("\n")


def _cli(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_b1_heading_once_between_tag_coverage_and_below_floor(tmp_path):
    out = radar_report(load_all(_register(tmp_path, FIXTURE) / "gaps"))
    assert out.count(HEADING + "\n") == 1
    lines = out.split("\n")
    assert lines.index(TAG_COVERAGE) < lines.index(HEADING) < lines.index(BELOW_FLOOR)


def test_b1_section_is_framed_by_its_neighbours(tmp_path):
    out = radar_report(load_all(_register(tmp_path, FIXTURE) / "gaps"))
    before, rest = out.split(HEADING + "\n", 1)
    after = BELOW_FLOOR + rest.split("\n" + BELOW_FLOOR, 1)[1]
    assert before.endswith("\n\n") and TAG_COVERAGE in before
    assert after.startswith(BELOW_FLOOR + "\n")


def test_b2_b3_b4_fixture_census_and_single_row(tmp_path):
    section = _section(radar_report(load_all(_register(tmp_path, FIXTURE) / "gaps")))
    assert section[1] == ""
    assert section[2] == CENSUS.format(r=2, n=4, g=1)
    assert section[3] == "" and section[5] == ""
    assert section[6] == TABLE_HEADER
    assert section[7] == "| --- | --- | --- |"
    assert section[8] == f"| GAP-001, GAP-002 | {L0}, {L1} | 2 |"
    assert section[9:] == [""]
    assert "GAP-003" not in "\n".join(section) and "GAP-004" not in "\n".join(section)


def test_b3_rows_sorted_by_first_id_uncapped_layers_in_taxonomy_order(tmp_path):
    records = [_rec("GAP-009", ["https://z.example/1"], layer=L1),
               _rec("GAP-002", ["https://z.example/1"], layer=L0),
               _rec("GAP-005", ["https://y.example/1", "https://y.example/2"]),
               _rec("GAP-001", ["https://y.example/2", "https://Y.example/1/"]),
               _rec("GAP-003", ["https://y.example/2#x", "https://y.example/1"])]
    section = _section(radar_report(load_all(_register(tmp_path, records) / "gaps")))
    assert section[2] == CENSUS.format(r=5, n=5, g=2)
    assert section[8:10] == [f"| GAP-001, GAP-003, GAP-005 | {L0} | 2 |",
                             f"| GAP-002, GAP-009 | {L0}, {L1} | 1 |"]


def test_b5_no_group_and_empty_register(tmp_path):
    distinct = [_rec("GAP-001", ["https://a.example/p"]),
                _rec("GAP-002", ["https://b.example/p"])]
    section = _section(radar_report(load_all(_register(tmp_path, distinct) / "gaps")))
    assert section[2] == CENSUS.format(r=0, n=2, g=0)
    assert section[6] == NONE_FOUND and TABLE_HEADER not in section
    empty = _section(radar_report([]))
    assert empty == [HEADING, "", NONE_FOUND, ""]


def test_b6_purpose_line_states_display_only(tmp_path):
    purpose = _section(radar_report(load_all(_register(tmp_path, FIXTURE) / "gaps")))[4]
    assert "may be one gap filed twice" in purpose
    assert ("no count in this section reaches priority, confidence, the ranking "
            "or the floor") in purpose
    assert "Nothing is merged or hidden" in purpose


def test_b7_grouping_moves_no_score(tmp_path, capsys):
    together = _register(tmp_path / "all", FIXTURE)
    _, out, _ = _cli(["list", str(together), "--json"], capsys)
    grouped = {r["gap_id"]: r for r in json.loads(out)["records"]}
    for record in FIXTURE[:2]:
        alone = _register(tmp_path / record["id"], [record])
        _, solo, _ = _cli(["list", str(alone), "--json"], capsys)
        (row,) = json.loads(solo)["records"]
        for key in ("confidence", "priority", "below_floor"):
            assert grouped[record["id"]][key] == row[key]


def test_b7_a_below_floor_group_member_stays_below_floor(tmp_path):
    weak = [_rec("GAP-001", ["https://a.example/p"], source_class="secondary-summary"),
            _rec("GAP-002", ["https://A.example/p/"], source_class="secondary-summary")]
    out = radar_report(load_all(_register(tmp_path, weak) / "gaps"))
    ranked, below = out.split(BELOW_FLOOR, 1)
    assert "| GAP-001 |" not in ranked.split(HEADING, 1)[0]
    assert "| GAP-001 |" in below and "| GAP-002 |" in below
    assert "| GAP-001, GAP-002 |" in "\n".join(_section(out))


def test_b8_committed_register_census_is_deterministic(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    first = _cli(["report", "."], capsys)
    second = _cli(["report", "."], capsys)
    assert first == second
    code, out, err = first
    assert code == 0 and err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert _section(out)[2] == CENSUS.format(r=17, n=120, g=8)


@pytest.mark.parametrize("flag", [["--layer", L1], ["--match", "Record GAP-00"]])
def test_scope_follows_the_report_narrowing(tmp_path, capsys, flag):
    root = _register(tmp_path, FIXTURE)
    code, out, err = _cli(["report", str(root), *flag], capsys)
    assert code == 0 and err == ""
    expected = (1, 0) if flag[0] == "--layer" else (4, 1)
    n, g = expected
    assert _section(out)[2] == CENSUS.format(r=2 * g, n=n, g=g)
