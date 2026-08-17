"""Iteration 09 behaviors: the two tables `radar report` renders are exactly the two
halves of `confidence(g) < floor`, derived from the register at every floor in `0..7`.

Iteration 08 proved every register id appears in the report EXACTLY ONCE. That census
cannot prove an id appears in the RIGHT section: a record rendered into the ranked table
while it belongs below the floor still appears exactly once, and iteration 08 still
passes. The claim `VISION.md` protects by name -- a below-floor record is DISPLAYED,
never silently dropped -- is therefore asserted here, and asserted as an ORACLE over
`confidence()` rather than as a list of ids, because this register grows on a schedule:
a literal id census reds the suite on new DATA while the renderer it claims to test is
untouched, and it reds naming a file under `gaps/`, which reads as a broken register
rather than as a fragile test.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion either runs
`agent_gap_radar.cli.main` and observes only its exit code, stdout and stderr, or calls
the public library API the spec names (`registry.load_all`, `scoring.confidence`).

Five habits kept on purpose:

* NO gap id literal appears in any expectation. The only id this file ever names is one
  it DERIVES at runtime, and it names it only inside a failure message it expects to see;
* no column index is a literal either -- the id and `Needs` columns are looked up in the
  table's own header row, and every data row is asserted to have the header's width, so a
  pipe inside a rendered Title fails loudly instead of silently shifting a cell;
* non-vacuity is asserted over the SWEEP rather than per floor, because at floors 0 and 1
  the below-floor half of this register is legitimately empty and `set() == set()` is the
  green that means nothing. One test proves some floor splits the register into two
  non-empty halves, so the partition claim is not trivially satisfied everywhere;
* the section parser asserts headings are UNIQUE, because a dict keeps only the LAST
  section with a given heading: a document rendering two below-floor tables would leave
  one of them unexamined while every assertion here still passed;
* the behavior-3 assertion is proven ARMED, not assumed: the same helper the real test
  calls is re-run with the seam that supplies the rendered below-floor rows monkeypatched
  to drop one row, and must then fail naming the dropped id. The wrapper records that it
  was reached and which id it dropped, so a seam that no longer exists fails loudly
  instead of arming nothing.
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import confidence

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: The spec's sweep is `0..7` INCLUSIVE. `range(7)` stops at 6 and silently drops two
#: floors, including the one where the ranked half first empties; `test_b0` pins the ends.
FLOORS = tuple(range(8))

RANKED_HEADING = "Ranked gaps"
BELOW_HEADING = "Below confidence floor"
ID_COLUMN = "ID"
NEEDS_COLUMN = "Needs"

#: Emitted by a section whose half of the partition is empty; there is no table at all.
EMPTY_MARKER = "None found."

#: Floor the spec measured behavior 6's anti-vacuity premise over.
ANTI_VACUITY_FLOOR = 5

ID_PATTERN = re.compile(r"^GAP-\d+$")

#: The seam behavior 5 arms. A dotted path, so a rename fails with a message that says
#: exactly which binding to re-point rather than arming nothing.
SEAM_MODULE = "agent_gap_radar.render"
SEAM_NAME = "below_floor"

REGISTER = load_all(GAPS_DIR)


# ---------------------------------------------------------------------------
# oracle -- the register's own answer, read from `confidence()`
# ---------------------------------------------------------------------------

def _below_floor_ids(floor: int) -> set[str]:
    return {gap.id for gap in REGISTER if confidence(gap) < floor}


def _ranked_ids(floor: int) -> set[str]:
    return {gap.id for gap in REGISTER if confidence(gap) >= floor}


# ---------------------------------------------------------------------------
# document plumbing -- run the product, parse only what it publishes
# ---------------------------------------------------------------------------

def _report(capsys, floor: int) -> str:
    assert main(["report", str(REPO_ROOT), "--floor", str(floor)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    document = captured.out
    assert document.startswith("# Agent infrastructure gap radar"), document[:80]
    assert document.endswith("\n") and not document.endswith("\n\n"), repr(document[-4:])
    return document


def _sections(document: str) -> dict[str, str]:
    """`## Heading` -> body, so no heading this iteration is not about gets named.

    Headings are asserted UNIQUE. A dict silently keeps only the LAST section carrying a
    given heading, so a document that rendered two `## Below confidence floor` tables
    would have one of them go unexamined while every assertion below still passed -- a
    fail-open in the direction a reader scores as success.
    """
    sections: dict[str, str] = {}
    seen: list[str] = []
    heading, body = None, []
    for line in document.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections[heading] = "\n".join(body)
            heading, body = line[3:].strip(), []
            seen.append(heading)
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections[heading] = "\n".join(body)
    duplicates = sorted({name for name in seen if seen.count(name) > 1})
    assert not duplicates, (
        f"a heading is rendered twice, so only the last section survives the parse and "
        f"one table would go unexamined: {duplicates}")
    return sections


def _table(document: str, heading: str, floor: int) -> tuple[list[str], list[list[str]]]:
    """(header cells, data rows) of `heading`'s table; ([], []) when the half is empty."""
    sections = _sections(document)
    assert heading in sections, f"floor {floor}: no '## {heading}' section: {sorted(sections)}"
    body = sections[heading]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in body.splitlines() if line.strip().startswith("|")]
    if not rows:
        assert EMPTY_MARKER in body, (
            f"floor {floor}: section {heading!r} renders neither a table nor "
            f"{EMPTY_MARKER!r}, so a record could be missing without a trace: {body!r}")
        return [], []
    assert len(rows) >= 2, f"floor {floor}: {heading!r} table has no separator row: {rows}"
    assert set(rows[1]) == {"---"}, (
        f"floor {floor}: {heading!r} row 2 is not a separator: {rows[1]}")
    header, data = rows[0], rows[2:]
    for row in data:
        assert len(row) == len(header), (
            f"floor {floor}: {heading!r} row has {len(row)} cells, header has "
            f"{len(header)} -- a rendered cell contains a pipe: {row}")
    return header, data


