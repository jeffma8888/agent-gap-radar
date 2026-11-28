"""Iteration 428 behaviors: the oldest Done-ledger rows move verbatim to PRODUCT_ARCHIVE.md.

Black-box: the roadmap files are read as text, the integrity tool is run as a child process,
and the committed helpers / brakes are driven through their public names. The split is judged
against an INDEPENDENT rejoin written here (not only `tests/_roadmap.rejoin`), and history is
judged against the immutable parent commit `PARENT` -- a fixed sha the ship cannot rewrite --
skipping loudly when git cannot answer (an exported tarball, a shallow clone).

Every test takes a fixture argument on purpose: `test_iter62_behavior`'s durability sweep
re-invokes ZERO-argument ledger-reading tests over a synthetic grown ledger, and these pins are
about this checkout's real files, not about any document the sweep substitutes.
"""

from __future__ import annotations

import collections
import pathlib
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

import _roadmap
import test_iter368_behavior as m368
import test_iter368_tester_behavior as m368t

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

INDEX = ROOT / "PRODUCT.md"
ARCHIVE = ROOT / "PRODUCT_ARCHIVE.md"
README = ROOT / "README.md"

#: The immutable parent of iteration 428's ship (iteration 427's ship commit).
PARENT = "a240466"
THIS_ITER = 428
POINTER_RE = re.compile(r"^Rows iter \d+\.\.\d+ are archived verbatim in `PRODUCT_ARCHIVE\.md`\.$")
ROW_RE = re.compile(r"^- iter (\d+) ")
ARCHIVE_HEADING = "## Done ledger (archive)"
INDEX_HEADING = "## Done ledger"


def _rows_after(text: str, heading: str) -> list[str]:
    lines = text.split("\n")
    assert heading in lines, f"no {heading!r} heading"
    return [line for line in lines[lines.index(heading) + 1 :] if ROW_RE.match(line)]


def _independent_rejoin(index_text: str, archive_text: str) -> str:
    lines = index_text.split("\n")
    at = [i for i, line in enumerate(lines) if POINTER_RE.match(line)]
    assert len(at) == 1, f"expected exactly one pointer line, found {len(at)}"
    p = at[0]
    assert lines[p + 1] == "", "pointer must be followed by one blank line"
    rows = _rows_after(archive_text, ARCHIVE_HEADING)
    return "\n".join(lines[:p] + rows + lines[p + 2 :])


def _git_show(spec: str) -> str | None:
    try:
        proc = subprocess.run(["git", "show", spec], cwd=ROOT, capture_output=True,
                              text=True, timeout=60, check=False)
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


@pytest.fixture(scope="module")
def docs() -> SimpleNamespace:
    index = INDEX.read_text(encoding="utf-8")
    archive = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.is_file() else None
    return SimpleNamespace(index=index, archive=archive)


@pytest.fixture(scope="module")
def parent_text() -> str:
    text = _git_show(f"{PARENT}:PRODUCT.md")
    if text is None:
        pytest.skip(f"git cannot show {PARENT}:PRODUCT.md (no git, or a shallow clone)")
    return text


# --- shape of the split ----------------------------------------------------------------------


def test_shape_archive_exists_with_title_heading_and_one_trailing_newline(docs) -> None:
    assert docs.archive is not None, "PRODUCT_ARCHIVE.md is missing"
    assert docs.archive.startswith("# ")
    assert ARCHIVE_HEADING in docs.archive.split("\n")
    assert docs.archive.endswith("\n") and not docs.archive.endswith("\n\n")


def test_shape_index_has_exactly_one_pointer_inside_the_ledger_section(docs) -> None:
    lines = docs.index.split("\n")
    at = [i for i, line in enumerate(lines) if POINTER_RE.match(line)]
    assert len(at) == 1, at
    assert at[0] > lines.index(INDEX_HEADING)
    assert lines[at[0] + 1] == ""
    # The first index row after the pointer is newer than every archived row.
    archived = [int(ROW_RE.match(r).group(1)) for r in _rows_after(docs.archive, ARCHIVE_HEADING)]
    kept = [int(ROW_RE.match(r).group(1)) for r in _rows_after(docs.index, INDEX_HEADING)]
    assert archived and kept
    assert max(archived) < min(kept)


def test_shape_archive_holds_the_173_rows_below_400_and_the_index_none(docs) -> None:
    archived = [int(ROW_RE.match(r).group(1)) for r in _rows_after(docs.archive, ARCHIVE_HEADING)]
    kept = [int(ROW_RE.match(r).group(1)) for r in _rows_after(docs.index, INDEX_HEADING)]
    assert len(archived) == 173
    assert all(n < 400 for n in archived)
    assert all(n >= 400 for n in kept)


