"""Iteration 368 behaviors: shipped rows' long Notes live in a verbatim archive.

The roadmap index (``PRODUCT.md``) is read by every stage of the loop under a
hard time cap, so the narrative of rows that already shipped moved one hop away
to ``docs/ROADMAP_NOTES_ARCHIVE.md``.  These nodes keep that split honest: the
archive's shape is fixed, the set of archived rows and the set of pointer rows
are the same set, and a pointer stub can only say what the archived body says
(its first ``Iteration NN`` token), so the move can never silently drop or
invent history.

Everything is read in-process with ``pathlib``; no subprocess, no git, no
frozen sha -- the losslessness round-trip against HEAD is a review-time check.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "PRODUCT.md"
ARCHIVE = ROOT / "docs" / "ROADMAP_NOTES_ARCHIVE.md"
POINTER = "Notes archived verbatim in `docs/ROADMAP_NOTES_ARCHIVE.md`."
BOARD_END = "## Non-goals for this roadmap"
HEADING_RE = re.compile(r"^## Row (\d+)$")
ITERATION_RE = re.compile(r"Iteration \d+")
ROW_RE = re.compile(r"^\| (\d+) \| .* \|$")
SHORT_NOTES_MAX = 200
PRODUCT_MAX_CHARS = 240_000


def _board_rows() -> dict[int, tuple[str, str]]:
    """Map board row id -> (status, notes) for table lines above the non-goals heading.

    A board row is a ``| N | ... |`` line, exactly as the spec defines it: three
    shipped rows (108, 109, 134) have lacked the closing `` |`` since before this
    iteration, so they are not well-formed table rows and the archiver left them
    in place.  Split at most three times so a Notes cell that itself contains ``" | "``
    stays one cell; the status cell is the third column.
    """
    text = ROADMAP.read_text(encoding="utf-8")
    board = text.split(BOARD_END, 1)[0]
    rows: dict[int, tuple[str, str]] = {}
    for line in board.splitlines():
        match = ROW_RE.match(line)
        if match is None:
            continue
        cells = line[2:].removesuffix(" |").split(" | ", 3)
        assert len(cells) == 4, line[:120]
        row_id = int(match.group(1))
        assert row_id not in rows, f"duplicate board row {row_id}"
        rows[row_id] = (cells[2], cells[3])
    return rows


def _archive_sections() -> dict[int, str]:
    """Map archived row id -> verbatim Notes body, enforcing the section shape (B2)."""
    lines = ARCHIVE.read_text(encoding="utf-8").split("\n")
    sections: dict[int, str] = {}
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match is None:
            continue
        row_id = int(match.group(1))
        assert row_id not in sections, f"duplicate archive heading Row {row_id}"
        assert lines[index + 1] == "", f"Row {row_id}: heading not followed by one empty line"
        body = lines[index + 2]
        assert body.strip(), f"Row {row_id}: body line is empty"
        following = index + 3
        assert following >= len(lines) or lines[following] == "", (
            f"Row {row_id}: body is more than one line"
        )
        sections[row_id] = body
    return sections


def _pointer_rows() -> dict[int, tuple[str, str]]:
    """Board rows whose Notes cell ends with the archive pointer sentence."""
    return {k: v for k, v in _board_rows().items() if v[1].endswith(POINTER)}


def test_b1_archive_exists_with_title_and_one_trailing_newline() -> None:
    raw = ARCHIVE.read_bytes()
    text = raw.decode("utf-8")
    assert text.split("\n", 1)[0] == "# Roadmap notes archive"
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_b2_archive_has_104_unique_well_formed_sections() -> None:
    sections = _archive_sections()
    assert len(sections) == 104
    headings = [
        ln for ln in ARCHIVE.read_text(encoding="utf-8").splitlines() if HEADING_RE.match(ln)
    ]
    assert len(headings) == len(set(headings)) == 104


def test_b3_archive_rows_equal_shipped_pointer_rows() -> None:
    pointer = _pointer_rows()
    assert all(status == "shipped" for status, _ in pointer.values())
    assert set(_archive_sections()) == set(pointer)


@pytest.mark.parametrize("row_id", sorted(_archive_sections()))
def test_b4_stub_is_first_iteration_token_or_bare_pointer(row_id: int) -> None:
    notes = _pointer_rows()[row_id][1]
    first = ITERATION_RE.search(_archive_sections()[row_id])
    expected = f"{first.group(0)}. {POINTER}" if first else POINTER
    assert notes == expected


@pytest.mark.parametrize("row_id", sorted(_archive_sections()))
def test_b5_archived_body_is_long_and_never_double_archived(row_id: int) -> None:
    body = _archive_sections()[row_id]
    assert len(body) > SHORT_NOTES_MAX
    assert POINTER not in body


def test_b6_no_open_row_carries_the_pointer() -> None:
    offenders = [k for k, (status, notes) in _board_rows().items() if status != "shipped" and POINTER in notes]
    assert offenders == []


def test_b7_unarchived_shipped_rows_have_short_notes() -> None:
    long_rows = [
        k
        for k, (status, notes) in _board_rows().items()
        if status == "shipped" and not notes.endswith(POINTER) and len(notes) > SHORT_NOTES_MAX
    ]
    assert long_rows == []


def test_b8_product_md_stays_under_the_paydown_floor() -> None:
    assert len(ROADMAP.read_text(encoding="utf-8")) <= PRODUCT_MAX_CHARS


def test_b9_no_vacuous_product_archive_at_repo_root() -> None:
    assert not (ROOT / "PRODUCT_ARCHIVE.md").exists()


def test_b10_exactly_one_iter_368_ledger_line() -> None:
    lines = ROADMAP.read_text(encoding="utf-8").splitlines()
    assert sum(1 for ln in lines if ln.startswith("- iter 368 ")) == 1


def test_b11_a_shipped_row_still_names_iteration_74() -> None:
    rows = [ln for ln in ROADMAP.read_text(encoding="utf-8").splitlines() if "| shipped |" in ln]
    assert any("Iteration 74" in ln for ln in rows)
