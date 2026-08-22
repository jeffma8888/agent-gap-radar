"""Registry loading, renderers, and the PRD bridge.

These tests build their own fixtures in tmp_path rather than asserting on the
repository's own gaps/ directory: a test that only passes on one checkout of
one machine is not a test.
"""

from __future__ import annotations

import json

import pytest

from agent_gap_radar.prd import prd_for, render_prd
from agent_gap_radar.registry import RegistryError, load_all, load_one
from agent_gap_radar.render import gap_brief, radar_report
from agent_gap_radar.models import Gap

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


def _write(d, record, name=None):
    d.mkdir(parents=True, exist_ok=True)
    p = d / (name or f"{record['id']}.json")
    p.write_text(json.dumps(record), encoding="utf-8")
    return p


def test_load_all_reads_and_validates(tmp_path):
    _write(tmp_path, RECORD)
    gaps = load_all(tmp_path)
    assert [g.id for g in gaps] == ["GAP-001"]


def test_load_all_is_deterministic_by_filename(tmp_path):
    for i in (3, 1, 2):
        _write(tmp_path, {**RECORD, "id": f"GAP-00{i}"})
    assert [g.id for g in load_all(tmp_path)] == ["GAP-001", "GAP-002", "GAP-003"]


def test_missing_directory_raises(tmp_path):
    with pytest.raises(RegistryError):
        load_all(tmp_path / "nope")


def test_invalid_json_is_reported_not_skipped(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError, match="broken.json"):
        load_all(tmp_path)


def test_schema_violation_is_reported(tmp_path):
    _write(tmp_path, {**RECORD, "layer": "invented-layer"})
    with pytest.raises(RegistryError, match="GAP-001"):
        load_all(tmp_path)


def test_duplicate_ids_are_rejected(tmp_path):
    _write(tmp_path, RECORD, name="a.json")
    _write(tmp_path, RECORD, name="b.json")
    with pytest.raises(RegistryError, match="duplicate"):
        load_all(tmp_path)


def test_load_one_finds_and_misses(tmp_path):
    _write(tmp_path, RECORD)
    assert load_one(tmp_path, "GAP-001").title == "A thing is broken"
    with pytest.raises(RegistryError, match="no such gap"):
        load_one(tmp_path, "GAP-999")


# --- renderers -------------------------------------------------------------

def test_report_has_single_trailing_newline_and_key_sections(tmp_path):
    _write(tmp_path, RECORD)
    out = radar_report(load_all(tmp_path))
    assert out.endswith("\n") and not out.endswith("\n\n")
    for heading in ("# Agent infrastructure gap radar", "## Ranked gaps",
                    "## By layer", "## Below confidence floor"):
        assert heading in out
    assert "GAP-001" in out


def test_report_shows_below_floor_records_rather_than_hiding_them(tmp_path):
    _write(tmp_path, RECORD)
    weak = {**RECORD, "id": "GAP-002",
            "evidence": [{**RECORD["evidence"][0], "source_class": "model-output"}]}
    _write(tmp_path, weak)
    out = radar_report(load_all(tmp_path))
    below = out.split("## Below confidence floor", 1)[1]
    assert "GAP-002" in below
    ranked = out.split("## Ranked gaps", 1)[1].split("## By layer", 1)[0]
    assert "GAP-002" not in ranked


def test_report_layer_table_lists_every_layer_including_empty_ones(tmp_path):
    """Reversed in iteration 17: this test previously asserted the OPPOSITE
    (`"cost-governance" not in layer_block`), pinning an omission filter as intent.
    A hidden layer makes "clean" and "unexamined" identical bytes, which is the
    silent-drop shape VISION.md names as the one rule the register protects. One
    test owns this contract, so the old name and assertion are gone rather than
    left beside a contradicting new test.
    """
    _write(tmp_path, RECORD)
    out = radar_report(load_all(tmp_path))
    layer_block = out.split("## By layer", 1)[1].split("## Below", 1)[0]
    assert "| orchestration | 1 |" in layer_block
    assert "| cost-governance | 0 |" in layer_block


def test_gap_brief_includes_evidence_quote_and_locator():
    gap = Gap.model_validate(RECORD)
    out = gap_brief(gap)
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert "> the verbatim line" in out
    assert "https://example.invalid/inc1" in out
    assert "## Build hypothesis" in out


def test_gap_brief_omits_build_hypothesis_when_absent():
    gap = Gap.model_validate({**RECORD, "build_hypothesis": ""})
    assert "## Build hypothesis" not in gap_brief(gap)


# --- the research-to-build bridge -----------------------------------------

def test_prd_is_valid_ralph_shape():
    doc = prd_for(Gap.model_validate(RECORD))
    assert set(doc) >= {"project", "branchName", "description", "stories"}
    assert doc["branchName"].startswith("ralph/")
    ids = [s["id"] for s in doc["stories"]]
    assert ids == ["US-001", "US-002", "US-003"]
    assert [s["priority"] for s in doc["stories"]] == [1, 2, 3]
    assert all(s["passes"] is False for s in doc["stories"])


def test_prd_first_story_is_a_failing_reproduction():
    """A loop that starts from a spec optimises the spec; start from a red test."""
    doc = prd_for(Gap.model_validate(RECORD))
    first = doc["stories"][0]
    assert "FAILS" in " ".join(first["acceptanceCriteria"])
    assert RECORD["symptom"] in " ".join(first["acceptanceCriteria"])


def test_prd_carries_evidence_provenance_forward():
    """The build loop must be able to see why it is building this."""
    doc = prd_for(Gap.model_validate(RECORD))
    assert doc["sourceGap"]["id"] == "GAP-001"
    assert doc["sourceGap"]["evidence"][0]["locator"].startswith("https://")


def test_prd_every_story_has_verifiable_criteria():
    doc = prd_for(Gap.model_validate(RECORD))
    for story in doc["stories"]:
        assert story["acceptanceCriteria"], story["id"]
        assert any("test" in c.lower() or "passes" in c.lower()
                   for c in story["acceptanceCriteria"]), story["id"]


def test_render_prd_is_parseable_json_with_trailing_newline():
    out = render_prd(Gap.model_validate(RECORD))
    assert out.endswith("\n")
    assert json.loads(out)["sourceGap"]["id"] == "GAP-001"


def test_branch_slug_is_safe_and_bounded():
    long_title = "A " + ("very " * 40) + "long title with / slashes and #hashes"
    doc = prd_for(Gap.model_validate({**RECORD, "title": long_title}))
    slug = doc["branchName"].removeprefix("ralph/")
    assert len(slug) <= 48
    assert all(c.isalnum() or c == "-" for c in slug)
    assert "--" not in slug