# --- behavior 1: the integrity tool -----------------------------------------------------------


def test_b1_roadmap_integrity_exits_zero_and_names_both_files(docs) -> None:
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "roadmap_integrity.py")],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "0 violation(s)" in out
    assert "archive PRODUCT_ARCHIVE.md: 173 ledger row(s)" in out
    m = re.search(r"(\d+) table row\(s\), (\d+) ledger row\(s\)", out)
    assert m, out[-2000:]
    # 26 at ship time (rows 400..428); later ships only append to the index.
    assert int(m.group(2)) == len(_rows_after(docs.index, INDEX_HEADING)) >= 26


def test_b1_the_tool_reports_a_violation_when_an_archived_ships_row_is_lost(tmp_path, docs) -> None:
    """Known-bad side: drop one archived row from a copy and the tool must red."""
    rows = _rows_after(docs.archive, ARCHIVE_HEADING)
    victim = next(r for r in rows if ROW_RE.match(r).group(1) == "31")
    (tmp_path / "PRODUCT.md").write_text(docs.index, encoding="utf-8")
    (tmp_path / "PRODUCT_ARCHIVE.md").write_text(
        docs.archive.replace(victim + "\n", "", 1), encoding="utf-8")
    ships = ri.shipped_iterations_from_git(ROOT)
    if ships.skip_reason is not None or 31 not in ships.iterations:
        pytest.skip(f"git cannot list ships: {ships.skip_reason}")
    union = ri.ledger_union(docs.index, (tmp_path / "PRODUCT_ARCHIVE.md").read_text(encoding="utf-8"))
    assert 31 in ri.unrecorded_ships(union, ships.iterations)


# --- behavior 2: rejoin is byte-exact ---------------------------------------------------------


def test_b2_helper_rejoin_equals_an_independent_rejoin(docs) -> None:
    mine = _independent_rejoin(docs.index, docs.archive)
    assert _roadmap.rejoined_roadmap(INDEX) == mine
    assert _roadmap.rejoin(docs.index, docs.archive) == mine
    assert POINTER_RE.pattern not in mine
    assert not any(POINTER_RE.match(line) for line in mine.split("\n"))


def test_b2_rejoined_rows_before_428_equal_the_parents_rows_in_order(docs, parent_text) -> None:
    rejoined = _independent_rejoin(docs.index, docs.archive)
    mine = [r for r in _rows_after(rejoined, INDEX_HEADING) if int(ROW_RE.match(r).group(1)) < THIS_ITER]
    theirs = _rows_after(parent_text, INDEX_HEADING)
    assert len(theirs) >= 190, "premise: the parent ledger is not vacuous"
    assert mine == theirs


def test_b2_the_rejoined_prefix_up_to_the_parents_last_row_is_the_parents_prefix(docs, parent_text) -> None:
    """Everything from the file start through the parent's last ledger row rejoins byte-exact.

    Narrower than the whole-file claim (later iterations edit the table above), so it pins
    only the ledger section: from `## Done ledger` through the parent's last row."""
    rejoined = _independent_rejoin(docs.index, docs.archive)
    last = _rows_after(parent_text, INDEX_HEADING)[-1]

    def section(text: str) -> str:
        start = text.index("\n" + INDEX_HEADING + "\n")
        end = text.index(last, start) + len(last)
        return text[start:end]

    assert section(rejoined) == section(parent_text)


# --- behavior 3: the multiset of rows ---------------------------------------------------------


def test_b3_union_multiset_is_the_parents_rows_plus_only_newer_rows(docs, parent_text) -> None:
    union = _rows_after(docs.index, INDEX_HEADING) + _rows_after(docs.archive, ARCHIVE_HEADING)
    old = collections.Counter(r for r in union if int(ROW_RE.match(r).group(1)) < THIS_ITER)
    assert old == collections.Counter(_rows_after(parent_text, INDEX_HEADING))
    assert len(union) == len(set(union)), "a row is duplicated across the two files"
    this = [r for r in union if ROW_RE.match(r).group(1) == str(THIS_ITER)]
    assert len(this) == 1, this
    assert this[0].startswith("- iter 428 row 159")


def test_b3_no_iter_line_outside_the_two_ledger_sections_was_added(docs, parent_text) -> None:
    def stray(text: str, heading: str) -> list[str]:
        lines = text.split("\n")
        return [l for l in lines[: lines.index(heading)] if l.startswith("- iter ")]

    assert stray(docs.archive, ARCHIVE_HEADING) == []
    assert stray(docs.index, INDEX_HEADING) == stray(parent_text, INDEX_HEADING)


