"""Iteration 08 behaviors: `rank()` and `below_floor()` are one single-pass partition,
so "a below-floor record is DISPLAYED, never silently dropped" -- the one rule
`VISION.md` protects by name -- becomes an asserted invariant instead of a coincidence
between two independently written filters.

Black-box. Nothing here reads the implementation source, the engineer's or reviewer's
notes, or a diff. Every assertion either calls the public library API the spec names
(`scoring.rank`, `scoring.below_floor`, `scoring.priority`, `scoring.confidence`,
`registry.load_all`) or runs `agent_gap_radar.cli.main` and observes only the exit code,
stdout and stderr.

Four habits this file keeps on purpose:

* every register-facing assertion asserts its DOMAIN IS NON-EMPTY first, because a green
  result over zero rows is the failure that looks like health;
* the per-floor split is checked against an INDEPENDENT ORACLE built from the public
  `confidence()` (`kept iff confidence(g) >= floor`), so it survives the register growing,
  while the exact census the spec measured is pinned in its own test that stands down --
  visibly, with a reason -- once the register is no longer the 16 records it was measured
  over. A stale hard-coded 16 would red the suite the day a research pass lands GAP-017;
* the evidence ladder used to construct the two vacuous edges is OBSERVED by parsing
  `radar taxonomy` output rather than imported from the module under test (the reference
  iterations 05 and 07 established);
* the call-count behavior -- the only one of the six that a two-filter implementation
  cannot satisfy -- ARMS its own instrument: it proves the counting wrapper is installed
  and reached before it treats a count as a measurement. Both halves are asserted at every
  floor on purpose, because the pre-change `N + kept` shape already equals N for whichever
  half the floor leaves empty, so a one-sided assertion would pass a two-filter tree at
  four of the eight floors.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

from agent_gap_radar import scoring
from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import below_floor, confidence, priority, rank

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: The spec's floor sweep. 0 and 1 leave `below_floor` empty; 6 and 7 leave `rank` empty.
FLOORS = tuple(range(8))

#: Register size the spec's census was measured over, and that census: floor -> (ranked, below).
MEASURED_SIZE = 16
MEASURED_CENSUS = {0: (16, 0), 1: (16, 0), 2: (15, 1), 3: (15, 1),
                   4: (15, 1), 5: (14, 2), 6: (0, 16), 7: (0, 16)}

REGISTER = load_all(GAPS_DIR)

RANKED_HEADING = "## Ranked gaps"
BELOW_HEADING = "## Below confidence floor"

#: A schema-valid record, cloned per test with only the fields a behavior needs.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 3, "frequency": 3, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


# ---------------------------------------------------------------------------
# the ladder, observed by running the product rather than imported
# ---------------------------------------------------------------------------

def _observed_ladder() -> tuple[tuple[str, int], ...]:
    buffer = io.StringIO()
    import contextlib
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
WEIGHT = dict(LADDER)
#: Strongest rung first in the published order, so index 0 is the top of the ladder.
STRONGEST_CLASS = LADDER[0][0]
ZERO_WEIGHT_CLASS = "model-output"


def _gap(gid: str, *, sev: int = 3, freq: int = 3, tract: int = 3,
         classes: tuple[str, ...] = ("first-party-field",)) -> Gap:
    record = dict(RECORD)
    record["id"] = gid
    record["title"] = f"constructed {gid}"
    record["severity"], record["frequency"], record["tractability"] = sev, freq, tract
    record["evidence"] = [
        {"source_class": klass, "title": f"src-{index}",
         "locator": f"https://example.invalid/{gid.lower()}-{index}",
         "date": "2026-01-02", "quote": "q"}
        for index, klass in enumerate(classes)
    ]
    return Gap.model_validate(record)


def _ids(rows) -> list[str]:
    return [gap.id for gap, _, _ in rows]


def _assert_partition(gaps, floor: int) -> tuple[list, list]:
    """The three assertions the spec names, plus the independent floor oracle."""
    kept, excluded = rank(gaps, floor), below_floor(gaps, floor)
    kept_ids, excluded_ids = _ids(kept), _ids(excluded)
    overlap = set(kept_ids) & set(excluded_ids)
    assert not overlap, f"floor {floor}: id in both results: {sorted(overlap)}"
    assert sorted(kept_ids + excluded_ids) == sorted(g.id for g in gaps), (
        f"floor {floor}: a record is in neither result")
    assert len(kept_ids) + len(excluded_ids) == len(gaps), (
        f"floor {floor}: {len(kept_ids)} + {len(excluded_ids)} != {len(gaps)}")
    assert sorted(kept_ids) == sorted(g.id for g in gaps if confidence(g) >= floor), (
        f"floor {floor}: kept set disagrees with the confidence oracle")
    assert sorted(excluded_ids) == sorted(g.id for g in gaps if confidence(g) < floor), (
        f"floor {floor}: excluded set disagrees with the confidence oracle")
    return kept, excluded


# ---------------------------------------------------------------------------
# behavior 1 -- partition over the committed register, every floor
# ---------------------------------------------------------------------------

def test_b1_the_register_is_a_non_empty_domain_of_unique_ids():
    """Anti-vacuity gate for every register-facing assertion in this file."""
    assert len(REGISTER) >= MEASURED_SIZE, f"register unexpectedly small: {len(REGISTER)}"
    ids = [g.id for g in REGISTER]
    assert len(set(ids)) == len(ids), "duplicate id in the register"
    assert len(LADDER) == 9 and WEIGHT[ZERO_WEIGHT_CLASS] == 0, LADDER


@pytest.mark.parametrize("floor", FLOORS)
def test_b1_rank_and_below_floor_partition_the_register(floor):
    assert REGISTER, "empty register: this assertion would be vacuous"
    _assert_partition(REGISTER, floor)


def test_b1_the_measured_census_is_unchanged():
    """The exact per-floor split the spec measured over the 16-record register.

    Stands down loudly rather than reddening the suite once a research pass has grown
    the register: the durable invariant is the parametrized partition test above, which
    derives its expectation from the register itself.
    """
    if len(REGISTER) != MEASURED_SIZE:
        pytest.skip(f"register is now {len(REGISTER)} records, not the measured "
                    f"{MEASURED_SIZE}; the partition test carries the invariant")
    measured = {floor: (len(rank(REGISTER, floor)), len(below_floor(REGISTER, floor)))
                for floor in FLOORS}
    assert measured == MEASURED_CENSUS
    assert all(sum(pair) == MEASURED_SIZE for pair in measured.values()), measured


# ---------------------------------------------------------------------------
# behavior 2 -- partition over constructed inputs, including both vacuous edges
# ---------------------------------------------------------------------------

def _constructed() -> list[Gap]:
    """Deliberately spans the ladder: a zero-weight record, a top-rung record, a middle."""
    return [
        _gap("GAP-901", classes=(ZERO_WEIGHT_CLASS,)),
        _gap("GAP-902", classes=(STRONGEST_CLASS,)),
        _gap("GAP-903", classes=("secondary-summary",)),
        _gap("GAP-904", classes=("peer-reviewed", "vendor-primary")),
    ]


@pytest.mark.parametrize("floor", FLOORS)
def test_b2_partition_holds_over_constructed_records_at_every_floor(floor):
    gaps = _constructed()
    assert confidence(gaps[0]) == 0, "the zero-weight record must score 0"
    assert confidence(gaps[1]) == max(WEIGHT.values()), "top-rung record must score the ceiling"
    _assert_partition(gaps, floor)


def test_b2_both_vacuous_edges_are_a_partition_not_an_error():
    gaps = _constructed()
    kept, excluded = _assert_partition(gaps, 0)
    assert len(kept) == len(gaps) and excluded == [], "floor 0 must exclude nothing"
    ceiling = max(WEIGHT.values())
    kept, excluded = _assert_partition(gaps, ceiling + 1)
    assert kept == [] and len(excluded) == len(gaps), "an unreachable floor must keep nothing"


@pytest.mark.parametrize("floor", FLOORS)
def test_b2_the_empty_list_partitions_into_nothing(floor):
    assert rank([], floor) == []
    assert below_floor([], floor) == []


# ---------------------------------------------------------------------------
# behavior 3 -- ordering and row shape are unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", FLOORS)
def test_b3_row_shape_is_a_triple_carrying_that_gap_own_scores(floor):
    rows = rank(REGISTER, floor) + below_floor(REGISTER, floor)
    assert rows, f"floor {floor}: no rows to inspect"
    for row in rows:
        assert isinstance(row, tuple) and len(row) == 3, row
        gap, shown_priority, shown_confidence = row
        assert shown_priority == priority(gap), gap.id
        assert shown_confidence == confidence(gap), gap.id


@pytest.mark.parametrize("floor", FLOORS)
def test_b3_rank_orders_by_priority_then_confidence_then_id(floor):
    rows = rank(REGISTER, floor)
    if not rows:
        pytest.skip(f"floor {floor} keeps nothing; ordering is covered at lower floors")
    keys = [(-p, -c, g.id) for g, p, c in rows]
    assert keys == sorted(keys), f"floor {floor}: rank is not in (-priority, -confidence, id) order"


@pytest.mark.parametrize("floor", FLOORS)
def test_b3_below_floor_orders_by_ascending_id(floor):
    rows = below_floor(REGISTER, floor)
    if not rows:
        pytest.skip(f"floor {floor} excludes nothing; ordering is covered at higher floors")
    assert _ids(rows) == sorted(_ids(rows)), f"floor {floor}: below_floor is not id-ordered"


def test_b3_the_tiebreakers_are_exercised_not_merely_assumed():
    """Constructed ties, so the second and third sort keys actually decide something."""
    same_priority_low_conf = _gap("GAP-911", classes=("secondary-summary",))
    same_priority_high_conf = _gap("GAP-912", classes=(STRONGEST_CLASS,))
    tie_on_both_later_id = _gap("GAP-913", classes=(STRONGEST_CLASS,))
    bigger = _gap("GAP-914", sev=5, freq=5, tract=5, classes=("secondary-summary",))
    gaps = [tie_on_both_later_id, same_priority_low_conf, bigger, same_priority_high_conf]
    assert priority(same_priority_low_conf) == priority(same_priority_high_conf)
    assert confidence(same_priority_high_conf) > confidence(same_priority_low_conf)
    assert _ids(rank(gaps, 0)) == ["GAP-914", "GAP-912", "GAP-913", "GAP-911"]
    assert _ids(below_floor(gaps, 99)) == ["GAP-911", "GAP-912", "GAP-913", "GAP-914"]


# ---------------------------------------------------------------------------
# behavior 4 -- one scoring pass per record per call
# ---------------------------------------------------------------------------

def _counting_confidence(monkeypatch) -> list[str]:
    """Install a counting wrapper on the module attribute and PROVE it is reached."""
    seen: list[str] = []
    real = scoring.confidence

    def wrapper(gap):
        seen.append(gap.id)
        return real(gap)

    monkeypatch.setattr(scoring, "confidence", wrapper)
    probe = scoring.confidence(REGISTER[0])
    assert seen == [REGISTER[0].id], "the counting wrapper was not installed"
    assert probe == real(REGISTER[0]), "the wrapper must delegate, not replace"
    seen.clear()
    return seen


@pytest.mark.parametrize("floor", FLOORS)
def test_b4_rank_scores_each_record_exactly_once(monkeypatch, floor):
    seen = _counting_confidence(monkeypatch)
    rank(REGISTER, floor)
    assert len(seen) == len(REGISTER), (
        f"floor {floor}: rank evaluated confidence {len(seen)} times over "
        f"{len(REGISTER)} records")


@pytest.mark.parametrize("floor", FLOORS)
def test_b4_below_floor_scores_each_record_exactly_once(monkeypatch, floor):
    seen = _counting_confidence(monkeypatch)
    below_floor(REGISTER, floor)
    assert len(seen) == len(REGISTER), (
        f"floor {floor}: below_floor evaluated confidence {len(seen)} times over "
        f"{len(REGISTER)} records")


def test_b4_the_count_is_per_call_and_no_cache_reduces_it(monkeypatch):
    seen = _counting_confidence(monkeypatch)
    rank(REGISTER, 2)
    rank(REGISTER, 2)
    assert len(seen) == 2 * len(REGISTER), (
        f"two rank calls evaluated confidence {len(seen)} times; a cross-call cache "
        f"would make the single-pass claim unfalsifiable")


def test_b4_each_record_is_the_one_scored_not_an_arbitrary_repeat(monkeypatch):
    """N calls could also be one record scored N times; pin the identities."""
    seen = _counting_confidence(monkeypatch)
    rank(REGISTER, 2)
    assert sorted(seen) == sorted(g.id for g in REGISTER)


# ---------------------------------------------------------------------------
# behavior 5 -- `radar report` never loses a record, at any floor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", (0, 2, 6))
def test_b5_report_carries_every_register_id_exactly_once(floor, capsys):
    ids = [g.id for g in REGISTER]
    assert len(ids) >= MEASURED_SIZE, f"register unexpectedly small: {len(ids)}"
    assert main(["report", str(REPO_ROOT), "--floor", str(floor)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    document = captured.out
    assert document.endswith("\n") and not document.endswith("\n\n"), repr(document[-4:])
    counts = {gid: len(re.findall(r"\b" + re.escape(gid) + r"\b", document)) for gid in ids}
    wrong = {gid: n for gid, n in counts.items() if n != 1}
    assert not wrong, f"floor {floor}: ids not appearing exactly once: {wrong}"
    assert RANKED_HEADING in document and BELOW_HEADING in document, (
        f"floor {floor}: a section heading is missing")


# ---------------------------------------------------------------------------
# behavior 6 -- `radar list --json` publishes an internally consistent census
# ---------------------------------------------------------------------------

BLENDED_KEY_HINTS = ("score", "blend", "combined", "weighted", "overall")


@pytest.mark.parametrize("floor", (0, 2, 5, 6, 7))
def test_b6_list_json_census_is_internally_consistent(floor, capsys):
    assert len(REGISTER) >= MEASURED_SIZE, f"register unexpectedly small: {len(REGISTER)}"
    assert main(["list", str(REPO_ROOT), "--floor", str(floor), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")
    payload = json.loads(captured.out)
    counts, records = payload["counts"], payload["records"]
    assert counts["total"] == counts["ranked"] + counts["below_floor"], counts
    assert len(records) == counts["total"], (len(records), counts)
    assert counts["ranked"] == len(rank(REGISTER, floor)), counts
    assert counts["below_floor"] == len(below_floor(REGISTER, floor)), counts
    assert sorted(r["gap_id"] for r in records) == sorted(g.id for g in REGISTER), (
        f"floor {floor}: the JSON record set is not the register")


@pytest.mark.parametrize("floor", (0, 2, 5, 6, 7))
def test_b6_list_json_keeps_the_two_axes_unblended(floor, capsys):
    assert main(["list", str(REPO_ROOT), "--floor", str(floor), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    keys = set(payload) | {k for record in payload["records"] for k in record}
    blended = sorted(k for k in keys if any(h in k.lower() for h in BLENDED_KEY_HINTS))
    assert not blended, f"a key looks like a blended score: {blended}"
    for record in payload["records"]:
        assert {"priority", "confidence"} <= set(record), record
        assert isinstance(record["confidence"], int), record
