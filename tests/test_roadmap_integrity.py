"""The roadmap brake must FIRE. A check that cannot fail is a comment.

Iteration 04's behaviors, in two halves that answer different questions.

TWO-SIDED FIXTURE CONTROLS ask "does the check work?" -- every check is a pure function
over text, so each gets a known-BAD inline fixture that must make it fire and a known-GOOD
one that must keep it silent. Absence of a finding is only evidence when the same function
is shown to produce one.

THE BRAKE asks "is the committed document right?" -- it runs the same functions over
`PRODUCT.md` and over this checkout's git log. That half is the part that fails a future
iteration which ships without recording itself, which is the point of the iteration.

The bad fixtures are built by mutating the good one, and every mutation asserts its own
premise: a silently no-op replace would turn a known-bad fixture into a copy of the
known-good one, and the test would pass while measuring nothing.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

import pytest

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures: one good document, and mutations of it that each break one rule
# ---------------------------------------------------------------------------

GOOD = """# Roadmap

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | a thing | shipped | landed |
| 2 | another thing | open | queued |

Status values are exactly `open` or `shipped` -- there is no third value.

## Done ledger

- iter 01 did a thing
- iter 02 did another thing

## Non-goals

- iter 99 outside the ledger section, so it is not a record
"""

_GOOD_OPEN_ROW = "| 2 | another thing | open | queued |"
_GOOD_LEDGER_ROW = "- iter 02 did another thing"
_GOOD_LEGEND = "Status values are exactly `open` or `shipped` -- there is no third value."


def _mutate(text: str, old: str, new: str) -> str:
    """Replace `old` once, asserting it was there. Guards against a vacuous fixture."""
    assert old in text, f"fixture premise broken: {old!r} is not in the good document"
    return text.replace(old, new, 1)


#: EB6: irregular padding inside the status cell must not hide the violation.
BAD_STATUS_PADDED = _mutate(GOOD, _GOOD_OPEN_ROW, "| 2 | another thing |  iter 02  | queued |")
BAD_STATUS_TIGHT = _mutate(GOOD, _GOOD_OPEN_ROW, "| 2 | another thing |iter 02| queued |")
#: A duplicate that is NOT also out of order.
BAD_LEDGER_DUPLICATE = _mutate(GOOD, _GOOD_LEDGER_ROW, "- iter 01 did another thing")
#: Out of order WITHOUT duplication: `duplicate` and `not-ascending` overlap, and a fixture
#: of `01, 02, 01` reports `duplicate`, leaving the `not-ascending` branch unproven.
BAD_LEDGER_ORDER = _mutate(GOOD, _GOOD_LEDGER_ROW, "- iter 03 landed\n- iter 02 recorded late")
BAD_LEDGER_ONE_DIGIT = _mutate(GOOD, "- iter 02 did", "- iter 2 did")
#: EB8: the same sentence, hard-wrapped by an editor.
WRAPPED_LEGEND = _mutate(
    GOOD,
    _GOOD_LEGEND,
    "Status values are exactly `open` or\n`shipped` -- there is no\nthird value.",
)
#: EB8 known-bad: names the two values but drops the clause that forbids a third.
PARTIAL_LEGEND = _mutate(GOOD, _GOOD_LEGEND, "Status values are `open` or `shipped`.")


# ---------------------------------------------------------------------------
# EB1 + EB6 + EB7: the status cell carries exactly one of two values
# ---------------------------------------------------------------------------

def test_status_check_is_silent_on_a_two_value_table() -> None:
    assert ri.row_status_violations(GOOD) == []


@pytest.mark.parametrize(
    "document, label",
    [(BAD_STATUS_PADDED, "padded cell"), (BAD_STATUS_TIGHT, "unpadded cell")],
)
def test_status_check_fires_regardless_of_cell_spacing(document: str, label: str) -> None:
    """EB6. The violation is reported as `(row number, offending status)`, spacing stripped."""
    assert ri.row_status_violations(document) == [("2", "iter 02")], label


def test_status_violation_message_names_the_row_and_the_value_verbatim() -> None:
    """EB7. A finding a reader cannot locate is a finding they will ignore."""
    message = ri.row_status_violations(BAD_STATUS_PADDED)[0].message
    assert "2" in message
    assert "iter 02" in message


def test_status_check_ignores_the_header_and_the_separator_rows() -> None:
    """Both look like table rows; neither carries a numeric id, which is the discriminator."""
    assert [row_id for row_id, _ in ri.table_rows(GOOD)] == ["1", "2"]


# ---------------------------------------------------------------------------
# EB2: ledger numbers are two-digit, unique and strictly ascending
# ---------------------------------------------------------------------------

def test_ledger_sequence_is_silent_on_a_good_ledger() -> None:
    assert ri.ledger_sequence_violations(GOOD) == []


def test_ledger_rows_are_scoped_to_the_done_ledger_section() -> None:
    """The `- iter 99` line under a later heading is prose, not a record."""
    assert ri.ledger_iterations(GOOD) == [("01", 1), ("02", 2)]


def test_ledger_duplicate_is_reported() -> None:
    assert ri.ledger_sequence_violations(BAD_LEDGER_DUPLICATE) == [("duplicate", "01")]


def test_ledger_not_ascending_is_reported_and_its_branch_is_reachable() -> None:
    """The fixture must be non-ascending WITHOUT duplicating, or this branch never runs."""
    values = [value for _, value in ri.ledger_iterations(BAD_LEDGER_ORDER)]
    assert len(values) == len(set(values)), "fixture duplicates, so it cannot isolate order"
    assert ri.ledger_sequence_violations(BAD_LEDGER_ORDER) == [("not-ascending", "02")]


def test_ledger_one_digit_is_reported() -> None:
    """`2` and `02` parse to one value, so the rule is about the text, not the number."""
    assert ri.ledger_sequence_violations(BAD_LEDGER_ONE_DIGIT) == [("not-two-digit", "2")]


def test_sequence_violation_kinds_are_the_declared_vocabulary() -> None:
    for document in (BAD_LEDGER_DUPLICATE, BAD_LEDGER_ORDER, BAD_LEDGER_ONE_DIGIT):
        for violation in ri.ledger_sequence_violations(document):
            assert violation.kind in ri.SEQUENCE_VIOLATION_KINDS
            assert violation.iteration in violation.message  # EB7


# ---------------------------------------------------------------------------
# EB3: git says shipped, so the ledger must say so once -- one direction only
# ---------------------------------------------------------------------------

def test_unrecorded_ship_is_reported_by_iteration_number() -> None:
    assert ri.unrecorded_ships(GOOD, [1, 2, 3]) == [3]
    assert "03" in ri.unrecorded_ship_messages([3])[0]  # EB7


def test_unrecorded_ships_is_silent_when_every_ship_has_a_row() -> None:
    assert ri.unrecorded_ships(GOOD, [1, 2]) == []


def test_unrecorded_ships_is_one_directional() -> None:
    """A ledger row ahead of git is the iteration currently landing, not a violation."""
    assert ri.unrecorded_ships(GOOD, [1]) == []
    assert ri.unrecorded_ships(GOOD, []) == []


def test_a_twice_recorded_iteration_is_not_recorded_once() -> None:
    """`exactly one row`: two rows for iteration 01 is a broken record, not a thorough one."""
    assert ri.unrecorded_ships(BAD_LEDGER_DUPLICATE, [1, 2]) == [1, 2]


# ---------------------------------------------------------------------------
# EB4: the git probe SKIPS with a reason -- it never silently passes
# ---------------------------------------------------------------------------

def test_git_probe_skips_outside_a_checkout(tmp_path: pathlib.Path) -> None:
    ships = ri.shipped_iterations_from_git(tmp_path)
    assert ships.iterations is None
    assert ships.skip_reason and ".git" in ships.skip_reason


def test_git_probe_skips_when_the_repository_is_broken(tmp_path: pathlib.Path) -> None:
    """A `.git` that exists but is not a repository: present, unusable, must not read clean."""
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    (tmp_path / ".git").write_text("not a repository\n", encoding="utf-8")
    ships = ri.shipped_iterations_from_git(tmp_path)
    assert ships.iterations is None
    assert ships.skip_reason and "git log exited" in ships.skip_reason


def test_git_probe_skips_when_git_cannot_be_run(tmp_path: pathlib.Path, monkeypatch) -> None:
    """An absent or unexecutable `git` is a SKIP, not a red suite on a source tarball."""
    (tmp_path / ".git").mkdir()

    def _boom(*_args, **_kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(ri.subprocess, "run", _boom)
    ships = ri.shipped_iterations_from_git(tmp_path)
    assert ships.iterations is None
    assert ships.skip_reason and "could not be run" in ships.skip_reason


def test_git_probe_collects_only_tagged_ship_subjects(tmp_path: pathlib.Path) -> None:
    """Two-sided on real git: a tagged subject is collected, an untagged one is not."""
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(tmp_path), *args],
                              capture_output=True, text=True, check=True)

    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    for subject in ("feat: a thing (foundry iter 01)", "docs: untagged, not a ship",
                    "fix: another thing (foundry iter 02)"):
        (tmp_path / "f.txt").write_text(subject, encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", subject)
    assert ri.shipped_iterations_from_git(tmp_path) == ((1, 2), None)


# ---------------------------------------------------------------------------
# EB8: the document states its own vocabulary, re-wrapping tolerated
# ---------------------------------------------------------------------------

def test_legend_check_survives_rewrapping() -> None:
    assert ri.legend_declares_two_values(WRAPPED_LEGEND) is True


def test_legend_check_fires_when_the_no_third_value_clause_is_missing() -> None:
    assert ri.legend_declares_two_values(PARTIAL_LEGEND) is False


# ---------------------------------------------------------------------------
# a brake that parsed nothing must not report clean
# ---------------------------------------------------------------------------

def test_vacuity_check_fires_on_a_document_with_no_rows() -> None:
    reasons = ri.vacuity_violations("# Roadmap\n\nnothing to see here\n")
    assert len(reasons) == 2


def test_vacuity_check_is_silent_on_a_real_document() -> None:
    assert ri.vacuity_violations(GOOD) == []


# ---------------------------------------------------------------------------
# THE BRAKE: the same functions over the committed roadmap
# ---------------------------------------------------------------------------

def _roadmap_text() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def test_committed_roadmap_is_parseable_at_all() -> None:
    assert ri.vacuity_violations(_roadmap_text()) == []


def test_committed_roadmap_uses_only_the_two_allowed_statuses() -> None:
    text = _roadmap_text()
    assert ri.table_rows(text), "no rows parsed, so the next assertion would be vacuous"
    violations = ri.row_status_violations(text)
    assert violations == [], "; ".join(v.message for v in violations)


def test_committed_ledger_numbers_are_two_digit_unique_and_ascending() -> None:
    text = _roadmap_text()
    assert ri.ledger_iterations(text), "no ledger rows parsed, so the check would be vacuous"
    violations = ri.ledger_sequence_violations(text)
    assert violations == [], "; ".join(v.message for v in violations)


def test_committed_roadmap_states_its_status_vocabulary() -> None:
    assert ri.legend_declares_two_values(_roadmap_text()) is True


def test_every_shipped_iteration_has_a_done_ledger_row() -> None:
    """The loss class this iteration closes. Skips loudly rather than passing quietly."""
    ships = ri.shipped_iterations_from_git(REPO_ROOT)
    if ships.iterations is None:
        pytest.skip(f"cannot ask git: {ships.skip_reason}")
    if not ships.iterations:
        pytest.skip("no ship commits in this history: the cross-check has nothing to say")
    missing = ri.unrecorded_ships(_roadmap_text(), ships.iterations)
    assert missing == [], "; ".join(ri.unrecorded_ship_messages(missing))
