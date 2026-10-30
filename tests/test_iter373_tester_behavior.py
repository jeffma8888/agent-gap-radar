"""Iteration 373 hotfix, tester's independent arm (black-box, subprocess-driven).

The engineer's module drives ``main()`` in-process and reuses the iteration-265
dialect tuple. This module deliberately differs: it runs the CLI as a separate
process, derives the expected remainder from arithmetic (hits minus the 10 shown
per rule), checks grammatical number agreement in BOTH directions, covers the
singular spelling with the ``, M in test files`` tail, and fuzzes the shared
first dialect with its own accept/reject grid.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

import test_iter265_behavior as t265

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
LOCATOR = re.compile(r"^[^\n]+:\d+$")
SHOWN_PER_RULE = 10
BODY = (
    'r = client.chat.completions.create(model="m", messages=messages)\n'
    "messages.append(r)\n"
)
#: Independent oracle for the remainder note: number must agree with the count.
REMAINDER = re.compile(r"^\(\+(\d+) more (match|matches)(?:, (\d+) in test files)?\)$")


def _run_scan(target: pathlib.Path) -> tuple[bytes, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "scan", str(target),
         "--gaps", str(GAPS), "--json"],
        capture_output=True, cwd=str(target),
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert proc.stderr == b"", proc.stderr
    return proc.stdout, json.loads(proc.stdout)


def _target(root: pathlib.Path, src_files: int, test_files: int = 0) -> pathlib.Path:
    root.mkdir()
    for n in range(1, src_files + 1):
        (root / f"m{n}.py").write_text(BODY, encoding="utf-8")
    if test_files:
        (root / "tests").mkdir()
        for n in range(1, test_files + 1):
            (root / "tests" / f"test_x{n}.py").write_text(BODY, encoding="utf-8")
    return root


def _gap041(payload: dict) -> dict:
    (hit,) = [f for f in payload["findings"] if f["gap_id"] == "GAP-041"]
    return hit


def _remainders(finding: dict) -> list[re.Match[str]]:
    out = []
    for note in finding.get("location_notes", []):
        if "more match" in note:
            m = REMAINDER.match(note)
            assert m is not None, f"remainder note outside the published shape: {note!r}"
            out.append(m)
    return out


@pytest.mark.parametrize("files", [10, 11, 12, 13])
def test_iter373t_remainder_count_and_number_agree_with_arithmetic(tmp_path, files) -> None:
    """Each of GAP-041's two rules hits ``files`` lines; the cut is files - 10."""
    _, payload = _run_scan(_target(tmp_path / "t", files))
    g = _gap041(payload)
    assert g["verdict"] == "PRESENT", g
    assert len(g["locations"]) == 2 * SHOWN_PER_RULE, g["locations"]
    assert all(LOCATOR.match(loc) for loc in g["locations"]), g["locations"]
    rem = _remainders(g)
    cut = files - SHOWN_PER_RULE
    if cut == 0:
        assert rem == [], [m.group(0) for m in rem]
        return
    assert len(rem) == 2, [m.group(0) for m in rem]
    for m in rem:
        assert int(m.group(1)) == cut, m.group(0)
        assert m.group(2) == ("match" if cut == 1 else "matches"), m.group(0)
        assert m.group(3) is None, m.group(0)


def test_iter373t_singular_with_test_file_tail(tmp_path) -> None:
    """10 source files + 1 test file: the one cut line is the test-file one."""
    _, payload = _run_scan(_target(tmp_path / "t", 10, test_files=1))
    notes = [m.group(0) for m in _remainders(_gap041(payload))]
    assert notes == ["(+1 more match, 1 in test files)"] * 2, notes
    # The iteration-265 dialect set (the fixed one) must accept this spelling too.
    assert all(t265._is_note(n) for n in notes), notes


def test_iter373t_every_note_in_every_payload_is_a_265_dialect(tmp_path) -> None:
    shapes = [(11, 0), (12, 0), (10, 1), (11, 2)]
    seen = []
    for i, (src, tst) in enumerate(shapes):
        _, payload = _run_scan(_target(tmp_path / f"t{i}", src, test_files=tst))
        for f in payload["findings"]:
            for note in f.get("location_notes", []):
                seen.append(note)
                assert t265._is_note(note), (f["gap_id"], note)
            for loc in f["locations"]:
                assert not t265._is_note(loc), (f["gap_id"], loc)
    assert any(n.startswith("(+1 more match") for n in seen), seen
    assert any("more matches" in n for n in seen), seen


ACCEPT = [
    "(+1 more match)",
    "(+1 more match, 1 in test files)",
    "(+2 more matches)",
    "(+120 more matches, 7 in test files)",
]
REJECT = [
    "a.py:3",
    "src/agent_gap_radar/x.py:10",
    "(+1 more match",
    "+1 more match)",
    "(+ more match)",
    "(+1 more match, in test files)",
    "(+1 more match) a.py:3",
    "(+1 more mat)",
]


@pytest.mark.parametrize("text", ACCEPT)
def test_iter373t_first_dialect_accepts_both_numbers(text) -> None:
    assert t265.NOTE_DIALECTS[0].match(text), text


@pytest.mark.parametrize("text", REJECT)
def test_iter373t_dialect_set_rejects_non_notes(text) -> None:
    assert not t265._is_note(text), text


def test_iter373t_contract_names_both_spellings_in_one_paragraph() -> None:
    paragraphs = CONTRACT.read_text(encoding="utf-8").split("\n\n")
    both = [p for p in paragraphs if "(+N more matches)" in p and "(+1 more match)" in p]
    assert len(both) == 1, len(both)
    assert "exactly one" in both[0], both[0]


def test_iter373t_scan_bytes_are_stable_and_end_in_one_newline(tmp_path) -> None:
    target = _target(tmp_path / "t", 11, test_files=1)
    first, _ = _run_scan(target)
    second, _ = _run_scan(target)
    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n"), first[-4:]
