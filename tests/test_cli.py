"""CLI contract: documents on stdout, 'Error: ' + exit 2 on failure."""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main

#: The real published register. The scan tests run against it on purpose:
#: a synthetic register would not prove the shipped checks behave.
REGISTER = pathlib.Path(__file__).resolve().parent.parent / "gaps"

RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


@pytest.fixture()
def repo(tmp_path):
    d = tmp_path / "gaps"
    d.mkdir()
    (d / "GAP-001.json").write_text(json.dumps(RECORD), encoding="utf-8")
    return tmp_path


def test_no_command_prints_help_and_exits_zero(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_validate_ok(repo, capsys):
    assert main(["validate", str(repo)]) == 0
    assert "1 gap record(s) valid" in capsys.readouterr().out


def test_path_accepts_repo_root_or_gaps_dir(repo, capsys):
    assert main(["validate", str(repo)]) == 0
    root_out = capsys.readouterr().out
    assert main(["validate", str(repo / "gaps")]) == 0
    assert capsys.readouterr().out == root_out


def test_validate_reports_error_and_exits_2(tmp_path, capsys):
    d = tmp_path / "gaps"
    d.mkdir()
    (d / "bad.json").write_text("{nope", encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: ")
    assert captured.out == ""


def test_list_one_line_per_gap(repo, capsys):
    assert main(["list", str(repo)]) == 0
    lines = capsys.readouterr().out.strip().split("\n")
    assert len(lines) == 1
    assert lines[0].startswith("GAP-001")
    assert "p=" in lines[0] and "c=" in lines[0]


def test_report_renders_markdown(repo, capsys):
    assert main(["report", str(repo)]) == 0
    assert capsys.readouterr().out.startswith("# Agent infrastructure gap radar")


def test_show_renders_one_brief(repo, capsys):
    assert main(["show", "GAP-001", str(repo)]) == 0
    assert capsys.readouterr().out.startswith("# GAP-001: A thing is broken")


def test_show_unknown_id_exits_2(repo, capsys):
    assert main(["show", "GAP-404", str(repo)]) == 2
    assert "no such gap" in capsys.readouterr().err


def test_prd_named_gap(repo, capsys):
    assert main(["prd", str(repo), "--gap", "GAP-001"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sourceGap"]["id"] == "GAP-001"


def test_prd_defaults_to_top_ranked_gap(repo, capsys):
    """With no --gap, the highest-priority record above the floor is used."""
    lower = {**RECORD, "id": "GAP-002", "severity": 1,
             "frequency": 1, "tractability": 1}
    (repo / "gaps" / "GAP-002.json").write_text(json.dumps(lower), encoding="utf-8")
    assert main(["prd", str(repo)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sourceGap"]["id"] == "GAP-001"


def test_prd_unknown_gap_exits_2(repo, capsys):
    assert main(["prd", str(repo), "--gap", "GAP-404"]) == 2
    assert "no such gap" in capsys.readouterr().err


def test_prd_project_flag_is_honoured(repo, capsys):
    assert main(["prd", str(repo), "--project", "downstream-repo"]) == 0
    assert json.loads(capsys.readouterr().out)["project"] == "downstream-repo"


def test_prd_exits_2_when_nothing_clears_the_floor(tmp_path, capsys):
    d = tmp_path / "gaps"
    d.mkdir()
    weak = {**RECORD,
            "evidence": [{**RECORD["evidence"][0], "source_class": "model-output"}]}
    (d / "GAP-001.json").write_text(json.dumps(weak), encoding="utf-8")
    assert main(["prd", str(tmp_path)]) == 2
    assert "confidence floor" in capsys.readouterr().err


def test_taxonomy_lists_layers_and_source_classes(capsys):
    assert main(["taxonomy"]) == 0
    out = capsys.readouterr().out
    assert "## Layers" in out
    assert "orchestration" in out
    assert "model-output" in out


def test_floor_flag_changes_the_ranking(repo, capsys):
    assert main(["list", str(repo), "--floor", "6"]) == 0
    assert capsys.readouterr().out.strip() == ""


# --------------------------------------------------------------------------
# `scan --json` is the surface a CI gate or build loop consumes. Prose is not a
# contract: a gate that scrapes markdown breaks on the first reworded heading.
# --------------------------------------------------------------------------

def test_scan_json_is_parseable_and_carries_the_stable_fields(tmp_path, capsys):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "loop.py").write_text(
        "import subprocess\nsubprocess.run(['x'], timeout=600)\n", encoding="utf-8"
    )
    rc = main(["scan", str(tmp_path), "--gaps", str(REGISTER), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target_name"] == tmp_path.name
    assert set(payload["counts"]) == {
        "PRESENT", "ABSENT", "NOT_APPLICABLE", "MANUAL", "UNKNOWN"
    }
    assert payload["findings"], "a scan with no findings tells a consumer nothing"
    row = payload["findings"][0]
    for field in ("gap_id", "verdict", "priority", "confidence", "locations",
                  "layer", "gap_type", "build_hypothesis"):
        assert field in row, field


def test_scan_json_never_blends_priority_and_confidence(tmp_path, capsys):
    """The register's core invariant must survive serialisation."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    main(["scan", str(tmp_path), "--gaps", str(REGISTER), "--json"])
    payload = json.loads(capsys.readouterr().out)
    for row in payload["findings"]:
        assert isinstance(row["priority"], (int, float))
        assert isinstance(row["confidence"], int)
        assert "score" not in row, "a blended score would launder the invariant"


def test_scan_json_is_byte_stable_across_runs(tmp_path, capsys):
    (tmp_path / "a.py").write_text("import subprocess\n", encoding="utf-8")
    main(["scan", str(tmp_path), "--gaps", str(REGISTER), "--json"])
    first = capsys.readouterr().out
    main(["scan", str(tmp_path), "--gaps", str(REGISTER), "--json"])
    assert capsys.readouterr().out == first


def test_scan_json_ends_in_exactly_one_newline(tmp_path, capsys):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    main(["scan", str(tmp_path), "--gaps", str(REGISTER), "--json"])
    out = capsys.readouterr().out
    assert out.endswith("}\n") and not out.endswith("\n\n")
