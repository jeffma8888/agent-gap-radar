"""Unit: `partition_by_baseline` is a partition of the NEW set, and the line is built from it.

Not a behavior file. The `radar scan --exit-code --baseline` line is pinned end-to-end by
the test engineer (iterations 300 and 305) over real `scan --json` baselines; what is pinned
here is the internal algebra an engineer's refactor can break silently:

* The two halves `render_baseline_line` prints are ONE partition of the ids the exit code
  was decided from -- disjoint, order-preserving, and jointly equal to `new_ids` -- so the
  document can never name an id in both clauses, in neither, or in a different order than
  the `new above-floor PRESENT` list it follows.
* The partition reads `Baseline.scanned`, never `Baseline.present`: an id the baseline held
  at ABSENT is SCANNED (the target moved), and only an id with no finding at all is
  UNSCANNED (the register grew, or the baseline was narrowed).
* `load_baseline` fills `scanned` with EVERY finding's id at ANY verdict, so `present` is
  always a subset of it.

Offline; every input is built in memory or under `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.scan import (Baseline, load_baseline, partition_by_baseline,
                                  render_baseline_line)


@pytest.mark.parametrize("new_ids, scanned, expected", [
    ((), frozenset(), ((), ())),
    (("G-1",), frozenset({"G-1"}), (("G-1",), ())),
    (("G-1",), frozenset(), ((), ("G-1",))),
    (("G-1", "G-2", "G-3"), frozenset({"G-2"}), (("G-2",), ("G-1", "G-3"))),
    # An id the baseline scanned but that is NOT new is nobody's business here.
    (("G-2",), frozenset({"G-1", "G-2", "G-9"}), (("G-2",), ())),
])
def test_partition_is_disjoint_order_preserving_and_covers_new_ids(new_ids, scanned, expected):
    scanned_new, unscanned_new = partition_by_baseline(new_ids, scanned)
    assert (scanned_new, unscanned_new) == expected
    assert not set(scanned_new) & set(unscanned_new)
    assert tuple(sorted(scanned_new + unscanned_new)) == tuple(sorted(new_ids))


def test_partition_reads_scanned_not_present():
    """A finding at ABSENT is a scan the baseline made; the id is SCANNED, not carried."""
    baseline = Baseline(spelling="b.json", target_name="t",
                        present=frozenset({"G-1"}), scanned=frozenset({"G-1", "G-2"}))
    assert partition_by_baseline(("G-2", "G-3"), baseline.scanned) == (("G-2",), ("G-3",))


def test_line_is_the_iteration_300_prefix_plus_the_two_partition_clauses():
    baseline = Baseline(spelling="typed/b.json", target_name="t",
                        present=frozenset({"G-1", "G-7"}), scanned=frozenset({"G-1", "G-2", "G-7"}))
    line = render_baseline_line(baseline, ("G-2", "G-3"))
    prefix = "Baseline: typed/b.json -- carried PRESENT: 2; new above-floor PRESENT: 2 (G-2, G-3)"
    assert line.startswith(prefix)
    assert line[len(prefix):] == ("; scanned by the baseline: 1 (G-2); "
                                  "unscanned by the baseline: 1 (G-3)")
    assert "\n" not in line


def test_empty_lists_spell_none_in_all_three_clauses():
    baseline = Baseline(spelling="b", target_name="t", present=frozenset(), scanned=frozenset())
    assert render_baseline_line(baseline, ()) == (
        "Baseline: b -- carried PRESENT: 0; new above-floor PRESENT: 0 (none); "
        "scanned by the baseline: 0 (none); unscanned by the baseline: 0 (none)")


def test_load_baseline_fills_scanned_from_every_finding_at_any_verdict(tmp_path: pathlib.Path):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"target_name": "t", "findings": [
        {"gap_id": "G-1", "verdict": "PRESENT"},
        {"gap_id": "G-2", "verdict": "ABSENT"},
        {"gap_id": "G-3", "verdict": "NOT_APPLICABLE"},
        {"gap_id": "G-4", "verdict": "MANUAL"},
        {"gap_id": "G-5", "verdict": "UNKNOWN"},
    ]}), encoding="utf-8")
    baseline = load_baseline(str(path))
    assert baseline.present == frozenset({"G-1"})
    assert baseline.scanned == frozenset({"G-1", "G-2", "G-3", "G-4", "G-5"})
    assert baseline.present <= baseline.scanned