def _rendered_ids(document: str, heading: str, floor: int) -> list[str]:
    header, data = _table(document, heading, floor)
    if not header:
        return []
    assert ID_COLUMN in header, f"floor {floor}: {heading!r} header has no id column: {header}"
    column = header.index(ID_COLUMN)
    ids = [row[column] for row in data]
    for value in ids:
        assert ID_PATTERN.match(value), (
            f"floor {floor}: {heading!r} id column holds {value!r}, not a gap id")
    return ids


# ---------------------------------------------------------------------------
# behavior 0 -- the derived expectations are not vacuous
# ---------------------------------------------------------------------------

def test_b0_the_sweep_covers_0_to_7_and_splits_the_register_both_ways():
    """A green result over an empty domain is the failure that looks like health."""
    assert FLOORS == (0, 1, 2, 3, 4, 5, 6, 7), FLOORS
    assert len(REGISTER) >= 2, f"register too small to partition: {len(REGISTER)}"
    ids = [gap.id for gap in REGISTER]
    assert len(set(ids)) == len(ids), "duplicate id in the register"
    below = {floor: len(_below_floor_ids(floor)) for floor in FLOORS}
    ranked = {floor: len(_ranked_ids(floor)) for floor in FLOORS}
    assert any(below.values()), f"no floor puts any record below it: {below}"
    assert any(ranked.values()), f"no floor keeps any record: {ranked}"
    both = [floor for floor in FLOORS if below[floor] and ranked[floor]]
    assert both, (
        f"no floor splits the register into two non-empty halves, so the partition "
        f"claim is trivially satisfied at every floor: below={below}")


def test_b0_the_section_parser_refuses_a_document_with_a_duplicate_heading(capsys):
    """Two-sided proof of the guard above: a guard nobody proves fires is decoration.

    Must FIRE on a planted document that renders the below-floor heading twice, and must
    NOT fire on what the product actually publishes. Without the first half, the parser
    could silently keep one section of two and every table assertion here would still be
    green; without the second half, the guard could be reddening real documents.
    """
    planted = (f"# planted\n\n## {BELOW_HEADING}\n\nfirst\n\n"
               f"## {RANKED_HEADING}\n\nsecond\n\n## {BELOW_HEADING}\n\nthird\n")
    with pytest.raises(AssertionError) as failure:
        _sections(planted)
    assert BELOW_HEADING in str(failure.value), str(failure.value)

    published = _sections(_report(capsys, ANTI_VACUITY_FLOOR))
    assert BELOW_HEADING in published and RANKED_HEADING in published, sorted(published)


