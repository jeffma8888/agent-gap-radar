"""Iteration 342 behaviors: ``skipped_files`` count-and-disclose on ``scan --json``.

Surface the count of ``_decode``-skipped files (oversized, non-UTF-8,
unreadable) in ``CheckOutcome`` and ``scan --json``, so ``ABSENT`` never
silently rests on unread bytes.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-9. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every
behavioral claim is measured by running the CLI, calling the public
``run_check`` / ``scan`` / ``scan_json`` API (all used by existing tests
under ``tests/``), or by comparing verb output against a git-archived
pre-change tree, all of which are inside the contract.
"""

from __future__ import annotations

import json as _json
import pathlib

from agent_gap_radar.checks import Verdict, run_check
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT_DOC = REPO / "docs" / "CONSUMER_CONTRACT.md"

MARKER = "GAPRADAR_ITER342_MARKER"
MITIGATION = "GAPRADAR_ITER342_MITIGATION"
MAX_FILE_BYTES = 512 * 1024


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


def _materialise(root, text_files, binary_files=None):
    target = root / "target"
    target.mkdir(parents=True, exist_ok=True)
    for rel, content in text_files.items():
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if binary_files:
        for rel, content in binary_files.items():
            p = target / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    return target


def _check_dict():
    """A content check that fires on MARKER and is mitigated by MITIGATION."""
    return {
        "id": "CHK-342",
        "rationale": "r",
        "manual_question": "q?",
        "present_when": {
            "kind": "content_matches",
            "globs": ["**/*.py"],
            "pattern": MARKER,
        },
        "mitigated_when": {
            "kind": "content_matches",
            "globs": ["**/*.py"],
            "pattern": MITIGATION,
        },
    }


def _gap_record():
    """A schema-valid gap record with a content check using mitigated_when."""
    return {
        "id": "GAP-900",
        "title": "test gap for skipped files",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [{
            "source_class": "first-party-field",
            "title": "t",
            "locator": "https://example.invalid/x",
            "date": "2026-01-02",
            "quote": "the verbatim line",
        }],
        "check": {
            "id": "CHK-900",
            "rationale": "r",
            "manual_question": "q?",
            "present_when": {
                "kind": "content_matches",
                "globs": ["**/*.py"],
                "pattern": MARKER,
            },
            "mitigated_when": {
                "kind": "content_matches",
                "globs": ["**/*.py"],
                "pattern": MITIGATION,
            },
            "fixtures": {
                "bad": {"a.py": MARKER + "\n"},
                "good": {"a.py": MITIGATION + "\n"},
            },
        },
    }


