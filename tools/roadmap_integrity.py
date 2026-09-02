#!/usr/bin/env python3
"""Roadmap-ledger integrity checks over `PRODUCT.md`.

WHY this is a suite brake and not a convention: `PRODUCT.md` is the input every planning
stage derives its next pick from, and its own ledger preamble says deferring a record is
how history gets permanently lost. It has now lost one -- iteration 03 shipped (its commit
subject carries `(foundry iter 03)`) with a row in neither the roadmap table nor the Done
ledger, and nothing looked wrong. The loss was invisible because the Status column carried
three vocabularies (`open`, `shipped`, `iter NN`), so a cell reading `iter 02` meant either
"currently landing" or "shipped by iter 02" depending on the reader. An ambiguous state
cannot be checked, so the third value is DELETED from the document and the remaining
two-value column is asserted here.

Every check below is a pure function over text, which is what makes it provable two-sided:
a known-bad string must make it fire and a known-good string must keep it silent. Git is
touched by exactly one function, and that function returns a SKIP REASON instead of
raising, because a check that could not run must say so rather than report clean.

The ship-order pointer is checked the same way, and it drifted for the same reason. The
`**Next up:**` paragraph is this repo's only statement of which row to build next, and
nothing in the build reads it -- so it came to name three rows the table's own Status column
reported `shipped`, one of them as the strongest remaining candidate. The requirement is
DERIVED from that column rather than from a list of retired rows, because such a list is a
second copy of the table and decays the moment a row flips.

Offline by contract: the only subprocess is a local `git log` inside this checkout.

Usage:
    python3 tools/roadmap_integrity.py [ROADMAP]

Exit codes: 0 no violations, 1 at least one violation, 2 bad usage.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from collections.abc import Sequence
from typing import NamedTuple

#: The only two status values a roadmap row may carry. There is deliberately no third:
#: the retired `iter NN` value was ambiguous, and an ambiguous state cannot be checked.
ALLOWED_STATUSES: tuple[str, ...] = ("open", "shipped")

#: The three ways a Done-ledger iteration sequence can be wrong. `duplicate` and
#: `not-ascending` overlap, so a fixture proving one must not also trip the other.
#: `not-two-digit` names a MINIMUM width of two, which is why it stays true of a ledger
#: that records iteration 100: the rule it enforces is canonical zero-padded form, so `2`
#: is a violation (its canonical form is `02`) and so is the over-padded `0100`.
SEQUENCE_VIOLATION_KINDS: tuple[str, ...] = ("not-two-digit", "duplicate", "not-ascending")

#: A table row opens with a numeric id cell, which excludes both the header row and the
#: `|---|` rule without needing to know where the table starts.
_TABLE_ROW = re.compile(r"^\|\s*(\d+)\s*\|")

#: A Done-ledger row. Collected only while inside the ledger section, so an `- iter NN`
#: line elsewhere in the document is not mistaken for a record.
_LEDGER_ROW = re.compile(r"^-\s+iter\s+(\d+)\b")

#: The iteration a commit subject claims to have shipped.
_SHIP_SUBJECT = re.compile(r"\(foundry iter (\d+)\)")

#: Compared against a lower-cased, stripped heading line.
_LEDGER_HEADING = "## done ledger"

#: The legend sentence that pins the vocabulary. Matched on whitespace-normalised text so
#: the paragraph may be re-wrapped without breaking the check.
LEGEND_SENTENCE = (
    "Status values are exactly `open` or `shipped` -- there is no third value."
)

#: 0-based index of the Status cell in a roadmap table row: `| # | Item | Status | Notes |`.
_STATUS_CELL = 2

#: The label that opens the roadmap's ship-order pointer.
SHIP_ORDER_LABEL: str = "**Next up:**"

#: The only status a row named as a forward candidate may carry. It is one of
#: `ALLOWED_STATUSES` by construction -- `shipped` is the other, and pointing the next build
#: at shipped work is the whole defect this check exists to stop.
SHIP_ORDER_STATUS: str = "open"

#: Anchored at line start on purpose. The document legitimately QUOTES this label in prose
#: -- a Done-ledger row explains that a missing pointer is itself a violation -- so a
#: file-wide search would find that copy on a document whose real pointer had been deleted,
#: which is fail-OPEN on the one case the non-vacuity rule exists to catch.
_SHIP_ORDER_MARKER = re.compile(rf"^[ \t]*{re.escape(SHIP_ORDER_LABEL)}", re.MULTILINE)

#: A GROUP of row ids after `row`/`rows`: `row 51`, `rows 64 and 70`, `rows 55/71`,
#: `rows 61, 62 and 63`. Extracting the group rather than a single integer is load-bearing:
#: a one-integer sweep over the drifted paragraph found five ids and missed two of the
#: `shipped` ones, so the narrower reading reports a mis-steering document clean.
_ROW_GROUP = re.compile(r"\brows?\s+(\d+(?:\s*(?:,|/|and|or)\s*\d+)*)", re.IGNORECASE)

_INTEGER = re.compile(r"\d+")

_GIT_LOG_TIMEOUT_S = 30


class StatusViolation(NamedTuple):
    """A roadmap row whose Status cell falls outside the two-value vocabulary.

    A plain tuple of `(row, status)`, both verbatim from the document, so a violation can
    be compared literally in a test and still carry a human-readable message.
    """

    row: str
    status: str

    @property
    def message(self) -> str:
        allowed = " or ".join(ALLOWED_STATUSES)
        return f"roadmap row {self.row}: status '{self.status}' is not {allowed}"


class SequenceViolation(NamedTuple):
    """A Done-ledger iteration number that is malformed, repeated, or out of order."""

    kind: str
    iteration: str

    @property
    def message(self) -> str:
        return f"done ledger iteration '{self.iteration}': {self.kind}"


class GitShips(NamedTuple):
    """What git reports as shipped, or why it could not be asked.

    Exactly one field is populated. `iterations is None` means SKIP, never "nothing
    shipped": conflating the two is how a check that cannot run reports clean.
    """

    iterations: tuple[int, ...] | None
    skip_reason: str | None


def normalise_whitespace(text: str) -> str:
    """Collapse every run of whitespace to one space.

    Committed prose is hard-wrapped, so a claim that spans two source lines is invisible
    to a substring match on the raw text -- a check written the obvious way is fail-open
    on exactly the drift it was written to catch.
    """
    return " ".join(text.split())


def table_rows(text: str) -> list[tuple[str, list[str]]]:
    """`(row id, stripped cells)` for every numbered roadmap table row, in file order."""
    rows: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        match = _TABLE_ROW.match(line)
        if match is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append((match.group(1), cells))
    return rows


def row_status_violations(text: str) -> list[StatusViolation]:
    """Rows whose Status cell is not exactly `open` or `shipped`.

    Cell-scoped on purpose. A file-wide search for the retired `iter NN` phrase is
    fail-CLOSED on the corrected document, because the row that RETIRES a vocabulary has
    to name it -- the phrase legitimately appears in an Item cell and a ledger row.
    """
    violations: list[StatusViolation] = []
    for row_id, cells in table_rows(text):
        if len(cells) <= _STATUS_CELL:
            continue
        status = normalise_whitespace(cells[_STATUS_CELL])
        if status not in ALLOWED_STATUSES:
            violations.append(StatusViolation(row_id, status))
    return violations


def ledger_iterations(text: str) -> list[tuple[str, int]]:
    """`(raw digits, value)` per Done-ledger row, in file order.

    The raw digits are kept because the two-digit rule is about the text, not the value:
    `2` and `02` parse to the same integer and only one of them is a valid record.
    """
    found: list[tuple[str, int]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip().lower() == _LEDGER_HEADING
            continue
        if not inside:
            continue
        match = _LEDGER_ROW.match(line)
        if match is not None:
            found.append((match.group(1), int(match.group(1))))
    return found


def ledger_sequence_violations(text: str) -> list[SequenceViolation]:
    """Ledger iteration numbers that are not canonically padded, unique and ascending.

    The number rule is a MINIMUM width of two, not an exact length of two, and the
    predicate spells that as canonical zero-padded form: `raw != f"{value:02d}"`. An exact
    length made iteration 100 unrecordable, which is a shipping ceiling rather than a
    cosmetic limit -- `unrecorded_ships` makes one ledger row per shipped iteration a ship
    PRECONDITION, so a ledger that cannot carry 100 stops every iteration from 100 onward,
    and it stopped iteration 97 already: two committed tests DERIVE rows above the live
    maximum, so the ceiling was crossed by the suite before the ledger ever reached it.

    Pointwise IDENTICAL to the length test across 1..99, which is why the published kind
    name and its four fixtures need no edit: every two-digit run of digits already IS its
    own canonical form, so `02` stays clean and `2` stays a violation because its canonical
    form is `02`. The only pairs the two predicates judge differently are the ones the
    length test could never accept -- an unpadded number of three digits or more. Over-pad
    is still refused (`0100` is not `100`), because the defect being caught is a raw
    iteration number that no other ledger reader will spell the same way.
    """
    violations: list[SequenceViolation] = []
    seen: list[int] = []
    for raw, value in ledger_iterations(text):
        if raw != f"{value:02d}":
            violations.append(SequenceViolation("not-two-digit", raw))
        if value in seen:
            violations.append(SequenceViolation("duplicate", raw))
        elif seen and value <= seen[-1]:
            violations.append(SequenceViolation("not-ascending", raw))
        seen.append(value)
    return violations


def unrecorded_ships(text: str, shipped: Sequence[int]) -> list[int]:
    """Iterations git calls shipped that do not have exactly one Done-ledger row.

    ONE-DIRECTIONAL by design, and that is what makes it safe in the suite: the iteration
    currently landing has a ledger row and no ship commit yet, and a REVERTED iteration
    produces a ship commit for nothing, so asserting the reverse direction would fail on
    the product's own bookkeeping and need carve-outs for both cases.
    """
    recorded = [value for _, value in ledger_iterations(text)]
    return [n for n in shipped if recorded.count(n) != 1]


def unrecorded_ship_messages(iterations: Sequence[int]) -> list[str]:
    """One message per unrecorded ship, naming the iteration as the ledger writes it."""
    return [
        f"iteration {n:02d} ships in git but has no single done-ledger row"
        for n in iterations
    ]


def legend_declares_two_values(text: str) -> bool:
    """True when the document itself states the vocabulary, re-wrapping tolerated."""
    return normalise_whitespace(LEGEND_SENTENCE) in normalise_whitespace(text)


def ship_order_paragraph(text: str) -> str | None:
    """The ship-order paragraph verbatim, or `None` when the document carries no pointer.

    `None` and `""` are kept distinct for the same reason `GitShips` separates them: a
    missing pointer is a finding, and an empty string would let a caller read it as a
    paragraph that merely named nothing.
    """
    match = _SHIP_ORDER_MARKER.search(text)
    if match is None:
        return None
    paragraph: list[str] = []
    for line in text[match.start():].splitlines():
        if paragraph and not line.strip():
            break
        paragraph.append(line)
    return "\n".join(paragraph)


def ship_order_rows(text: str) -> list[str]:
    """Row ids the ship-order paragraph names, in first-mention order, de-duplicated.

    Ids stay as the document spells them so a message can quote one verbatim, and a row
    named twice is one pointer rather than two violations.
    """
    paragraph = ship_order_paragraph(text)
    if paragraph is None:
        return []
    named: list[str] = []
    for group in _ROW_GROUP.finditer(paragraph):
        for row_id in _INTEGER.findall(group.group(1)):
            if row_id not in named:
                named.append(row_id)
    return named


def row_statuses(text: str) -> dict[str, str]:
    """`{row id: status}` for every table row that carries a Status cell."""
    return {
        row_id: normalise_whitespace(cells[_STATUS_CELL])
        for row_id, cells in table_rows(text)
        if len(cells) > _STATUS_CELL
    }


def ship_order_violations(text: str) -> list[str]:
    """Reasons the roadmap's ship-order pointer would mis-steer the next build.

    Messages rather than a tuple type: this check has three unrelated failure shapes
    (absent, vacuous, wrong status) and inventing a field that is null for two of them
    would say less than the sentence does.

    Non-vacuous by construction. A missing pointer and a pointer naming zero rows are each
    their own finding, because a rule that passes over an empty parse is the failure
    `vacuity_violations` was added to prevent -- and unlike the parses there, this one is
    switched off by deleting a single line.
    """
    if ship_order_paragraph(text) is None:
        return [f"no line opens with `{SHIP_ORDER_LABEL}`: the ship-order check is vacuous"]
    named = ship_order_rows(text)
    if not named:
        return [
            f"the `{SHIP_ORDER_LABEL}` paragraph names no roadmap row: "
            "the ship-order check is vacuous"
        ]
    statuses = row_statuses(text)
    violations: list[str] = []
    for row_id in named:
        status = statuses.get(row_id)
        if status is None:
            violations.append(
                f"ship order names row {row_id}, which the roadmap table does not carry"
            )
        elif status != SHIP_ORDER_STATUS:
            violations.append(
                f"ship order names row {row_id}, whose status is '{status}' and not "
                f"'{SHIP_ORDER_STATUS}'"
            )
    return violations


def vacuity_violations(text: str) -> list[str]:
    """Reasons this document cannot be checked at all.

    A parser that matched nothing makes every check above trivially clean, so an empty
    parse is itself the finding. Without this a renamed heading turns the brake off and
    the suite stays green.
    """
    reasons: list[str] = []
    if not table_rows(text):
        reasons.append("no numbered roadmap table rows found: the status check is vacuous")
    if not ledger_iterations(text):
        reasons.append("no done-ledger rows found: the ledger checks are vacuous")
    return reasons


def shipped_iterations_from_git(repo: pathlib.Path) -> GitShips:
    """Iterations whose ship commit exists in `repo`'s history, or a stated skip reason.

    Every failure mode -- no checkout, no `git`, a broken repository, a timeout -- becomes
    a reason string. Raising would make the suite red on a tarball, and returning an empty
    tuple would make it green while measuring nothing.
    """
    if not (repo / ".git").exists():
        return GitShips(None, f"no git checkout: {repo.name}/.git does not exist")
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=_GIT_LOG_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GitShips(None, f"git log could not be run: {type(exc).__name__}: {exc}")
    if completed.returncode != 0:
        first_line = completed.stderr.strip().splitlines()[:1]
        detail = first_line[0] if first_line else "no stderr"
        return GitShips(None, f"git log exited {completed.returncode}: {detail}")
    found = {int(match.group(1)) for match in _SHIP_SUBJECT.finditer(completed.stdout)}
    return GitShips(tuple(sorted(found)), None)


def default_roadmap() -> pathlib.Path:
    """`PRODUCT.md` beside this checkout, found relative to this file."""
    return pathlib.Path(__file__).resolve().parent.parent / "PRODUCT.md"


def main(argv: list[str]) -> int:
    roadmap = pathlib.Path(argv[1]) if len(argv) > 1 else default_roadmap()
    if not roadmap.is_file():
        sys.stderr.write(f"Error: not a file: {roadmap}\n")
        return 2

    text = roadmap.read_text(encoding="utf-8")
    findings: list[str] = list(vacuity_violations(text))
    findings += [violation.message for violation in row_status_violations(text)]
    findings += [violation.message for violation in ledger_sequence_violations(text)]
    if not legend_declares_two_values(text):
        findings.append("status legend does not state the two-value vocabulary verbatim")
    findings += ship_order_violations(text)

    ships = shipped_iterations_from_git(roadmap.resolve().parent)
    if ships.iterations is None:
        print(f"  SKIP  shipped-iteration cross-check: {ships.skip_reason}")
    else:
        print(f"  git reports shipped: {list(ships.iterations)}")
        findings += unrecorded_ship_messages(unrecorded_ships(text, ships.iterations))

    print(f"  ship order names row(s): {ship_order_rows(text)}")
    rows, ledger = len(table_rows(text)), len(ledger_iterations(text))
    print(f"  {rows} table row(s), {ledger} ledger row(s)")
    for finding in findings:
        print(f"  VIOLATION  {finding}")
    print(f"\n{len(findings)} violation(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
