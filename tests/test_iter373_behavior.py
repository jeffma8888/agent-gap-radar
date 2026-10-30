"""Iteration 373 hotfix: the per-rule cap's singular remainder is a published note.

``scan --json`` cuts each rule's matched lines at the cap and writes the
remainder to ``location_notes``. When exactly one line is cut the note reads
``(+1 more match)``; otherwise ``(+N more matches)``. The iteration-265 pins
only saw the plural because the self-scan never cut exactly one line until the
repo grew. These nodes pin both spellings on a fixed tmp target, so the
singular stays covered no matter how the repo's own match counts drift.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from test_iter265_behavior import NOTE_DIALECTS

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
LOCATOR = re.compile(r"^[^\n]+:\d+$")

#: Two lines per file, both matched by GAP-041's rule, so N files give 2N hits.
FILE_BODY = (
    'r = client.chat.completions.create(model="m", messages=messages)\n'
    "messages.append(r)\n"
)


def _scan_gap041(target: pathlib.Path, files: int,
                 capsys: pytest.CaptureFixture[str]) -> tuple[dict, list[dict]]:
    """Write ``files`` copies of FILE_BODY, scan, and return (GAP-041, all findings)."""
    target.mkdir()
    for n in range(1, files + 1):
        (target / f"m{n}.py").write_text(FILE_BODY, encoding="utf-8")
    code = main(["scan", str(target), "--gaps", str(GAPS), "--json"])
    out = capsys.readouterr().out
    assert code == 0, out
    findings = json.loads(out)["findings"]
    (gap041,) = [f for f in findings if f["gap_id"] == "GAP-041"]
    return gap041, findings


def _is_note(text: str) -> bool:
    return any(p.match(text) for p in NOTE_DIALECTS)


def test_iter373_b4_exactly_one_cut_line_is_spelled_singular(tmp_path, capsys) -> None:
    """11 files: each of GAP-041's two rules hits 11 lines, shows 10 and cuts 1."""
    gap041, _ = _scan_gap041(tmp_path / "t", 11, capsys)
    assert gap041["verdict"] == "PRESENT", gap041
    assert len(gap041["locations"]) == 20, gap041["locations"]
    assert all(LOCATOR.match(loc) for loc in gap041["locations"]), gap041["locations"]
    assert "(+1 more match)" in gap041["location_notes"], gap041["location_notes"]


def test_iter373_b4_two_cut_lines_are_spelled_plural(tmp_path, capsys) -> None:
    gap041, _ = _scan_gap041(tmp_path / "t", 12, capsys)
    assert gap041["verdict"] == "PRESENT", gap041
    assert "(+2 more matches)" in gap041["location_notes"], gap041["location_notes"]


@pytest.mark.parametrize("files", [11, 12])
def test_iter373_b5_every_note_in_both_payloads_is_a_published_dialect(
        tmp_path, capsys, files: int) -> None:
    _, findings = _scan_gap041(tmp_path / "t", files, capsys)
    notes = [(f["gap_id"], n) for f in findings for n in f.get("location_notes", [])]
    assert notes, "the payload carried no notes; the cap was never exercised"
    offenders = [(gid, n) for gid, n in notes if not _is_note(n)]
    assert offenders == [], offenders


def test_iter373_b2_the_dialect_set_still_rejects_a_locator() -> None:
    assert _is_note("(+1 more match)") and _is_note("(+3 more matches, 2 in test files)")
    assert not _is_note("a.py:3")
