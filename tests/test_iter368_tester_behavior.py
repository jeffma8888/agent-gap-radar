"""Iteration 368, tester-side black-box checks of the roadmap notes archive.

Written from the spec's Expected Behaviors only: the shipped board rows of
``PRODUCT.md`` keep a one-line pointer and their long Notes prose lives,
verbatim, in ``docs/ROADMAP_NOTES_ARCHIVE.md``.  This module parses both files
with its own (deliberately different) readers so that a quirk shared by one
parser cannot hide a broken split: the archive is walked line by line as a
whole-file grammar, and board rows are recognised by their leading ``| N |``
cell whether or not the closing pipe is present.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "PRODUCT.md"
NOTES_ARCHIVE = ROOT / "docs" / "ROADMAP_NOTES_ARCHIVE.md"
POINTER = "Notes archived verbatim in `docs/ROADMAP_NOTES_ARCHIVE.md`."
BOARD_END = "## Non-goals for this roadmap"
TITLE = "# Roadmap notes archive"
HEADING = re.compile(r"^## Row (\d+)$")
ITERATION = re.compile(r"Iteration \d+")
ROW_START = re.compile(r"^\| (\d+) \| ")
LIMIT = 200
EXPECTED_SECTIONS = 104
# Three shipped rows lost their closing " |" before this iteration, so they are
# not ``| N | ... |`` board rows under the spec's own definition and stay
# unarchived.  They are the ONLY permitted long-notes residue.
MALFORMED_RESIDUE = {108, 109, 134}


def _text(path: pathlib.Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")


def _board_lines() -> list[str]:
    roadmap = _text(ROADMAP)
    assert roadmap.count(BOARD_END) == 1
    return [ln for ln in roadmap.split(BOARD_END, 1)[0].split("\n") if ROW_START.match(ln)]


def _parse_row(line: str) -> tuple[int, str, str, bool]:
    """Return (id, status, notes, well_formed) for one board line.

    The status cell is located by token, not by column split, so a pipe inside
    the item text cannot shift it: it is the first `` | shipped | `` /
    `` | open | `` cell after the id, and the Notes cell is everything after it.
    """
    row_id = int(ROW_START.match(line).group(1))
    well_formed = line.endswith(" |")
    match = re.search(r" \| (shipped|open) \| ", line)
    assert match is not None, f"row {row_id}: no status cell"
    notes = line[match.end():]
    if well_formed:
        notes = notes[: -len(" |")]
    return row_id, match.group(1), notes, well_formed


def _rows() -> list[tuple[int, str, str, bool]]:
    return [_parse_row(ln) for ln in _board_lines()]


def _sections() -> dict[int, str]:
    """Parse the archive as a whole-file grammar.

    title, empty, preamble paragraph(s), then repeated
    ``## Row N`` / empty / one body line / (empty | EOF).  Any stray line after
    the first heading is a failure, not something to skip.
    """
    text = _text(NOTES_ARCHIVE)
    lines = text.split("\n")
    assert lines[-1] == "", "archive must end in a newline"
    lines = lines[:-1]
    first = next(i for i, ln in enumerate(lines) if ln.startswith("## "))
    sections: dict[int, str] = {}
    i = first
    while i < len(lines):
        match = HEADING.match(lines[i])
        assert match is not None, f"line {i + 1}: expected a '## Row N' heading, got {lines[i][:80]!r}"
        row_id = int(match.group(1))
        assert row_id not in sections, f"Row {row_id} appears twice"
        assert i + 2 < len(lines), f"Row {row_id}: truncated section"
        assert lines[i + 1] == "", f"Row {row_id}: no empty line after heading"
        body = lines[i + 2]
        assert body.strip() and not HEADING.match(body), f"Row {row_id}: missing body"
        sections[row_id] = body
        nxt = i + 3
        if nxt == len(lines):
            break
        assert lines[nxt] == "", f"Row {row_id}: body spans more than one line"
        i = nxt + 1
    return sections


# --- B1 -----------------------------------------------------------------------


def test_b1_archive_is_utf8_titled_and_ends_in_exactly_one_newline() -> None:
    raw = NOTES_ARCHIVE.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    assert text.split("\n", 1)[0] == TITLE
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert b"\r" not in raw


# --- B2 -----------------------------------------------------------------------


def test_b2_archive_grammar_yields_exactly_104_unique_sections() -> None:
    sections = _sections()
    assert len(sections) == EXPECTED_SECTIONS


def test_b2_raw_heading_count_agrees_with_the_grammar_walk() -> None:
    headings = re.findall(r"^## Row (\d+)$", _text(NOTES_ARCHIVE), flags=re.MULTILINE)
    assert len(headings) == EXPECTED_SECTIONS
    assert len(set(headings)) == EXPECTED_SECTIONS
    assert {int(h) for h in headings} == set(_sections())


def test_b2_no_heading_other_than_row_headings_after_the_preamble() -> None:
    hashes = [ln for ln in _text(NOTES_ARCHIVE).split("\n") if ln.startswith("#")]
    assert hashes[0] == TITLE
    assert all(HEADING.match(ln) for ln in hashes[1:]), [ln for ln in hashes[1:] if not HEADING.match(ln)]


# --- B3 -----------------------------------------------------------------------


def test_b3_archived_ids_equal_shipped_pointer_rows() -> None:
    pointer_ids = {rid for rid, status, notes, _ in _rows() if status == "shipped" and notes.endswith(POINTER)}
    assert pointer_ids == set(_sections())


def test_b3_every_pointer_row_is_a_well_formed_shipped_row() -> None:
    bad = [rid for rid, status, notes, ok in _rows() if POINTER in notes and (status != "shipped" or not ok)]
    assert bad == []


def test_b3_board_row_ids_are_unique() -> None:
    ids = [rid for rid, *_ in _rows()]
    assert len(ids) == len(set(ids))


def test_b3_pointer_sentence_appears_once_per_pointer_row_and_nowhere_else() -> None:
    roadmap = _text(ROADMAP)
    assert roadmap.count(POINTER) == EXPECTED_SECTIONS
    for rid, _, notes, _ in _rows():
        assert notes.count(POINTER) <= 1, rid


# --- B4 -----------------------------------------------------------------------


def test_b4_every_stub_is_first_iteration_token_or_bare_pointer() -> None:
    sections = _sections()
    wrong: list[tuple[int, str, str]] = []
    for rid, status, notes, _ in _rows():
        if rid not in sections:
            continue
        found = ITERATION.search(sections[rid])
        expected = POINTER if found is None else f"{found.group(0)}. {POINTER}"
        if notes != expected:
            wrong.append((rid, notes, expected))
    assert wrong == []


def test_b4_both_stub_forms_are_exercised() -> None:
    sections = _sections()
    bare = [rid for rid, body in sections.items() if ITERATION.search(body) is None]
    tagged = [rid for rid, body in sections.items() if ITERATION.search(body) is not None]
    assert tagged, "no tagged stub: the Iteration-token arm is untested"
    notes = {rid: n for rid, _, n, _ in _rows()}
    for rid in bare:
        assert notes[rid] == POINTER
    for rid in tagged:
        assert notes[rid].startswith("Iteration ") and notes[rid].endswith(". " + POINTER)


# --- B5 -----------------------------------------------------------------------


def test_b5_every_body_is_long_and_never_double_archived() -> None:
    short = {rid: len(b) for rid, b in _sections().items() if len(b) <= LIMIT}
    doubled = [rid for rid, b in _sections().items() if POINTER in b or "ROADMAP_NOTES_ARCHIVE" in b]
    assert short == {}
    assert doubled == []


def test_b5_bodies_are_bare_cell_text_without_table_pipes_at_the_edges() -> None:
    edged = [rid for rid, b in _sections().items() if b.endswith(" |") or b.startswith("| ") or b != b.strip()]
    assert edged == []


# --- B6 -----------------------------------------------------------------------


def test_b6_open_rows_never_point_at_the_archive() -> None:
    rows = _rows()
    open_rows = [r for r in rows if r[1] == "open"]
    assert open_rows, "no open row found: the parser is not seeing the board"
    assert [rid for rid, _, notes, _ in open_rows if POINTER in notes] == []
    assert not {rid for rid, *_ in open_rows} & set(_sections())


# --- B7 -----------------------------------------------------------------------


def test_b7_well_formed_unarchived_shipped_rows_have_short_notes() -> None:
    long_rows = {
        rid: len(notes)
        for rid, status, notes, ok in _rows()
        if ok and status == "shipped" and not notes.endswith(POINTER) and len(notes) > LIMIT
    }
    assert long_rows == {}


def test_b7_any_long_unarchived_shipped_line_is_only_the_known_malformed_residue() -> None:
    residue = {
        rid
        for rid, status, notes, ok in _rows()
        if status == "shipped" and not notes.endswith(POINTER) and len(notes) > LIMIT
    }
    assert residue <= MALFORMED_RESIDUE
    assert all(not ok for rid, _, _, ok in _rows() if rid in residue)


# --- B8 -----------------------------------------------------------------------


def test_b8_product_md_is_at_most_240000_chars() -> None:
    assert len(_text(ROADMAP)) <= 240_000


# --- B9 -----------------------------------------------------------------------


def test_b9_roadmap_integrity_tool_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "roadmap_integrity.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "0 violation(s)" in proc.stdout + proc.stderr


def test_b9_no_product_archive_file_at_repo_root() -> None:
    assert not (ROOT / "PRODUCT_ARCHIVE.md").exists()


# --- B10 / B11 ----------------------------------------------------------------


def test_b10_exactly_one_iteration_368_done_row() -> None:
    hits = [ln for ln in _text(ROADMAP).split("\n") if ln.startswith("- iter 368 ")]
    assert len(hits) == 1


def test_b11_some_shipped_row_still_names_iteration_74() -> None:
    assert any(status == "shipped" and "Iteration 74" in ln for ln, (_, status, _, _) in zip(_board_lines(), _rows()))
