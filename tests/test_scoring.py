"""Scoring must be deterministic, bounded, and must never blend confidence in."""

from __future__ import annotations

from agent_gap_radar.models import Gap
from agent_gap_radar.scoring import (below_floor, confidence, priority, rank)


def _gap(gid="GAP-001", sev=3, freq=3, tract=3, classes=("first-party-field",)):
    return Gap.model_validate({
        "id": gid, "title": f"t{gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s",
        "why_now": "w", "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "q"} for c in classes],
    })


def test_priority_is_bounded_and_monotonic():
    assert priority(_gap(sev=1, freq=1, tract=1)) == 2.0
    assert priority(_gap(sev=5, freq=5, tract=5)) == 10.0
    assert priority(_gap(sev=4)) > priority(_gap(sev=3))


def test_severity_outweighs_tractability():
    """Weights must be ordered severity > frequency > tractability."""
    high_sev = priority(_gap(sev=5, freq=1, tract=1))
    high_tract = priority(_gap(sev=1, freq=1, tract=5))
    assert high_sev > high_tract


def test_priority_is_stable_across_calls():
    g = _gap(sev=4, freq=2, tract=5)
    assert len({priority(g) for _ in range(50)}) == 1


def test_confidence_ceiling_from_strongest_source():
    assert confidence(_gap(classes=("survey-aggregate",))) == 3
    assert confidence(_gap(classes=("peer-reviewed",))) == 4
    assert confidence(_gap(classes=("first-party-field",))) == 5


def test_corroboration_adds_one_but_caps_at_five():
    single = confidence(_gap(classes=("survey-aggregate",)))
    both = confidence(_gap(classes=("survey-aggregate", "peer-reviewed")))
    assert both == min(5, 4 + 1)
    assert both > single
    assert confidence(_gap(classes=("first-party-field", "peer-reviewed"))) == 5


def test_duplicate_class_is_not_corroboration():
    """Two citations of the same class are one kind of evidence, not two."""
    assert confidence(_gap(classes=("peer-reviewed", "peer-reviewed"))) == 4


def test_model_output_alone_scores_zero_regardless_of_volume():
    assert confidence(_gap(classes=("model-output",) * 9)) == 0


def test_model_output_does_not_count_as_corroboration():
    only_real = confidence(_gap(classes=("peer-reviewed",)))
    with_model = confidence(_gap(classes=("peer-reviewed", "model-output")))
    assert with_model == only_real


def test_rank_orders_by_priority_then_confidence_then_id():
    a = _gap("GAP-001", sev=5, freq=5, tract=5)
    b = _gap("GAP-002", sev=1, freq=1, tract=1)
    c = _gap("GAP-003", sev=5, freq=5, tract=5)
    ordered = [g.id for g, _, _ in rank([b, c, a])]
    assert ordered == ["GAP-001", "GAP-003", "GAP-002"]


def test_confidence_floor_excludes_but_does_not_delete():
    weak = _gap("GAP-050", classes=("model-output",))
    strong = _gap("GAP-051")
    assert [g.id for g, _, _ in rank([weak, strong])] == ["GAP-051"]
    assert [g.id for g, _, _ in below_floor([weak, strong])] == ["GAP-050"]


def test_a_weakly_sourced_big_problem_still_outranks_nothing():
    """Priority must not be silently discounted by confidence (no blending)."""
    weak_big = _gap("GAP-060", sev=5, freq=5, tract=5, classes=("survey-aggregate",))
    strong_small = _gap("GAP-061", sev=1, freq=1, tract=1,
                        classes=("first-party-field", "peer-reviewed"))
    assert priority(weak_big) > priority(strong_small)
    assert [g.id for g, _, _ in rank([strong_small, weak_big])][0] == "GAP-060"
