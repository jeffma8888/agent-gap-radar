"""Iteration 344 behaviors: ``radar show <ID> [<repo>] --json``.

Emit the full gap brief as a stable JSON object via ``json_document()``,
closing the last ``--json`` parity gap in the verb surface.

THE ISOLATION CONTRACT IS HONORED.  Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7.  No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff.  Every
behavioral claim is measured by running the CLI, or by comparing verb
output against a git-archived pre-change tree, both of which are inside
the contract.
"""

from __future__ import annotations

import json as _json
import pathlib

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"


EXPECTED_TOP_KEYS = [
    "gap_id", "title", "layer", "gap_type", "status",
    "priority", "confidence", "below_floor", "strongest_source",
    "problem", "symptom", "why_now", "existing", "build_hypothesis",
    "tags", "evidence",
]

EXPECTED_EVIDENCE_KEYS = [
    "source_class", "title", "locator", "date", "quote", "confidence_without",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cli(argv, capsys):
    try:
        rc = main(argv) or 0
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# ---------------------------------------------------------------------------
# B1 -- ``radar show GAP-001 --json`` exits 0, valid JSON, 16 top-level
# keys in contract order, evidence array with 6 required keys in order,
# exactly one trailing newline.  (EB1, EB2, EB3)
# ---------------------------------------------------------------------------

def test_b1_show_json_valid_structure(capsys):
    rc, out, err = _cli(["show", "GAP-001", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    assert out.endswith("\n"), "document must end in a newline"
    assert not out.endswith("\n\n"), "document must end in exactly one newline"

    doc = _json.loads(out)
    assert list(doc.keys()) == EXPECTED_TOP_KEYS, (
        f"top-level key order mismatch: {list(doc.keys())}")

    assert isinstance(doc["gap_id"], str)
    assert doc["gap_id"] == "GAP-001"
    assert isinstance(doc["below_floor"], bool)
    assert isinstance(doc["confidence"], int)
    assert isinstance(doc["priority"], (int, float))
    assert isinstance(doc["tags"], list)
    assert isinstance(doc["existing"], list)

    evidence = doc["evidence"]
    assert isinstance(evidence, list)
    assert len(evidence) >= 1, "must have at least one evidence item"
    for item in evidence:
        assert list(item.keys()) == EXPECTED_EVIDENCE_KEYS, (
            f"evidence key order mismatch: {list(item.keys())}")
        assert isinstance(item["source_class"], str)
        assert isinstance(item["confidence_without"], int)


# ---------------------------------------------------------------------------
# B3 -- ``radar show NONEXISTENT --json`` exits 2 with ``Error:`` prefix on
# stderr, empty stdout.  (EB6)
# ---------------------------------------------------------------------------

def test_b3_nonexistent_gap_exits_2(capsys):
    rc, out, err = _cli(
        ["show", "NONEXISTENT", str(GAPS), "--json"], capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    err_lines = [l for l in err.splitlines() if l.strip()]
    assert len(err_lines) >= 1, "must have at least one stderr line"
    assert err_lines[-1].startswith("Error: "), (
        f"last stderr line must start 'Error: '; got {err_lines[-1]!r}")


# ---------------------------------------------------------------------------
# B4 -- canonicalization: ``GAP-9`` resolves to ``GAP-009`` in JSON output.
# (EB7 wiring, implicit via existing id resolution)
# ---------------------------------------------------------------------------

def test_b4_canonicalization(capsys):
    rc, out, err = _cli(["show", "GAP-9", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    doc = _json.loads(out)
    assert doc["gap_id"] == "GAP-009", (
        f"GAP-9 must canonicalize to GAP-009; got {doc['gap_id']!r}")


# ---------------------------------------------------------------------------
# B5 -- determinism: two consecutive ``show --json`` runs produce
# byte-identical output.  (EB5)
# ---------------------------------------------------------------------------

def test_b5_determinism(capsys):
    argv = ["show", "GAP-001", str(GAPS), "--json"]
    rc1, out1, _ = _cli(argv, capsys)
    rc2, out2, _ = _cli(argv, capsys)
    assert rc1 == rc2 == 0
    assert out1 == out2, "two identical show --json runs must be byte-identical"
