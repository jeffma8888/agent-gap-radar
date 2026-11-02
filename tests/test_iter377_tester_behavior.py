"""Iteration 377 (tester): black-box pins for the `diff` PRD-target line and `ranking` key.

The engineer's module drives small hand-built registers. This one adds:

- LIVE-REGISTER copies in `tmp_path`: the real top record is re-scored, moved to every
  terminal status, or deleted, and `diff` must name exactly what bare `radar prd` names
  for each side (behaviors 3, 5, 6);
- markdown/JSON parity: the top line is parsed with ONE anchored regex and compared with
  the `ranking` object over a shared CASES table, plus a "shape reached" node proving the
  table really exercises changed, unchanged, none-old, none-new and none-both (1, 2, 7);
- symmetry: swapping the sides swaps old_top/new_top and keeps `changed`;
- the floor is a floor, not a priority tiebreak: a higher-priority below-floor record is
  never the top, and a `partially-addressed` record still is (citable);
- `--exit-code`: a removal that also moves the top still exits 1 with the same document,
  and reopening the terminal top exits 1 (8);
- a fresh process prints the same bytes as the in-process run, ending in one newline (9).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main
from agent_gap_radar.scoring import CONFIDENCE_FLOOR_DEFAULT
from test_iter77_behavior import _evidence, _record, _register

REPO = pathlib.Path(__file__).resolve().parents[1]
GID = r"GAP-\d+"
LINE = re.compile(
    rf"^Top gap at the default floor \({CONFIDENCE_FLOOR_DEFAULT}\): "
    rf"(?:(?P<same>{GID}|none) \(unchanged\)|(?P<old>{GID}|none) -> (?P<new>{GID}|none) \(changed\))\.$"
)


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _prd_top(capsys, root: pathlib.Path) -> str | None:
    code, out, err = _run(capsys, "prd", str(root))
    if code == 2:
        assert out == "" and err.startswith("Error: "), (out, err)
        return None
    assert code == 0, err
    return json.loads(out)["sourceGap"]["id"]


def _parse_line(document: str) -> tuple[str | None, str | None, bool]:
    lines = document.splitlines()
    assert lines[2].startswith("Old: ") and lines[4] == "" and lines[5].startswith("## Added ("), lines[:6]
    tops = [line for line in lines if line.startswith("Top gap at the default floor")]
    assert tops == [lines[3]], tops  # exactly one such line, at index 3
    match = LINE.match(lines[3])
    assert match, lines[3]
    if match["same"] is not None:
        top = None if match["same"] == "none" else match["same"]
        return top, top, False
    old = None if match["old"] == "none" else match["old"]
    new = None if match["new"] == "none" else match["new"]
    assert old != new, lines[3]  # "(changed)" must never name the same id twice
    return old, new, True


def _both(capsys, old: pathlib.Path, new: pathlib.Path) -> tuple[str, dict]:
    code, document, err = _run(capsys, "diff", str(old), str(new))
    assert code == 0 and err == "", err
    assert document.endswith("\n") and not document.endswith("\n\n")
    code, out, err = _run(capsys, "diff", str(old), str(new), "--json")
    assert code == 0 and err == "", err
    assert out.endswith("\n") and not out.endswith("\n\n")
    payload = json.loads(out)
    assert list(payload) == ["counts", "added", "removed", "changed", "ranking"]
    assert list(payload["ranking"]) == ["old_top", "new_top", "changed"]
    return document, payload


def _check_parity_and_oracle(capsys, old, new) -> tuple[str | None, str | None, bool]:
    document, payload = _both(capsys, old, new)
    ranking = payload["ranking"]
    parsed = _parse_line(document)
    assert parsed == (ranking["old_top"], ranking["new_top"], ranking["changed"]), (parsed, ranking)
    assert type(ranking["changed"]) is bool
    assert ranking["changed"] is (ranking["old_top"] != ranking["new_top"])
    assert ranking["old_top"] == _prd_top(capsys, old)
    assert ranking["new_top"] == _prd_top(capsys, new)
    return parsed


# -- shared fixtures -------------------------------------------------------------------

WEAK = _evidence("secondary-summary")


def _case_records(name: str) -> tuple[list[dict], list[dict]]:
    a, b = _record("GAP-001", severity=5), _record("GAP-002")
    weak_hi = _record("GAP-001", severity=5, evidence=WEAK)
    return {
        "unchanged": ([a, b], [a, b]),
        "unchanged-with-edit": ([a, b], [a, _record("GAP-002", frequency=1)]),
        "rescored": ([a, b], [_record("GAP-001", severity=1), b]),
        "removed-top": ([a, b], [b]),
        "added-top": ([b], [a, b]),
        "terminal-top": ([a, b], [_record("GAP-001", severity=5, status="retired"), b]),
        "below-floor-old": ([weak_hi], [a]),
        "below-floor-new": ([a], [weak_hi]),
        "none-both": ([weak_hi], [_record("GAP-001", status="addressed")]),
        "floor-beats-priority": ([weak_hi, b], [weak_hi, b]),
        "partially-addressed": ([a, b], [_record("GAP-001", severity=5, status="partially-addressed"), b]),
    }[name]


CASES = [
    "unchanged", "unchanged-with-edit", "rescored", "removed-top", "added-top", "terminal-top",
    "below-floor-old", "below-floor-new", "none-both", "floor-beats-priority",
    "partially-addressed",
]

EXPECTED = {
    "unchanged": ("GAP-001", "GAP-001", False),
    "unchanged-with-edit": ("GAP-001", "GAP-001", False),
    "rescored": ("GAP-001", "GAP-002", True),
    "removed-top": ("GAP-001", "GAP-002", True),
    "added-top": ("GAP-002", "GAP-001", True),
    "terminal-top": ("GAP-001", "GAP-002", True),
    "below-floor-old": (None, "GAP-001", True),
    "below-floor-new": ("GAP-001", None, True),
    "none-both": (None, None, False),
    "floor-beats-priority": ("GAP-002", "GAP-002", False),
    "partially-addressed": ("GAP-001", "GAP-001", False),
}


def _pair(tmp_path: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path]:
    old, new = _case_records(name)
    return _register(tmp_path / "old", old), _register(tmp_path / "new", new)


@pytest.mark.parametrize("name", CASES)
def test_b1_b2_b6_b7_markdown_line_json_ranking_and_prd_agree(capsys, tmp_path, name):
    old, new = _pair(tmp_path, name)
    assert _check_parity_and_oracle(capsys, old, new) == EXPECTED[name]


def test_cases_table_reaches_every_line_shape():
    shapes = set()
    for old, new, changed in EXPECTED.values():
        if not changed:
            shapes.add("none-unchanged" if old is None else "id-unchanged")
        elif old is None:
            shapes.add("none-old")
        elif new is None:
            shapes.add("none-new")
        else:
            shapes.add("id-changed")
    assert shapes == {"none-unchanged", "id-unchanged", "none-old", "none-new", "id-changed"}


@pytest.mark.parametrize("name", CASES)
def test_swapping_sides_swaps_the_tops(capsys, tmp_path, name):
    old, new = _pair(tmp_path, name)
    forward = _check_parity_and_oracle(capsys, old, new)
    backward = _check_parity_and_oracle(capsys, new, old)
    assert backward == (forward[1], forward[0], forward[2])


def test_b7_other_json_keys_match_the_markdown_sections(capsys, tmp_path):
    old, new = _pair(tmp_path, "removed-top")
    document, payload = _both(capsys, old, new)
    for section, key in (("Added", "added"), ("Removed", "removed"), ("Changed", "changed")):
        assert f"## {section} ({len(payload[key])})" in document
    assert [r["gap_id"] for r in payload["removed"]] == ["GAP-001"]
    assert payload["added"] == [] and payload["changed"] == []


# -- live register copies --------------------------------------------------------------

def _live_copy(dest: pathlib.Path) -> pathlib.Path:
    shutil.copytree(REPO / "gaps", dest / "gaps")
    return dest


def _gap_file(root: pathlib.Path, gid: str) -> pathlib.Path:
    (path,) = sorted((root / "gaps").glob(f"{gid}-*.json"))
    return path


def _edit(root: pathlib.Path, gid: str, **over) -> None:
    path = _gap_file(root, gid)
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(over)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def live_pair(tmp_path, capsys):
    old = _live_copy(tmp_path / "old")
    new = _live_copy(tmp_path / "new")
    top = _prd_top(capsys, old)
    assert top is not None
    return old, new, top


def test_b3_live_top_rescored_down_hands_over_and_changed_lists_only_it(capsys, live_pair):
    old, new, top = live_pair
    record = json.loads(_gap_file(old, top).read_text(encoding="utf-8"))
    _edit(new, top, tractability=max(1, record["tractability"] - 2))
    old_top, new_top, changed = _check_parity_and_oracle(capsys, old, new)
    assert old_top == top and new_top not in (None, top) and changed is True
    document, payload = _both(capsys, old, new)
    assert "## Changed (1)" in document and [c["gap_id"] for c in payload["changed"]] == [top]
    assert "## Added (0)" in document and "## Removed (0)" in document


@pytest.mark.parametrize("status", sorted(taxonomy.terminal_statuses()))
def test_b5_live_top_moved_to_each_terminal_status_is_never_the_new_top(capsys, live_pair, status):
    old, new, top = live_pair
    _edit(new, top, status=status)
    old_top, new_top, changed = _check_parity_and_oracle(capsys, old, new)
    assert old_top == top and new_top is not None and new_top != top and changed
    # forward is not a regression; the reverse reopens the gap, which --exit-code flags
    _, plain, _ = _run(capsys, "diff", str(old), str(new))
    code, gated, _ = _run(capsys, "diff", str(old), str(new), "--exit-code")
    assert code == 0 and gated == plain
    _, plain, _ = _run(capsys, "diff", str(new), str(old))
    code, gated, _ = _run(capsys, "diff", str(new), str(old), "--exit-code")
    assert code == 1 and gated == plain
    assert _parse_line(gated) == (new_top, top, True)


def test_b8_live_top_deleted_exits_1_under_exit_code_with_the_same_document(capsys, live_pair):
    old, new, top = live_pair
    _gap_file(new, top).unlink()
    old_top, new_top, _ = _check_parity_and_oracle(capsys, old, new)
    assert old_top == top and new_top not in (None, top)
    for surface in ((), ("--json",)):
        _, plain, _ = _run(capsys, "diff", str(old), str(new), *surface)
        code, gated, err = _run(capsys, "diff", str(old), str(new), *surface, "--exit-code")
        assert code == 1 and err == "" and gated == plain


def test_b9_fresh_process_prints_the_same_bytes(capsys, tmp_path):
    old, new = _pair(tmp_path, "rescored")
    for surface in ((), ("--json",)):
        _, in_process, _ = _run(capsys, "diff", str(old), str(new), *surface)
        proc = subprocess.run(
            [sys.executable, "-m", "agent_gap_radar.cli", "diff", str(old), str(new), *surface],
            capture_output=True, text=True, encoding="utf-8", cwd=REPO, timeout=120,
        )
        assert proc.returncode == 0 and proc.stderr == ""
        assert proc.stdout == in_process
        assert proc.stdout.endswith("\n") and not proc.stdout.endswith("\n\n")


def test_errors_stay_on_stderr_with_exit_2(capsys, tmp_path):
    old, _ = _pair(tmp_path, "unchanged")
    code, out, err = _run(capsys, "diff", str(old), str(tmp_path / "missing"))
    assert code == 2 and out == "" and err.startswith("Error: ")