# --- behavior 4: the 100 k brake --------------------------------------------------------------


def test_b4_product_md_is_under_the_tightened_brake(docs) -> None:
    assert m368.PRODUCT_MAX_CHARS == 100_000
    assert len(docs.index) <= 100_000


def test_b4_the_brake_still_fires_above_the_limit(tmp_path, monkeypatch) -> None:
    over = tmp_path / "PRODUCT.md"
    over.write_text("x" * 100_001, encoding="utf-8")
    monkeypatch.setattr(m368, "ROADMAP", over)
    with pytest.raises(AssertionError):
        m368.test_b8_product_md_stays_under_the_paydown_floor()
    at = tmp_path / "at.md"
    at.write_text("x" * 100_000, encoding="utf-8")
    monkeypatch.setattr(m368, "ROADMAP", at)
    m368.test_b8_product_md_stays_under_the_paydown_floor()


def test_b4_the_brake_would_have_fired_on_the_parent(parent_text) -> None:
    assert len(parent_text) > m368.PRODUCT_MAX_CHARS


# --- behavior 5: the inverted b9 pins ---------------------------------------------------------


def test_b5_archive_is_tracked_non_vacuous_and_judged_clean(docs) -> None:
    assert _roadmap.archive_rows(docs.archive)
    assert ri.archive_findings(docs.archive) == []
    assert _roadmap.ARCHIVE_NAME == ri.ARCHIVE_NAME == ARCHIVE.name
    tracked = _roadmap.git_tracks(ARCHIVE)
    if tracked is None:
        pytest.skip("git cannot say whether PRODUCT_ARCHIVE.md is tracked")
    assert tracked is True


def test_b5_both_inverted_b9_pins_fail_when_the_archive_is_absent(tmp_path, monkeypatch) -> None:
    (tmp_path / "PRODUCT.md").write_text("# no archive here\n", encoding="utf-8")
    monkeypatch.setattr(m368, "ROOT", tmp_path)
    monkeypatch.setattr(m368t, "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        m368.test_b9_the_done_ledger_archive_is_tracked_non_vacuous_and_clean()
    with pytest.raises(AssertionError):
        m368t.test_b9_the_product_archive_file_is_tracked_and_judged_clean()


def test_b5_the_tools_archive_judge_flags_a_rowless_archive(docs) -> None:
    rowless = docs.archive.split(ARCHIVE_HEADING)[0] + ARCHIVE_HEADING + "\n"
    assert ri.archive_findings(rowless) != []


# --- behavior 6: README index row -------------------------------------------------------------


def test_b6_readme_index_names_the_archive_once_with_one_provenance_value(docs) -> None:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Documents in this repo", 1)[1].split("\n## ", 1)[0]
    rows = [l for l in section.split("\n") if l.startswith("| `PRODUCT_ARCHIVE.md` |")]
    assert len(rows) == 1, rows
    provenance = [w for w in ("generated by the build loop", "hand-written") if w in rows[0]]
    assert len(provenance) == 1, rows[0]


# --- behavior 7: the shared helper ------------------------------------------------------------


def test_b7_helper_finds_the_archive_beside_a_scratch_copy(tmp_path, docs) -> None:
    copy = tmp_path / "PRODUCT.md"
    copy.write_text(docs.index, encoding="utf-8")
    assert _roadmap.rejoined_roadmap(copy) == docs.index, "no archive beside: unchanged"
    (tmp_path / "PRODUCT_ARCHIVE.md").write_text(docs.archive, encoding="utf-8")
    assert _roadmap.rejoined_roadmap(copy) == _independent_rejoin(docs.index, docs.archive)


def test_b7_helper_refuses_a_split_index_whose_pointer_is_gone(tmp_path, docs) -> None:
    broken = "\n".join(l for l in docs.index.split("\n") if not POINTER_RE.match(l))
    with pytest.raises(AssertionError):
        _roadmap.rejoin(broken, docs.archive)


def test_b7_integrity_union_covers_every_row_of_both_files(docs) -> None:
    union = ri.ledger_union(docs.index, ri.read_archive(INDEX))
    got = {n for _, n in ri.ledger_iterations(union)}
    want = {int(ROW_RE.match(r).group(1))
            for r in _rows_after(docs.index, INDEX_HEADING) + _rows_after(docs.archive, ARCHIVE_HEADING)}
    assert got == want and len(want) >= 199