def _write_register(root, records):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(
            _json.dumps(rec), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# B1 -- oversized file (>512 KiB) increments CheckOutcome.skipped_files
# (EB1, EB2, EB5)
# ---------------------------------------------------------------------------

def test_b1_oversized_file_increments_skipped_files(tmp_path):
    target = _materialise(tmp_path, {
        "normal.py": MITIGATION + "\n",
        "oversized.py": "x" * (MAX_FILE_BYTES + 1) + "\n",
    })
    outcome = run_check(_check_dict(), target)
    assert outcome.verdict is Verdict.ABSENT, (
        f"expected ABSENT (mitigated via normal.py); got {outcome.verdict.value}")
    assert outcome.skipped_files >= 1, (
        f"oversized file must increment skipped_files; got {outcome.skipped_files}")


# ---------------------------------------------------------------------------
# B2 -- binary file (non-UTF-8) increments CheckOutcome.skipped_files
# (EB1, EB2, EB6)
# ---------------------------------------------------------------------------

def test_b2_binary_file_increments_skipped_files(tmp_path):
    target = _materialise(tmp_path, {
        "normal.py": MITIGATION + "\n",
    }, binary_files={
        "binary.py": bytes(range(256)) * 100,
    })
    outcome = run_check(_check_dict(), target)
    assert outcome.verdict is Verdict.ABSENT, (
        f"expected ABSENT (mitigated via normal.py); got {outcome.verdict.value}")
    assert outcome.skipped_files >= 1, (
        f"binary file must increment skipped_files; got {outcome.skipped_files}")


# ---------------------------------------------------------------------------
# B3 -- scan --json on this repo: skipped_files key present on all findings,
# all zero on a target with no skipped files (EB3, EB8)
# ---------------------------------------------------------------------------

def test_b3_scan_json_skipped_files_key_present_and_zero(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    doc = _json.loads(out)
    findings = doc["findings"]
    assert len(findings) > 0, "must have at least one finding"
    for f in findings:
        assert "skipped_files" in f, (
            f"finding {f.get('gap_id')} missing skipped_files key")
        assert isinstance(f["skipped_files"], int), (
            f"skipped_files must be int; got {type(f['skipped_files']).__name__}")
        assert f["skipped_files"] == 0, (
            f"on a target with no skipped files, {f.get('gap_id')} "
            f"reports skipped_files={f['skipped_files']}")


# ---------------------------------------------------------------------------
# B5 -- scan --json on synthetic target with oversized file via scan API
# (EB3, EB5): the skipped_files integer propagates through scan_json.
# ---------------------------------------------------------------------------

def test_b5_scan_json_oversized_file_via_scan_api(tmp_path):
    reg = _write_register(tmp_path / "b5", [_gap_record()])
    target = _materialise(tmp_path / "b5t", {
        "normal.py": MITIGATION + "\n",
        "oversized.py": "x" * (MAX_FILE_BYTES + 1) + "\n",
    })
    result = scan(load_all(reg), target)
    payload = _json.loads(scan_json(result))
    findings = payload["findings"]
    assert len(findings) == 1, f"expected 1 finding; got {len(findings)}"
    f = findings[0]
    assert f["gap_id"] == "GAP-900"
    assert f["verdict"] == "ABSENT"
    assert "skipped_files" in f, "skipped_files key must be present"
    assert isinstance(f["skipped_files"], int)
    assert f["skipped_files"] >= 1, (
        f"oversized file must produce skipped_files >= 1; "
        f"got {f['skipped_files']}")


# ---------------------------------------------------------------------------
# B6 -- scan --json on synthetic target with binary file via scan API
# (EB3, EB6): the skipped_files integer propagates through scan_json.
# ---------------------------------------------------------------------------

def test_b6_scan_json_binary_file_via_scan_api(tmp_path):
    reg = _write_register(tmp_path / "b6", [_gap_record()])
    target = _materialise(tmp_path / "b6t", {
        "normal.py": MITIGATION + "\n",
    }, binary_files={
        "binary.py": bytes(range(256)) * 100,
    })
    result = scan(load_all(reg), target)
    payload = _json.loads(scan_json(result))
    findings = payload["findings"]
    assert len(findings) == 1, f"expected 1 finding; got {len(findings)}"
    f = findings[0]
    assert f["gap_id"] == "GAP-900"
    assert f["verdict"] == "ABSENT"
    assert "skipped_files" in f, "skipped_files key must be present"
    assert isinstance(f["skipped_files"], int)
    assert f["skipped_files"] >= 1, (
        f"binary file must produce skipped_files >= 1; "
        f"got {f['skipped_files']}")


# ---------------------------------------------------------------------------
# B7 -- markdown scan does not contain skipped_files annotation (EB4)
# The disclosure is JSON-only; the markdown is a human summary.
# ---------------------------------------------------------------------------

def test_b7_markdown_no_skipped_annotation(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS)], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert "skipped_files" not in out, (
        "markdown scan must not contain skipped_files annotation; "
        "disclosure is JSON-only per spec")


# ---------------------------------------------------------------------------
# B8 -- consumer contract discloses skipped_files (EB9)
# ---------------------------------------------------------------------------

def test_b8_consumer_contract_discloses_skipped_files():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "skipped_files" in text, (
        "CONSUMER_CONTRACT.md must disclose skipped_files")


# ---------------------------------------------------------------------------
# B9 -- clean target (all readable files) → skipped_files == 0 (EB1, EB2)
# ---------------------------------------------------------------------------

def test_b9_clean_target_skipped_files_zero(tmp_path):
    target = _materialise(tmp_path, {
        "normal.py": MITIGATION + "\n",
    })
    outcome = run_check(_check_dict(), target)
    assert outcome.skipped_files == 0, (
        f"clean target must have skipped_files == 0; "
        f"got {outcome.skipped_files}")


# ---------------------------------------------------------------------------
# B10 -- determinism: two scan --json runs produce identical skipped_files (EB3)
# ---------------------------------------------------------------------------

def test_b10_scan_json_deterministic(capsys):
    argv = ["scan", str(REPO), "--gaps", str(GAPS), "--json"]
    rc1, out1, _ = _cli(argv, capsys)
    rc2, out2, _ = _cli(argv, capsys)
    assert rc1 == rc2 == 0
    assert out1 == out2, "two identical scan --json runs must be byte-identical"
