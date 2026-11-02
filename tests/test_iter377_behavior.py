"""Iteration 377: `radar diff` names the PRD target (rank-1 citable record at the
default floor) of each side, in one markdown line and a last `ranking` JSON key.

Every fixture is cross-checked against what bare `radar prd` emits for the same side
(behavior 6), so `diff` can never name a different record than the one the build loop
is handed.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.scoring import CONFIDENCE_FLOOR_DEFAULT
from test_iter77_behavior import _evidence, _record, _register

HEAD = f"Top gap at the default floor ({CONFIDENCE_FLOOR_DEFAULT}): "
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _top_line(document: str) -> str:
    lines = document.splitlines()
    assert lines[2].startswith("Old: "), lines[:4]
    assert lines[4] == "" and lines[5].startswith("## Added ("), lines[:6]
    return lines[3]


def _prd_top(capsys, root: pathlib.Path) -> str | None:
    """What bare `radar prd` builds from, or None when it refuses (exit 2)."""
    code, out, err = _run(capsys, "prd", str(root))
    if code == 2:
        assert out == "" and err.startswith("Error: "), (out, err)
        return None
    assert code == 0, err
    return json.loads(out)["sourceGap"]["id"]


def _ranking(capsys, old: pathlib.Path, new: pathlib.Path) -> dict:
    code, out, err = _run(capsys, "diff", str(old), str(new), "--json")
    assert code == 0 and err == "", err
    payload = json.loads(out)
    assert list(payload) == ["counts", "added", "removed", "changed", "ranking"]
    ranking = payload["ranking"]
    assert list(ranking) == ["old_top", "new_top", "changed"], ranking
    assert ranking["changed"] is (ranking["old_top"] != ranking["new_top"])
    return ranking


def _assert_consistent(capsys, old: pathlib.Path, new: pathlib.Path) -> dict:
    ranking = _ranking(capsys, old, new)
    assert ranking["old_top"] == _prd_top(capsys, old)
    assert ranking["new_top"] == _prd_top(capsys, new)
    return ranking


def _overtaken(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """GAP-101 wins the id tiebreak at tractability 4, then drops to 2 so GAP-102 leads."""
    old = _register(tmp_path / "old", [_record("GAP-101", tractability=4),
                                       _record("GAP-102", tractability=4)])
    new = _register(tmp_path / "new", [_record("GAP-101", tractability=2),
                                       _record("GAP-102", tractability=4)])
    return old, new


def test_b1_b3_a_moved_top_is_named_on_the_line_after_the_domain_sizes(capsys, tmp_path):
    old, new = _overtaken(tmp_path)
    code, document, err = _run(capsys, "diff", str(old), str(new))
    assert code == 0 and err == ""
    assert _top_line(document) == f"{HEAD}GAP-101 -> GAP-102 (changed)."
    changed = document.split("## Changed (1)", 1)[1]
    assert changed.startswith("\n\n- GAP-101\n  - tractability: 4 -> 2\n"), changed
    assert document.endswith("\n") and not document.endswith("\n\n")
    assert _assert_consistent(capsys, old, new) == {
        "old_top": "GAP-101", "new_top": "GAP-102", "changed": True}


def test_b1_an_equal_top_reads_unchanged(capsys, tmp_path):
    old = _register(tmp_path / "old", [_record("GAP-001", severity=5), _record("GAP-002")])
    new = _register(tmp_path / "new", [_record("GAP-001", severity=5)])
    _, document, _ = _run(capsys, "diff", str(old), str(new))
    assert _top_line(document) == f"{HEAD}GAP-001 (unchanged)."
    assert _assert_consistent(capsys, old, new)["changed"] is False


def test_b2_a_below_floor_side_renders_none(capsys, tmp_path):
    weak = _evidence("secondary-summary")
    old = _register(tmp_path / "old", [_record("GAP-001", evidence=weak)])
    new = _register(tmp_path / "new", [_record("GAP-001")])
    code, document, _ = _run(capsys, "diff", str(old), str(new))
    assert code == 0
    assert _top_line(document) == f"{HEAD}none -> GAP-001 (changed)."
    assert _assert_consistent(capsys, old, new) == {
        "old_top": None, "new_top": "GAP-001", "changed": True}


def test_b2_both_sides_without_a_ranked_record_read_none_unchanged(capsys, tmp_path):
    weak = _evidence("secondary-summary")
    old = _register(tmp_path / "old", [_record("GAP-001", evidence=weak)])
    new = _register(tmp_path / "new", [_record("GAP-001", status="addressed")])
    _, document, _ = _run(capsys, "diff", str(old), str(new))
    assert _top_line(document) == f"{HEAD}none (unchanged)."
    assert _assert_consistent(capsys, old, new) == {
        "old_top": None, "new_top": None, "changed": False}


def test_b4_an_added_record_that_outranks_becomes_the_new_top(capsys, tmp_path):
    old = _register(tmp_path / "old", [_record("GAP-001")])
    new = _register(tmp_path / "new", [_record("GAP-001"), _record("GAP-009", severity=5)])
    _, document, _ = _run(capsys, "diff", str(old), str(new))
    assert _top_line(document) == f"{HEAD}GAP-001 -> GAP-009 (changed)."
    assert "## Added (1)\n\n- GAP-009" in document
    assert _assert_consistent(capsys, old, new)["new_top"] == "GAP-009"


def test_b5_a_top_moved_to_a_terminal_status_hands_over_to_the_next_citable(capsys,
                                                                           tmp_path):
    old = _register(tmp_path / "old", [_record("GAP-001", severity=5), _record("GAP-002")])
    new = _register(tmp_path / "new", [_record("GAP-001", severity=5, status="addressed"),
                                       _record("GAP-002")])
    _, document, _ = _run(capsys, "diff", str(old), str(new))
    assert _top_line(document) == f"{HEAD}GAP-001 -> GAP-002 (changed)."
    assert _assert_consistent(capsys, old, new)["new_top"] == "GAP-002"


def test_b8_a_moved_top_alone_is_not_a_regression_and_the_document_is_unchanged(
        capsys, tmp_path):
    old, new = _overtaken(tmp_path)
    for surface in ((), ("--json",)):
        _, plain, _ = _run(capsys, "diff", str(old), str(new), *surface)
        code, gated, err = _run(capsys, "diff", str(old), str(new), *surface, "--exit-code")
        assert code == 0 and err == "" and gated == plain


def test_b9_the_live_register_against_itself_is_unchanged_and_byte_stable(capsys):
    root = str(REPO_ROOT)
    _, first, _ = _run(capsys, "diff", root, root)
    _, second, _ = _run(capsys, "diff", root, root)
    assert first == second and first.endswith("\n") and not first.endswith("\n\n")
    line = _top_line(first)
    assert line.startswith(HEAD + "GAP-") and line.endswith(" (unchanged)."), line
    for section in ("Added", "Removed", "Changed"):
        assert f"## {section} (0)" in first
    ranking = _ranking(capsys, REPO_ROOT, REPO_ROOT)
    assert ranking["old_top"] == ranking["new_top"] == _prd_top(capsys, REPO_ROOT)
    assert ranking["old_top"] is not None


@pytest.mark.parametrize("side", ["old", "new"])
def test_b2_an_empty_side_reads_none(capsys, tmp_path, side):
    full = _register(tmp_path / "full", [_record("GAP-001")])
    (tmp_path / "empty" / "gaps").mkdir(parents=True)
    empty = tmp_path / "empty"
    old, new = (empty, full) if side == "old" else (full, empty)
    ranking = _ranking(capsys, old, new)
    assert ranking[f"{side}_top"] is None and ranking["changed"] is True
