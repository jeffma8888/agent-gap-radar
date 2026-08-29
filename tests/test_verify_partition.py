"""The partition must judge each record on its OWN quotes.

This is the regression test for a ratchet that ran for eleven days. The verifier
used to return one verdict for a whole directory, so a driver reading that exit
code refused to promote ANYTHING whenever ANY quote failed. With a growing pool
and a non-zero per-quote failure rate, that state is permanent: one bad quote
vetoes every good candidate behind it, and fixing individual quotes never clears
it because each fix exposes the next one.

The tool is network-facing, so `fetch` is monkeypatched here. The suite stays
offline by contract.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import verify_quotes as vq  # noqa: E402

PAGES = {
    "https://good.example/a": "the sky is blue and the grass is green",
    "https://good.example/b": "a second page that says something else entirely",
    "https://dead.example/c": None,          # unreachable
    # Long enough that a quote can share a 12-word prefix and still diverge,
    # which is the only way PARTIAL can trigger (PARTIAL_WINDOW = 12 words).
    "https://good.example/long": (
        "the sky is blue and the grass is green and the trees are tall "
        "and the river runs fast past the old stone bridge"
    ),
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every fetch is served from a table. A real request would be a test bug."""
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        if url not in PAGES:
            raise AssertionError(f"test fetched an unexpected url: {url}")
        return PAGES[url]

    monkeypatch.setattr(vq, "fetch", fake_fetch)
    return calls


def _candidate(tmp: pathlib.Path, name: str, evidence: list[tuple[str, str]]):
    doc = {
        "id": "GAP-900",
        "title": name,
        "evidence": [{"locator": u, "quote": q, "source_class": "vendor-primary",
                      "title": "t", "date": "2026-01-01"} for u, q in evidence],
    }
    (tmp / (name + ".json")).write_text(json.dumps(doc), encoding="utf-8")


def _dirs(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox, tmp_path / "quarantine", tmp_path / "deferred"


def test_one_bad_record_does_not_veto_the_good_ones(tmp_path):
    """THE regression: this is the eleven-day outage, as a test."""
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "good1", [("https://good.example/a", "the sky is blue")])
    _candidate(inbox, "bad", [("https://good.example/a", "this text is not on the page")])
    _candidate(inbox, "good2", [("https://good.example/b", "a second page")])

    rc = vq.partition(inbox, q, d)

    assert rc == 0, "partitioning is the tool working, not failing"
    survivors = {p.stem for p in inbox.glob("*.json")}
    assert survivors == {"good1", "good2"}, survivors
    assert (q / "bad.json").exists(), "the offender must be quarantined"
    assert (q / "bad.reason.txt").exists(), "a human needs the reason"
    assert "not found" in (q / "bad.reason.txt").read_text()


def test_unreachable_is_deferred_not_condemned(tmp_path):
    """A rate-limited page is not evidence that a citation is fake."""
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "unreach", [("https://dead.example/c", "anything at all")])
    vq.partition(inbox, q, d)
    assert (d / "unreach.json").exists(), "should be deferred for a later pass"
    assert not (q / "unreach.json").exists(), "must NOT be quarantined"


def test_a_record_is_quarantined_if_any_one_of_its_quotes_fails(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "mixed", [
        ("https://good.example/a", "the sky is blue"),
        ("https://good.example/b", "definitely not present here"),
    ])
    vq.partition(inbox, q, d)
    assert (q / "mixed.json").exists()


def test_not_found_outranks_unreachable(tmp_path):
    """A proven-bad quote must not be excused by an unrelated dead page."""
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "both", [
        ("https://good.example/a", "this text is not on the page"),
        ("https://dead.example/c", "whatever"),
    ])
    vq.partition(inbox, q, d)
    assert (q / "both.json").exists(), "quarantine wins over defer"
    assert not (d / "both.json").exists()


def test_each_unique_page_is_fetched_once(tmp_path, _no_network):
    """The page cache is what makes a large backlog tractable."""
    inbox, q, d = _dirs(tmp_path)
    for i in range(5):
        _candidate(inbox, f"c{i}", [("https://good.example/a", "the sky is blue")])
    vq.partition(inbox, q, d)
    assert _no_network.count("https://good.example/a") == 1, _no_network


def test_max_records_bounds_one_pass(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    for i in range(6):
        _candidate(inbox, f"c{i}", [("https://good.example/a", "the sky is blue")])
    vq.partition(inbox, q, d, max_records=2)
    assert len(list(inbox.glob("*.json"))) == 6, "verified records stay in the inbox"


def test_partial_match_counts_as_verified(tmp_path):
    """A quote with an elided tail is legitimate and must not be quarantined."""
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "elided", [(
        "https://good.example/long",
        "the sky is blue and the grass is green and the trees are tall "
        "and then it was elided by the author",
    )])
    vq.partition(inbox, q, d)
    assert (inbox / "elided.json").exists(), "a shared 12-word prefix should pass"


def test_a_quote_sharing_no_long_run_is_quarantined(tmp_path):
    """The negative control for PARTIAL: a short near-miss must still fail."""
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "nearmiss", [
        ("https://good.example/a", "the sky is blue and the grass is not green"),
    ])
    vq.partition(inbox, q, d)
    assert (q / "nearmiss.json").exists(), "no 12-word shared prefix, so it fails"


def test_unparseable_json_is_quarantined_with_a_reason(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    (inbox / "broken.json").write_text("{not json", encoding="utf-8")
    vq.partition(inbox, q, d)
    assert (q / "broken.json").exists()
    assert "not valid JSON" in (q / "broken.reason.txt").read_text()


def test_non_url_locator_is_quarantined(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    _candidate(inbox, "noturl", [("a blog post I remember", "some words")])
    vq.partition(inbox, q, d)
    assert (q / "noturl.json").exists()


def test_empty_inbox_is_not_an_error(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    assert vq.partition(inbox, q, d) == 0


def test_classify_normalises_both_sides(tmp_path):
    """The fail-CLOSED bug that started this file: normalise page AND quote."""
    page = vq.page_text('<p>He said \u201cAlways Allow\u201d and stopped.</p>')
    assert vq.classify('He said "Always Allow" and stopped.', page) == vq.VERBATIM
