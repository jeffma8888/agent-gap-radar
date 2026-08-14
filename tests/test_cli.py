"""CLI contract: documents on stdout, 'Error: ' + exit 2 on failure."""

from __future__ import annotations

import json

import pytest

from agent_gap_radar.cli import main

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
