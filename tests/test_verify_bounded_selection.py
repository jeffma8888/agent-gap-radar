"""A bounded verification pass must not be able to starve a whole layer.

The bound itself is necessary: verifying a quote costs a network fetch, so a pass
over a large backlog has to stop somewhere. The bug was in HOW it stopped. It took
`sorted(paths)[:limit]`, which is alphabetical by filename, and candidate filenames
begin with the research topic -- so the cut was not a sample, it was a permanent
filter. Whatever sorts late is never verified, never promoted, and absent from the
register no matter how much research covers it.

Measured while it was live: 861 queued candidates spanning all 11 layers
(observability 136, multi-agent 95, tool-action 92, human-interface 86 ...) had
produced a verified queue of 99 containing exactly THREE (benchmarkgap, context,
cost). Eight layers were unreachable rather than under-researched, and the register
they fed was 65% one layer.

These tests are offline. `select_bounded` reads candidate files but never the
network; the one test that drives `partition` monkeypatches `fetch`.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import verify_quotes as vq  # noqa: E402


def _write(inbox: pathlib.Path, name: str, layer: str | None,
           source_class: str = "vendor-primary") -> pathlib.Path:
    doc: dict = {"id": "GAP-900", "title": name, "evidence": [
        {"locator": "https://good.example/a", "quote": "the sky is blue",
         "source_class": source_class, "title": "t", "date": "2026-01-01"}]}
    if layer is not None:
        doc["layer"] = layer
    path = inbox / (name + ".json")
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _inbox(tmp_path: pathlib.Path) -> pathlib.Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox


def _layers(paths: list[pathlib.Path]) -> set[str]:
    out = set()
    for p in paths:
        try:
            out.add(json.loads(p.read_text(encoding="utf-8")).get("layer", ""))
        except Exception:
            out.add("")
    return out


# --------------------------------------------------------------------------
# The regression
# --------------------------------------------------------------------------

def test_a_layer_that_sorts_late_is_still_reached(tmp_path):
    """THE regression: eight layers were starved by an alphabetical cut.

    The control matters as much as the assertion. `limit` is set BELOW the number
    of layer-A records on purpose, so the old slice provably reached zero layer-B
    records -- a test whose control could pass under the old code would prove
    nothing about the fix.
    """
    inbox = _inbox(tmp_path)
    for i in range(20):
        _write(inbox, f"aaa-context-{i:02d}", "context-memory")
    for i in range(3):
        _write(inbox, f"zzz-observability-{i:02d}", "observability")
    paths = sorted(inbox.glob("*.json"))
    limit = 6

    # Control: the discarded implementation, run here so the precondition is
    # asserted rather than assumed.
    old = paths[:limit]
    assert _layers(old) == {"context-memory"}, "control is not in the failing range"

    chosen = vq.select_bounded(paths, limit)

    assert "observability" in _layers(chosen), (
        "a layer sorting after the budget is exhausted must still get a turn")
    assert len(chosen) == limit


def test_a_bounded_partition_pass_reaches_a_late_layer(tmp_path, monkeypatch):
    """End to end: the spread has to survive into what `partition` acts on.

    Observable through the gate: the late-sorting records carry a non-URL locator,
    so a pass that looks at them quarantines them. Under the alphabetical cut the
    quarantine directory stays empty.
    """
    monkeypatch.setattr(vq, "fetch", lambda url: "the sky is blue and more text")
    inbox = _inbox(tmp_path)
    for i in range(20):
        _write(inbox, f"aaa-context-{i:02d}", "context-memory")
    for i in range(3):
        doc = {"id": "GAP-901", "title": f"z{i}", "layer": "observability",
               "evidence": [{"locator": "a blog post I remember", "quote": "words",
                             "source_class": "vendor-primary", "title": "t",
                             "date": "2026-01-01"}]}
        (inbox / f"zzz-observability-{i:02d}.json").write_text(
            json.dumps(doc), encoding="utf-8")
    quarantine, deferred = tmp_path / "q", tmp_path / "d"

    rc = vq.partition(inbox, quarantine, deferred, max_records=6)

    assert rc == 0
    seen = sorted(p.name for p in quarantine.glob("zzz-*.json"))
    assert seen, "the bounded pass never looked at the late-sorting layer"


# --------------------------------------------------------------------------
# The unbounded path must be untouched
# --------------------------------------------------------------------------

@pytest.mark.parametrize("limit", [0, -1])
def test_no_limit_returns_the_input_unchanged(tmp_path, limit):
    inbox = _inbox(tmp_path)
    for i in range(4):
        _write(inbox, f"c{i}", "context-memory")
    paths = sorted(inbox.glob("*.json"))
    assert vq.select_bounded(paths, limit) == paths


def test_a_limit_at_or_above_the_population_returns_the_input_unchanged(tmp_path):
    inbox = _inbox(tmp_path)
    for i in range(4):
        _write(inbox, f"c{i}", "context-memory")
    paths = sorted(inbox.glob("*.json"))
    assert vq.select_bounded(paths, 4) == paths
    assert vq.select_bounded(paths, 99) == paths


# --------------------------------------------------------------------------
# Fairness properties
# --------------------------------------------------------------------------

def test_a_thin_layer_contributes_all_of_itself_and_blocks_nobody(tmp_path):
    """A layer with one candidate gives that one and drops out of the rotation.

    Without this, a fair-share divisor would reserve capacity a thin layer cannot
    use and the pass would return fewer records than its budget allows.
    """
    inbox = _inbox(tmp_path)
    for i in range(10):
        _write(inbox, f"aaa-{i:02d}", "context-memory")
    thin = _write(inbox, "mmm-only-one", "model-runtime")
    paths = sorted(inbox.glob("*.json"))

    chosen = vq.select_bounded(paths, 5)

    assert thin in chosen, "the single record of a thin layer must be taken"
    assert len(chosen) == 5, "the unusable share must fall through to other layers"


def test_exactly_the_budget_is_returned(tmp_path):
    inbox = _inbox(tmp_path)
    for i in range(7):
        _write(inbox, f"a{i}", "context-memory")
    for i in range(7):
        _write(inbox, f"b{i}", "tool-action")
    paths = sorted(inbox.glob("*.json"))
    for limit in (1, 2, 3, 5, 8, 13):
        assert len(vq.select_bounded(paths, limit)) == limit, limit


def test_the_spread_is_even_when_every_layer_is_deep_enough(tmp_path):
    inbox = _inbox(tmp_path)
    for layer in ("context-memory", "observability", "tool-action"):
        for i in range(5):
            _write(inbox, f"{layer}-{i}", layer)
    paths = sorted(inbox.glob("*.json"))

    chosen = vq.select_bounded(paths, 6)

    counts: dict[str, int] = {}
    for p in chosen:
        layer = json.loads(p.read_text(encoding="utf-8"))["layer"]
        counts[layer] = counts.get(layer, 0) + 1
    assert counts == {"context-memory": 2, "observability": 2, "tool-action": 2}, counts


# --------------------------------------------------------------------------
# Malformed records must stay reachable
# --------------------------------------------------------------------------

def test_a_record_with_no_layer_is_still_selectable(tmp_path):
    """It has to reach the gate that judges it, not be filtered out before it."""
    inbox = _inbox(tmp_path)
    for i in range(10):
        _write(inbox, f"aaa-{i:02d}", "context-memory")
    nolayer = _write(inbox, "zzz-no-layer", None)
    paths = sorted(inbox.glob("*.json"))

    assert nolayer in vq.select_bounded(paths, 4)


def test_unreadable_json_is_still_selectable(tmp_path):
    """Selection must not raise on a broken candidate, nor hide it.

    A record that cannot be parsed is exactly the one a human needs to see. If
    selection dropped it, it would sit in the inbox forever and never be
    quarantined.
    """
    inbox = _inbox(tmp_path)
    for i in range(10):
        _write(inbox, f"aaa-{i:02d}", "context-memory")
    broken = inbox / "zzz-broken.json"
    broken.write_text("{not json", encoding="utf-8")
    paths = sorted(inbox.glob("*.json"))

    assert broken in vq.select_bounded(paths, 4)


def test_a_non_string_layer_does_not_crash_selection(tmp_path):
    inbox = _inbox(tmp_path)
    for i in range(6):
        _write(inbox, f"aaa-{i}", "context-memory")
    odd = inbox / "zzz-odd.json"
    odd.write_text(json.dumps({"id": "GAP-902", "layer": 7, "evidence": []}),
                   encoding="utf-8")
    paths = sorted(inbox.glob("*.json"))

    assert odd in vq.select_bounded(paths, 3)


# --------------------------------------------------------------------------
# Ordering inside a layer
# --------------------------------------------------------------------------

def test_stronger_evidence_is_taken_first_inside_a_layer(tmp_path):
    """Given a choice within one layer, verify the better-sourced record first.

    Filename order is the thing being removed, so the strong record is named to
    sort LAST -- otherwise the test would pass under a plain alphabetical cut.
    """
    inbox = _inbox(tmp_path)
    weak = _write(inbox, "aaa-weak", "context-memory", source_class="model-output")
    strong = _write(inbox, "zzz-strong", "context-memory",
                    source_class="incident-postmortem")
    paths = sorted(inbox.glob("*.json"))
    assert paths[0] == weak, "control: the weak record sorts first by filename"

    assert vq.select_bounded(paths, 1) == [strong]


def test_evidence_rank_reads_the_strongest_class_present():
    doc = {"evidence": [{"source_class": "model-output"},
                        {"source_class": "peer-reviewed"},
                        {"source_class": "secondary-summary"}]}
    assert vq._evidence_rank(doc) == 4


def test_evidence_rank_survives_a_malformed_record():
    """It runs on candidates the schema has not seen yet, so it must not raise."""
    assert vq._evidence_rank({}) == 0
    assert vq._evidence_rank({"evidence": "not a list"}) == 0
    assert vq._evidence_rank({"evidence": [None, 3, "x"]}) == 0
    assert vq._evidence_rank({"evidence": [{"source_class": "invented"}]}) == 0


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def test_selection_is_deterministic_and_returned_sorted(tmp_path):
    """Two identical inboxes must produce identical passes, byte for byte."""
    inbox = _inbox(tmp_path)
    for layer in ("context-memory", "observability", "tool-action"):
        for i in range(4):
            _write(inbox, f"{layer}-{i}", layer)
    paths = sorted(inbox.glob("*.json"))

    first = vq.select_bounded(paths, 7)
    second = vq.select_bounded(list(reversed(paths)), 7)

    assert first == second, "input order must not change the selection"
    assert first == sorted(first), "output is sorted so a pass is reproducible"