# ---------------------------------------------------------------------------
# behavior 3 -- the below-floor table IS the sub-floor half of the register
# ---------------------------------------------------------------------------

def _assert_below_floor_table_is_the_oracle(floor: int, capsys) -> set[str]:
    """Behavior 3, factored out so behavior 5 can arm this exact assertion."""
    rendered = _rendered_ids(_report(capsys, floor), BELOW_HEADING, floor)
    assert len(set(rendered)) == len(rendered), (
        f"floor {floor}: an id is rendered twice below the floor: {rendered}")
    expected = _below_floor_ids(floor)
    missing = sorted(expected - set(rendered))
    unexpected = sorted(set(rendered) - expected)
    assert set(rendered) == expected, (
        f"floor {floor}: the below-floor table disagrees with the confidence oracle -- "
        f"missing {missing}, unexpected {unexpected}")
    return set(rendered)


@pytest.mark.parametrize("floor", FLOORS)
def test_b3_below_floor_table_is_exactly_the_records_under_the_floor(floor, capsys):
    _assert_below_floor_table_is_the_oracle(floor, capsys)


# ---------------------------------------------------------------------------
# behavior 4 -- the ranked table is the other half, and the halves partition
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", FLOORS)
def test_b4_ranked_table_is_the_other_half_and_the_two_are_a_partition(floor, capsys):
    document = _report(capsys, floor)
    ranked = _rendered_ids(document, RANKED_HEADING, floor)
    below = _rendered_ids(document, BELOW_HEADING, floor)
    assert len(set(ranked)) == len(ranked), (
        f"floor {floor}: an id is rendered twice in the ranked table: {ranked}")
    expected = _ranked_ids(floor)
    assert set(ranked) == expected, (
        f"floor {floor}: the ranked table disagrees with the confidence oracle -- "
        f"missing {sorted(expected - set(ranked))}, "
        f"unexpected {sorted(set(ranked) - expected)}")
    overlap = set(ranked) & set(below)
    assert not overlap, f"floor {floor}: id rendered in BOTH tables: {sorted(overlap)}"
    whole = {gap.id for gap in REGISTER}
    assert set(ranked) | set(below) == whole, (
        f"floor {floor}: a record is in neither table: "
        f"{sorted(whole - set(ranked) - set(below))}")
    assert len(ranked) + len(below) == len(REGISTER), (
        f"floor {floor}: {len(ranked)} + {len(below)} != {len(REGISTER)}")


@pytest.mark.parametrize("floor", FLOORS)
def test_b4_the_header_census_agrees_with_the_two_rendered_tables(floor, capsys):
    """The document's own count line is derived from the same partition it introduces."""
    document = _report(capsys, floor)
    ranked = _rendered_ids(document, RANKED_HEADING, floor)
    below = _rendered_ids(document, BELOW_HEADING, floor)
    line = [row for row in document.splitlines() if row.startswith("Records:")]
    assert len(line) == 1, f"floor {floor}: expected one census line, got {line}"
    found = re.match(
        r"^Records: (\d+) \| ranked: (\d+) \| below confidence floor \((\d+)\): (\d+)$",
        line[0])
    assert found, f"floor {floor}: census line not parsed: {line[0]!r}"
    total, said_ranked, said_floor, said_below = (int(g) for g in found.groups())
    assert said_floor == floor, f"the document echoes floor {said_floor}, asked for {floor}"
    assert total == len(REGISTER), (total, len(REGISTER))
    assert said_ranked == len(ranked), (said_ranked, ranked)
    assert said_below == len(below), (said_below, below)


# ---------------------------------------------------------------------------
# behavior 5 -- behavior 3 is ARMED: a dropped row fails and names the id
# ---------------------------------------------------------------------------

