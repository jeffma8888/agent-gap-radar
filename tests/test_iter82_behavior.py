"""Iteration 82 behaviors: the roadmap's ship-order pointer may name only `open` rows.

`PRODUCT.md`'s `**Next up:**` paragraph is this repo's only statement of ship order -- the
line a PM lead reads to choose the next row -- and nothing read it, so it drifted until it
named rows the table's own Status column reports `shipped` as forward candidates. Wrong there
does not mislead a reader, it mis-steers a build. This iteration turns the pointer into a
checked artifact: `tools/roadmap_integrity.ship_order_violations` DERIVES the requirement from
the Status column, so the commit that flips a named row to `shipped` must rewrite the pointer
too, exactly as it must record itself in the roadmap's Done section.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source (`src/`, `tools/*.py` text), the engineer's or the reviewer's notes,
`IMPLEMENTATION.patch`, or any diff. Every expectation comes from `pm.md`'s Expected
Behaviors; every value is measured by CALLING the public `tools/roadmap_integrity` interface
or by RUNNING the tool at the process boundary, over the committed `PRODUCT.md` or over a
fixture derived from it under pytest's `tmp_path`.

Structural notes, so this file cannot lie later:

* **The clean verdict is proved two-sided.** `ship_order_violations` returning `[]` over the
  committed roadmap is evidence only because the SAME function is shown to fire on three
  distinct planted defects -- a `shipped` row named, a missing pointer, and a pointer naming
  no row at all. A brake that cannot fire reports a document it never examined.
* **The row sweep is measured by DERIVED EQUALITY against an independent extractor written
  here**, so a sweep that quietly stopped seeing `and` / `,` / `/` groupings -- the exact
  omission `pm.md` records a prior sweep making -- cannot pass by agreeing with itself.
* **Every mutated fixture asserts its own premise**, so a no-op `replace` cannot turn a
  known-bad document into a copy of the known-good one and pass while measuring nothing.
* **No literal row id is written down as an expectation.** The `open` and `shipped` ids the
  fixtures use are read from the table's Status column at run time, so a later iteration
  flipping any row's status cannot make a fixture silently stop discriminating.
* **No absolute machine path and no personal or employer identifier appears here**; the repo
  root is derived from `__file__` and every fixture is written under pytest's `tmp_path`.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"
TOOL = REPO_ROOT / "tools" / "roadmap_integrity.py"

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402


# ---------------------------------------------------------------------------
# an INDEPENDENT reader of the pointer's row ids, so the sweep is not its own oracle
# ---------------------------------------------------------------------------

#: `row 51`, `rows 64 and 70`, `rows 1, 2 and 3`, `rows 1/2` -- an integer after `row`/`rows`
#: plus any run of `,` / `/` / `and` continuations. Written from `pm.md`'s statement that the
#: brake must extract a GROUP of integers rather than a single one, NOT from the tool's code.
_ROW_GROUP = re.compile(
    r"\brows?\s+(\d+(?:\s*(?:,|/|and)\s*\d+)*)",
    re.IGNORECASE,
)


#: An inline code span. Its contents are identifiers -- a path, a commit sha, a verb -- so
#: they are exempt from the restated-figure sweep below.
_CODE_SPAN = re.compile(r"`[^`]*`")


def _lines_opening_with_the_label(text: str) -> int:
    """How many LINES open with the pointer label.

    A substring count is the wrong measurement: the committed roadmap mentions the label a
    second time inside a prose bullet, and the pointer is the line that OPENS with it.
    """
    return sum(1 for line in text.splitlines() if line.startswith(ri.SHIP_ORDER_LABEL))


def _rows_named_independently(paragraph: str) -> list[str]:
    """Row ids named in `paragraph`, in order of appearance, duplicates kept."""
    found: list[str] = []
    for match in _ROW_GROUP.finditer(paragraph):
        found.extend(re.findall(r"\d+", match.group(1)))
    return found


# ---------------------------------------------------------------------------
# fixtures, all derived from the committed document
# ---------------------------------------------------------------------------

def _live() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _pointer(text: str) -> str:
    """The committed pointer paragraph, asserted present -- every fixture mutates it."""
    paragraph = ri.ship_order_paragraph(text)
    assert paragraph, (
        f"premise broken: the roadmap carries no {ri.SHIP_ORDER_LABEL} paragraph, so every "
        f"fixture below would be built from nothing")
    return paragraph


def _replace_pointer(text: str, replacement: str) -> str:
    """Swap the pointer paragraph for `replacement`, asserting the edit was not a no-op."""
    paragraph = _pointer(text)
    assert text.count(paragraph) == 1, (
        "premise broken: the pointer paragraph occurs more than once, so a single replace "
        "would leave a second copy behind")
    mutated = text.replace(paragraph, replacement, 1)
    assert mutated != text, "premise broken: the mutation was a no-op"
    return mutated


def _ids_by_status(text: str, status: str) -> list[str]:
    """Table row ids carrying `status`, ascending, read from the Status column at run time."""
    statuses = ri.row_statuses(text)
    assert statuses, "premise broken: no table rows parsed, so status selection is vacuous"
    return sorted((row for row, value in statuses.items() if value == status), key=int)


def _an_open_id(text: str) -> str:
    ids = _ids_by_status(text, "open")
    assert ids, "premise broken: the table carries no `open` row to build a clean fixture from"
    return ids[0]


def _a_shipped_id(text: str) -> str:
    ids = _ids_by_status(text, "shipped")
    assert ids, "premise broken: the table carries no `shipped` row, so nothing can offend"
    return ids[0]


def _as_file(tmp_path: pathlib.Path, text: str, name: str) -> pathlib.Path:
    path = tmp_path / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _run_tool(argv: list[str]) -> subprocess.CompletedProcess:
    """The tool at the PROCESS boundary, which is the surface a ship gate actually runs."""
    return subprocess.run([sys.executable, str(TOOL), *argv], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, timeout=180)


def _count_line(stdout: str) -> str:
    lines = [line for line in stdout.splitlines() if line.strip().endswith("violation(s)")]
    assert len(lines) == 1, f"expected exactly one count line, got {lines} in {stdout!r}"
    return lines[0].strip()


# ---------------------------------------------------------------------------
# Behavior 1: the check exists, returns message strings, and is silent on the committed doc
# ---------------------------------------------------------------------------

def test_iter82_b1_ship_order_check_is_silent_over_the_committed_roadmap() -> None:
    """Behavior 1. `ship_order_violations(text)` returns a list of message strings, and over
    the committed `PRODUCT.md` that list is empty.

    Silence here is only evidence because `test_iter82_b2_*`, `..._b3_*` and `..._b4_*` show
    the same function firing on planted defects.
    """
    violations = ri.ship_order_violations(_live())
    assert isinstance(violations, list), f"expected a list, got {type(violations)!r}"
    assert violations == [], "; ".join(str(v) for v in violations)


def test_iter82_b1_every_message_is_a_string_when_the_check_fires() -> None:
    """Behavior 1's type claim, asserted where it is observable: a clean run yields an empty
    list, which is a list of anything at all."""
    text = _live()
    offending = _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} row {_a_shipped_id(text)}.")
    violations = ri.ship_order_violations(offending)
    assert violations, "premise broken: the planted defect produced no violation"
    non_strings = [v for v in violations if not isinstance(v, str)]
    assert non_strings == [], f"non-string violation(s): {non_strings!r}"


# ---------------------------------------------------------------------------
# Behavior 2: a pointer naming a `shipped` row yields exactly one violation naming it
# ---------------------------------------------------------------------------

def test_iter82_b2_a_pointer_naming_a_shipped_row_yields_exactly_one_named_violation() -> None:
    """Behavior 2. The defect this iteration exists to refuse."""
    text = _live()
    shipped = _a_shipped_id(text)
    assert shipped not in ri.ship_order_rows(text), (
        f"premise broken: row {shipped} is already named by the committed pointer, so this "
        f"fixture cannot show the check reacting to the mutation")

    offending = _replace_pointer(
        text, f"{ri.SHIP_ORDER_LABEL} the strongest remaining candidate is row {shipped}.")
    assert ri.ship_order_rows(offending) == [shipped], (
        f"premise broken: the mutated pointer names {ri.ship_order_rows(offending)}, not "
        f"exactly [{shipped!r}]")

    violations = ri.ship_order_violations(offending)
    assert len(violations) == 1, f"expected exactly one violation, got {violations}"
    assert re.search(rf"\b{re.escape(shipped)}\b", violations[0]), (
        f"the violation does not name row {shipped}, so a reader cannot locate it: "
        f"{violations[0]!r}")


@pytest.mark.parametrize("template, label", [
    ("{label} rows {open_id} and {shipped_id} are next.", "`and` grouping"),
    ("{label} rows {open_id}, {shipped_id} are next.", "comma grouping"),
    ("{label} rows {open_id}/{shipped_id} are next.", "slash grouping"),
    ("{label} rows {open_id}, {shipped_id} and {open_id}.", "comma plus `and` grouping"),
    ("{label} row {open_id} leads; row {shipped_id} follows.", "two separate `row` phrases"),
    ("{label} Rows {open_id} and {shipped_id}.", "capitalised `Rows`"),
])
def test_iter82_b2_the_row_sweep_sees_a_shipped_id_inside_every_grouping(
        template: str, label: str) -> None:
    """Behavior 2's reachability half.

    `pm.md` records a prior sweep that found five of the seven ids the pointer named because
    it read a single integer after `row` rather than a GROUP -- it missed the ids hidden
    behind `and` and `/`. A sweep with that omission reports a clean pointer while a
    `shipped` row sits in it, which is the fail-open this brake exists to remove. So each
    grouping form is planted with a `shipped` id inside it and must produce a violation
    naming that id.
    """
    text = _live()
    open_id, shipped = _an_open_id(text), _a_shipped_id(text)
    offending = _replace_pointer(text, template.format(
        label=ri.SHIP_ORDER_LABEL, open_id=open_id, shipped_id=shipped))

    assert shipped in ri.ship_order_rows(offending), (
        f"{label}: the sweep did not see row {shipped}; it read "
        f"{ri.ship_order_rows(offending)}")
    violations = ri.ship_order_violations(offending)
    assert len(violations) == 1, f"{label}: expected exactly one violation, got {violations}"
    assert re.search(rf"\b{re.escape(shipped)}\b", violations[0]), (
        f"{label}: {violations[0]!r} does not name row {shipped}")


def test_iter82_b2_naming_only_open_rows_stays_silent_in_the_same_grouping() -> None:
    """Behavior 2's control: the grouping is not what makes the check fire, the STATUS is.

    Without this, every assertion above is satisfied by a check that fires on any pointer
    carrying two row ids.
    """
    text = _live()
    open_ids = _ids_by_status(text, "open")
    assert len(open_ids) >= 2, (
        f"premise broken: only {len(open_ids)} `open` row(s), so a two-id clean fixture "
        f"cannot be built")
    first, second = open_ids[0], open_ids[1]
    clean = _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} rows {first} and {second} lead.")
    assert ri.ship_order_rows(clean) == [first, second], ri.ship_order_rows(clean)
    assert ri.ship_order_violations(clean) == [], ri.ship_order_violations(clean)


# ---------------------------------------------------------------------------
# Behaviors 3 and 4: a brake that passes over an empty parse is the vacuous success
# ---------------------------------------------------------------------------

def test_iter82_b3_a_roadmap_with_no_pointer_yields_exactly_one_violation() -> None:
    """Behavior 3. Deleting the paragraph must not silence the check.

    A rule that reads a document section and reports clean when that section is ABSENT is the
    failure `vacuity_violations` was added to this tool to prevent: the cheapest way to make
    a brake green is to delete what it reads.
    """
    text = _live()
    without = _replace_pointer(text, "")
    assert _lines_opening_with_the_label(without) == 0, (
        f"premise broken: a line still opens with {ri.SHIP_ORDER_LABEL} after the deletion, "
        f"so the fixture is not the missing-pointer case")
    assert ri.ship_order_paragraph(without) is None, ri.ship_order_paragraph(without)

    violations = ri.ship_order_violations(without)
    assert len(violations) == 1, f"expected exactly one violation, got {violations}"


def test_iter82_b3_the_pointer_is_the_line_that_OPENS_with_the_label() -> None:
    """Behavior 3's discrimination, measured because the committed roadmap needs it.

    The label occurs TWICE in the committed document: once as the pointer, and once inside a
    prose bullet that describes this very iteration. A reader keyed on the substring would
    take the bullet as the pointer, extract that sentence's row ids, and report on the wrong
    paragraph -- so the reader must key on the line OPENING with the label. Both halves are
    asserted: the committed document really does carry the label more than once, and the
    paragraph returned is the one that opens a line.
    """
    text = _live()
    assert text.count(ri.SHIP_ORDER_LABEL) >= 2, (
        "premise broken: the label occurs once, so this file cannot show the reader "
        "discriminating; the property still holds, it is just no longer measured here")
    assert _lines_opening_with_the_label(text) == 1, (
        f"{_lines_opening_with_the_label(text)} line(s) open with {ri.SHIP_ORDER_LABEL}; the "
        f"pointer must be unique or `the only statement of ship order` is false")
    paragraph = _pointer(text)
    assert paragraph.startswith(ri.SHIP_ORDER_LABEL), repr(paragraph[:80])

    embedded = f"prose that mentions {ri.SHIP_ORDER_LABEL} row {_a_shipped_id(text)} inline."
    assert ri.ship_order_paragraph(_replace_pointer(text, embedded)) is None, (
        "an inline mention was read as the pointer, so the reader can be steered by any "
        "sentence that quotes the label")


def test_iter82_b4_a_pointer_naming_zero_rows_yields_exactly_one_violation() -> None:
    """Behavior 4. Keeping the label while naming nothing must not silence the check either.

    This is the harder half of behavior 3: the label is present, so a reader skimming for the
    paragraph finds one, and only a check that counts the ids it extracted can tell that the
    pointer states no order at all.
    """
    text = _live()
    empty = _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} see the table above.")
    assert ri.ship_order_paragraph(empty), "premise broken: the label was not preserved"
    assert ri.ship_order_rows(empty) == [], (
        f"premise broken: the fixture names {ri.ship_order_rows(empty)}, not zero rows")

    violations = ri.ship_order_violations(empty)
    assert len(violations) == 1, f"expected exactly one violation, got {violations}"


def test_iter82_b34_the_two_vacuity_cases_are_reported_distinguishably() -> None:
    """Behaviors 3 and 4 are separate failures -- a missing pointer and a pointer that names
    nothing are fixed by different edits -- so their messages must not be interchangeable."""
    text = _live()
    missing = ri.ship_order_violations(_replace_pointer(text, ""))
    empty = ri.ship_order_violations(
        _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} see the table above."))
    assert missing and empty, f"premise broken: {missing} / {empty}"
    assert missing[0] != empty[0], (
        f"both vacuity cases report the same message, so a reader cannot tell which edit is "
        f"owed: {missing[0]!r}")


# ---------------------------------------------------------------------------
# Behavior 5: the tool COUNTS the findings and exits 1; the committed roadmap exits 0
# ---------------------------------------------------------------------------

def test_iter82_b5_the_committed_roadmap_exits_zero_at_the_process_boundary() -> None:
    """Behavior 5, clean half, over the real file this brake guards."""
    proc = _run_tool([])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _count_line(proc.stdout).startswith("0 violation(s)"), proc.stdout


def test_iter82_b5_a_copy_of_the_committed_roadmap_exits_zero(tmp_path) -> None:
    """Behavior 5, clean half, hermetically: a copy under `tmp_path` isolates this behavior
    from every other check the tool runs against the real checkout."""
    path = _as_file(tmp_path, _live(), "unchanged")
    proc = _run_tool([str(path)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _count_line(proc.stdout) == "0 violation(s)", proc.stdout


def test_iter82_b5_one_offending_row_exits_one_and_is_counted(tmp_path) -> None:
    """Behavior 5, fail half."""
    text = _live()
    shipped = _a_shipped_id(text)
    path = _as_file(
        tmp_path,
        _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} row {shipped} is next."),
        "one_offender")
    proc = _run_tool([str(path)])
    assert proc.returncode == 1, f"exited {proc.returncode}: {proc.stdout + proc.stderr}"
    assert _count_line(proc.stdout) == "1 violation(s)", proc.stdout
    assert re.search(rf"\b{re.escape(shipped)}\b", proc.stdout), proc.stdout


def test_iter82_b5_three_offending_rows_are_counted_as_three(tmp_path) -> None:
    """Behavior 5's COUNT claim. One offender cannot distinguish "counts them" from
    "reports the first one", so the count is measured against a fixture with three."""
    text = _live()
    shipped = _ids_by_status(text, "shipped")[:3]
    assert len(shipped) == 3, f"premise broken: only {len(shipped)} `shipped` row(s)"
    path = _as_file(
        tmp_path,
        _replace_pointer(
            text,
            f"{ri.SHIP_ORDER_LABEL} rows {shipped[0]}, {shipped[1]} and {shipped[2]}."),
        "three_offenders")

    assert len(ri.ship_order_violations(path.read_text(encoding="utf-8"))) == 3, \
        "premise broken: the fixture does not carry three violations"
    proc = _run_tool([str(path)])
    assert proc.returncode == 1, f"exited {proc.returncode}: {proc.stdout + proc.stderr}"
    assert _count_line(proc.stdout) == "3 violation(s)", proc.stdout
    for row in shipped:
        assert re.search(rf"\b{re.escape(row)}\b", proc.stdout), (row, proc.stdout)


@pytest.mark.parametrize("name, build", [
    ("missing_pointer", lambda text: _replace_pointer(text, "")),
    ("no_rows_named",
     lambda text: _replace_pointer(text, f"{ri.SHIP_ORDER_LABEL} see the table above.")),
])
def test_iter82_b5_each_vacuity_case_also_exits_one(tmp_path, name, build) -> None:
    """Behavior 5 over behaviors 3 and 4: a non-vacuity finding must fail the gate, not
    merely print. A finding the exit code ignores is a comment."""
    path = _as_file(tmp_path, build(_live()), name)
    proc = _run_tool([str(path)])
    assert proc.returncode == 1, f"exited {proc.returncode}: {proc.stdout + proc.stderr}"
    assert _count_line(proc.stdout) == "1 violation(s)", proc.stdout


# ---------------------------------------------------------------------------
# Behavior 6: the committed pointer names only `open` rows
# ---------------------------------------------------------------------------

def test_iter82_b6_the_committed_pointer_names_only_open_rows() -> None:
    """Behavior 6, asserted WITHOUT going through `ship_order_violations`.

    Behavior 1 already runs the check; if the check itself were wrong, behavior 1 and
    behavior 6 would agree with each other and neither would be about the document. So this
    reads the Status column directly and compares.
    """
    text = _live()
    named = ri.ship_order_rows(text)
    assert named, (
        "anti-vacuity: the committed pointer names no row, so `only open rows` is satisfied "
        "by naming nothing")
    statuses = ri.row_statuses(text)
    offenders = {row: statuses.get(row, "<not in the table>") for row in named
                 if statuses.get(row) != ri.SHIP_ORDER_STATUS}
    assert offenders == {}, (
        f"the ship-order pointer names row(s) the table does not report "
        f"{ri.SHIP_ORDER_STATUS!r}: {offenders}")


def test_iter82_b6_the_row_sweep_agrees_with_an_independent_reader() -> None:
    """Behavior 6's anti-vacuity by DERIVED EQUALITY.

    `ship_order_rows` is the tool's own reader, so behavior 6 asserted only through it would
    pass if the reader silently stopped seeing grouped ids -- precisely the omission `pm.md`
    records. `_rows_named_independently` is written here from the spec's description of the
    grouping, shares no code with the tool, and must agree.
    """
    text = _live()
    mine = _rows_named_independently(_pointer(text))
    theirs = ri.ship_order_rows(text)
    assert mine, "anti-vacuity: the independent reader found no row id in the pointer"
    assert theirs == mine, (
        f"the tool's sweep and an independent reader disagree about which rows the pointer "
        f"names: tool={theirs} independent={mine}")


def test_iter82_b6_the_independent_reader_is_armed_against_the_grouping_omission() -> None:
    """Two-sided control for the reader above: a reader that finds ids in the committed
    pointer proves nothing unless it is also shown to find ids the naive `single integer
    after row` form misses."""
    naive = re.compile(r"\brows?\s+(\d+)", re.IGNORECASE)
    sample = "**Next up:** rows 11 and 22, then rows 33/44, then row 55."
    assert [m.group(1) for m in naive.finditer(sample)] == ["11", "33", "55"], (
        "premise broken: the naive form no longer misses grouped ids, so this control is "
        "not measuring the omission it names")
    assert _rows_named_independently(sample) == ["11", "22", "33", "44", "55"], \
        _rows_named_independently(sample)


def test_iter82_b6_the_pointer_restates_no_row_or_register_count() -> None:
    """Behavior 6's durability half, from `pm.md`'s Why: the paragraph had accumulated four
    dead figures because a hand-copied count decays on every research pass.

    The numbers a pointer may carry are STABLE IDENTIFIERS -- a row id, and a commit sha or a
    path inside an inline code span. Any other integer in its PROSE is a restated measurement
    that nothing keeps current, so row groupings and code spans are removed and whatever
    digits survive are refused. Scoped to prose deliberately: refusing a digit inside a code
    span would forbid citing the commit that fixed a row, which is a locator, not a figure.

    This goes one step beyond behavior 6's letter (`names only open rows`). It is included
    because the committed paragraph makes the claim itself -- `No register or file figure is
    restated here` -- and an unchecked self-claim is the class of prose this iteration exists
    to stop shipping.
    """
    paragraph = _pointer(_live())
    prose = _CODE_SPAN.sub("", paragraph)
    assert prose != paragraph, (
        "premise broken: no inline code span was removed, so this sweep is not the "
        "prose-only sweep it claims to be")
    leftovers = re.findall(r"\d[\d,]*", _ROW_GROUP.sub("row", prose))
    assert leftovers == [], (
        f"the ship-order pointer restates {leftovers}; a hand-copied figure decays on every "
        f"pass, which is why the paragraph is rewritten to measure the file instead")
