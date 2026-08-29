"""A malformed candidate must be QUARANTINED, never allowed to crash the pass.

Companion to `test_verify_partition.py`. That file proves a record whose QUOTE does
not verify cannot veto its neighbours. This one proves the same property against a
record whose SHAPE is wrong, which is a different code path and a strictly larger
risk: candidates are written by unattended research agents, so "valid JSON that is
not the expected shape" is a routine output, not an edge case.

Why this matters rather than being defensive boilerplate: `partition` builds its
url set by walking every record BEFORE it judges any of them. An `AttributeError`
raised there aborts the whole pass, so a single malformed file reinstates exactly
the all-or-nothing veto that `--partition` exists to remove -- the ratchet returns
wearing a traceback instead of an exit code. A crash is worse than the original
bug, because the original at least logged a verdict.

Offline by contract, like its companion: every fetch is served from a table.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import verify_quotes as vq  # noqa: E402

PAGE_URL = "https://good.example/a"
PAGES = {PAGE_URL: "the sky is blue and the grass is green"}
GOOD_QUOTE = "the sky is blue"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def fake_fetch(url: str):
        if url not in PAGES:
            raise AssertionError(f"test fetched an unexpected url: {url}")
        return PAGES[url]

    monkeypatch.setattr(vq, "fetch", fake_fetch)


def _dirs(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox, tmp_path / "quarantine", tmp_path / "deferred"


def _write(inbox: pathlib.Path, name: str, doc) -> None:
    (inbox / (name + ".json")).write_text(json.dumps(doc), encoding="utf-8")


def _good(inbox: pathlib.Path, name: str) -> None:
    _write(inbox, name, {
        "id": "GAP-900", "title": name,
        "evidence": [{"locator": PAGE_URL, "quote": GOOD_QUOTE,
                      "source_class": "vendor-primary", "title": "t",
                      "date": "2026-01-01"}],
    })


#: Each is valid JSON that `json.loads` accepts happily, and each reaches a
#: different unguarded attribute access inside `partition`.
MALFORMED = {
    "record_is_a_list": [1, 2, 3],
    "record_is_a_string": "not an object",
    "record_is_null": None,
    "evidence_is_a_string": {"id": "GAP-901", "evidence": "not a list"},
    "evidence_is_a_dict": {"id": "GAP-902", "evidence": {"locator": PAGE_URL}},
    "evidence_item_is_a_string": {"id": "GAP-903", "evidence": ["just a string"]},
    "evidence_item_is_null": {"id": "GAP-904", "evidence": [None]},
    "locator_is_an_int": {"id": "GAP-905",
                          "evidence": [{"locator": 123, "quote": GOOD_QUOTE}]},
    "locator_is_null": {"id": "GAP-906",
                        "evidence": [{"locator": None, "quote": GOOD_QUOTE}]},
    "quote_is_an_int": {"id": "GAP-907",
                        "evidence": [{"locator": PAGE_URL, "quote": 42}]},
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_malformed_record_is_quarantined_rather_than_crashing(tmp_path, name):
    inbox, q, d = _dirs(tmp_path)
    _write(inbox, name, MALFORMED[name])

    rc = vq.partition(inbox, q, d)          # must not raise

    assert rc == 0, "partitioning is the tool working, not failing"
    assert (q / (name + ".json")).exists(), "a malformed record belongs in quarantine"
    assert not (inbox / (name + ".json")).exists(), "it must not stay promotable"
    assert (q / (name + ".reason.txt")).exists(), "a human needs to know why"


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_one_malformed_record_does_not_veto_its_good_neighbours(tmp_path, name):
    """The whole point of partitioning, on the shape path rather than the quote path."""
    inbox, q, d = _dirs(tmp_path)
    _good(inbox, "good1")
    _good(inbox, "good2")
    _write(inbox, name, MALFORMED[name])

    rc = vq.partition(inbox, q, d)

    assert rc == 0
    survivors = {p.stem for p in inbox.glob("*.json")}
    assert survivors == {"good1", "good2"}, (
        f"a malformed {name} must not take the good records down with it: {survivors}")
    assert (q / (name + ".json")).exists()


def test_a_reason_names_the_actual_defect(tmp_path):
    """The reason file is the only channel to the human, so it must be specific."""
    inbox, q, d = _dirs(tmp_path)
    _write(inbox, "locator_is_an_int", MALFORMED["locator_is_an_int"])

    vq.partition(inbox, q, d)

    reason = (q / "locator_is_an_int.reason.txt").read_text(encoding="utf-8")
    assert "locator_is_an_int.json" in reason, "name the file"
    assert reason.strip() != "locator_is_an_int.json", "say more than the filename"


def test_a_record_with_no_evidence_at_all_is_quarantined(tmp_path):
    """Zero evidence trivially satisfies 'no failing quote', so it must be caught
    explicitly or an unsupported record promotes on a technicality."""
    inbox, q, d = _dirs(tmp_path)
    _write(inbox, "empty", {"id": "GAP-908", "title": "t", "evidence": []})

    rc = vq.partition(inbox, q, d)

    assert rc == 0
    assert (q / "empty.json").exists(), (
        "a record citing nothing has no verified evidence and must not promote")
    assert not (inbox / "empty.json").exists()


# --------------------------------------------------------------------------
# Staging verified work. Without this, bounding a pass and then promoting the
# inbox promotes the UNPROCESSED tail, whose quotes were never checked.
# --------------------------------------------------------------------------

def test_verified_records_stay_in_the_inbox_when_no_destination_is_given(tmp_path):
    """Backward compatible: omitting `verified` must not change the old behaviour."""
    inbox, q, d = _dirs(tmp_path)
    _good(inbox, "good1")

    assert vq.partition(inbox, q, d) == 0
    assert (inbox / "good1.json").exists()


def test_verified_records_are_staged_when_a_destination_is_given(tmp_path):
    inbox, q, d = _dirs(tmp_path)
    verified = tmp_path / "verified"
    _good(inbox, "good1")
    _good(inbox, "good2")

    assert vq.partition(inbox, q, d, verified=verified) == 0
    assert {p.stem for p in verified.glob("*.json")} == {"good1", "good2"}
    assert list(inbox.glob("*.json")) == [], "nothing checked should remain behind"


def test_bounding_a_pass_leaves_no_unverified_work_promotable(tmp_path):
    """The reason `verified` exists.

    With a bounded pass and no staging, the inbox afterwards holds BOTH the records
    that passed and the tail that was never looked at -- indistinguishable to a
    driver that promotes the inbox. Staging separates them, so the set handed to
    `promote` contains only records whose quotes were actually checked.
    """
    inbox, q, d = _dirs(tmp_path)
    verified = tmp_path / "verified"
    for i in range(5):
        _good(inbox, f"good{i}")

    assert vq.partition(inbox, q, d, max_records=2, verified=verified) == 0

    staged = {p.stem for p in verified.glob("*.json")}
    unprocessed = {p.stem for p in inbox.glob("*.json")}
    assert len(staged) == 2, staged
    assert len(unprocessed) == 3, unprocessed
    assert not (staged & unprocessed), "a record must be in exactly one state"