def _floor_with_at_least_two_records_below_it() -> int:
    for floor in FLOORS:
        if len(_below_floor_ids(floor)) >= 2:
            return floor
    raise AssertionError(
        "no floor in the sweep puts two records below it, so a dropped row cannot be "
        "distinguished from an emptied table")


def test_b5_dropping_one_rendered_row_fails_behavior_3_and_names_the_id(monkeypatch, capsys):
    floor = _floor_with_at_least_two_records_below_it()
    assert len(_assert_below_floor_table_is_the_oracle(floor, capsys)) >= 2

    module = importlib.import_module(SEAM_MODULE)
    real = getattr(module, SEAM_NAME, None)
    assert callable(real), (
        f"{SEAM_MODULE}.{SEAM_NAME} is not the seam that supplies the rendered "
        f"below-floor rows any more; re-point SEAM_MODULE/SEAM_NAME or this test arms "
        f"nothing")

    reached: list[int] = []
    dropped: list[str] = []

    def dropping_one(*args, **kwargs):
        rows = list(real(*args, **kwargs))
        reached.append(len(rows))
        if rows:
            dropped.append(rows[0][0].id)
            return rows[1:]
        return rows

    monkeypatch.setattr(f"{SEAM_MODULE}.{SEAM_NAME}", dropping_one)
    with pytest.raises(AssertionError) as failure:
        _assert_below_floor_table_is_the_oracle(floor, capsys)
    message = str(failure.value)
    assert reached, "the seam wrapper was never reached, so this proves nothing"
    assert dropped, f"the wrapper dropped no row; it saw row counts {reached}"
    assert f"floor {floor}" in message, message
    assert dropped[0] in message, (
        f"the failure does not name the dropped id {dropped[0]}: {message}")


def test_b5_the_unpatched_assertion_passes_at_the_same_floor(capsys):
    """The known-bad above must be caused by the dropped row, not by a broken helper."""
    floor = _floor_with_at_least_two_records_below_it()
    assert _assert_below_floor_table_is_the_oracle(floor, capsys) == _below_floor_ids(floor)


# ---------------------------------------------------------------------------
# behavior 6 -- the anti-vacuity claim the deleted id literal used to carry
# ---------------------------------------------------------------------------

def _needs_cells(document: str, floor: int) -> dict[str, str]:
    header, data = _table(document, BELOW_HEADING, floor)
    if not header:
        return {}
    assert header[-1] == NEEDS_COLUMN, f"floor {floor}: last column is not Needs: {header}"
    return {row[header.index(ID_COLUMN)]: row[header.index(NEEDS_COLUMN)] for row in data}


def test_b6_the_below_floor_table_holds_two_rows_with_two_distinct_needs(capsys):
    """Derived form of the deleted `sorted(cells) == [two ids]`: no id is named.

    Stands down loudly rather than reddening the suite if a research pass promotes the
    register past this premise -- the durable claims are behaviors 3, 4 and the
    every-floor cell test below, all of which derive their expectations from the register.
    """
    cells = _needs_cells(_report(capsys, ANTI_VACUITY_FLOOR), ANTI_VACUITY_FLOOR)
    if len(cells) < 2:
        pytest.skip(
            f"the register now puts {len(cells)} record(s) below floor "
            f"{ANTI_VACUITY_FLOOR}; the anti-vacuity premise this test needs is gone")
    assert set(cells) == _below_floor_ids(ANTI_VACUITY_FLOOR), cells
    assert len(cells) >= 2, cells
    assert len(set(cells.values())) >= 2, (
        f"every below-floor record at floor {ANTI_VACUITY_FLOOR} got the same cell, so a "
        f"template sentence would satisfy this: {cells}")


@pytest.mark.parametrize("floor", FLOORS)
def test_b6_every_rendered_below_floor_row_carries_a_non_empty_needs_cell(floor, capsys):
    cells = _needs_cells(_report(capsys, floor), floor)
    assert set(cells) == _below_floor_ids(floor), (floor, sorted(cells))
    for gap_id, cell in cells.items():
        assert cell, f"floor {floor}: {gap_id} rendered an empty Needs cell"
