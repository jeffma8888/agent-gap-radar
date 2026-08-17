"""Iteration 04 behaviors: the roadmap's status vocabulary is exactly two values, its
Done ledger is a well-formed sequence, and a shipped iteration with no ledger row fails
the suite.

Black-box. Nothing here reads the implementation source (`tools/roadmap_integrity.py`);
the module is driven only through the public names the suite already uses. Expected
values are stated literally from the spec, or derived by an INDEPENDENT ORACLE written
from the spec's own description of the document format -- never copied out of the
implementation:

* `_oracle_table_rows` -- a roadmap row is a line whose first pipe-cell is a number,
  which excludes the header and the `|---|` separator; its status is the third cell.
* `_oracle_ledger_rows` -- a ledger row is `- iter NN`, collected ONLY inside the
  `## Done ledger` section (stop at the next `## ` heading).
* `_shipped_from_git` -- `(foundry iter NN)` in a commit subject, extracted here with
  its own regex over this checkout's own `git log`.

The oracle earns the right to be believed by disagreeing with a planted defect: every
mutation fixture below is built from the REAL committed document and asserts its own
premise, so a no-op edit cannot turn a known-bad fixture into a copy of the good one.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

import pytest

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

ALLOWED_STATUSES = ("open", "shipped")
LEDGER_HEADING = "## done ledger"


# ---------------------------------------------------------------------------
# independent oracle: the document format as the SPEC describes it
# ---------------------------------------------------------------------------

def _roadmap_text() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Collapse every run of whitespace, so a re-wrapped sentence still matches."""
    return " ".join(text.split())


def _oracle_table_rows(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        rows.append((cells[0], cells[2]))
    return rows


def _oracle_ledger_indices(text: str) -> list[tuple[int, str]]:
    """(line index, iteration digits) for ledger rows, scoped to the ledger section."""
    inside = False
    found: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        if line.startswith("## "):
            inside = line.strip().lower() == LEDGER_HEADING
            continue
        if not inside:
            continue
        match = re.match(r"^-\s+iter\s+(\d+)\b", line)
        if match:
            found.append((index, match.group(1)))
    return found


def _oracle_ledger_rows(text: str) -> list[str]:
    return [digits for _, digits in _oracle_ledger_indices(text)]


def _shipped_from_git(root: pathlib.Path) -> tuple[int, ...] | None:
    """Independent extraction of shipped iterations. None means 'cannot ask git'."""
    if shutil.which("git") is None or not (root / ".git").exists():
        return None
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%s"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    found = {int(n) for n in re.findall(r"\(foundry iter (\d+)\)", done.stdout)}
    return tuple(sorted(found))


# ---------------------------------------------------------------------------
# mutation fixtures, all built from the REAL committed document
# ---------------------------------------------------------------------------

def _set_status_cell(text: str, row_id: str, new_cell: str) -> str:
    """Rewrite one row's status cell verbatim, asserting the row exists first."""
    out, hits = [], 0
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) > 4 and parts[1].strip() == row_id:
            parts[3] = new_cell
            line = "|".join(parts)
            hits += 1
        out.append(line)
    assert hits == 1, f"fixture premise broken: row {row_id} is not a unique table row"
    return "\n".join(out) + "\n"


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"fixture premise broken: {old!r} is not unique in the document"
    assert new != old, "fixture premise broken: the replacement is a no-op"
    return text.replace(old, new, 1)


def _swap_last_two_ledger_rows(text: str) -> str:
    """Non-ascending WITHOUT duplicating: `duplicate` and `not-ascending` overlap, and a
    ledger of 01,02,01 classifies as `duplicate`, leaving `not-ascending` unproven."""
    rows = _oracle_ledger_indices(text)
    assert len(rows) >= 2, "fixture premise broken: fewer than two ledger rows"
    (first_index, first_digits), (second_index, second_digits) = rows[-2], rows[-1]
    assert first_digits != second_digits, "fixture premise broken: the two rows duplicate"
    lines = text.splitlines()
    lines[first_index], lines[second_index] = lines[second_index], lines[first_index]
    return "\n".join(lines) + "\n"


REAL = _roadmap_text()
LAST_LEDGER_DIGITS = _oracle_ledger_rows(REAL)[-1]
LEGEND = "Status values are exactly `open` or `shipped` -- there is no third value."

BAD_STATUS_PADDED = _set_status_cell(REAL, "19", "  iter 04  ")
BAD_STATUS_TIGHT = _set_status_cell(REAL, "19", "iter 04")
GOOD_STATUS_PADDED = _set_status_cell(REAL, "19", "    shipped    ")
BAD_LEDGER_ORDER = _swap_last_two_ledger_rows(REAL)
BAD_LEDGER_DUPLICATE = _replace_once(
    REAL, f"- iter {LAST_LEDGER_DIGITS} ", "- iter 03 duplicated: "
)
#: A one-digit row written literally: deriving it by stripping a leading zero would
#: become a silent no-op the day the ledger reaches `iter 10`, and a vacuous bad fixture
#: is worse than no fixture.
BAD_LEDGER_ONE_DIGIT = _replace_once(REAL, f"- iter {LAST_LEDGER_DIGITS} ", "- iter 9 ")
BAD_LEGEND_PARTIAL = _replace_once(REAL, LEGEND, "Status values are `open` or `shipped`.")
BAD_LEGEND_ABSENT = _replace_once(REAL, LEGEND, "")
GOOD_LEGEND_REWRAPPED = _replace_once(
    REAL, LEGEND, "Status values are exactly `open` or\n`shipped` -- there is\nno third value."
)


def _all_document_findings(text: str) -> list[str]:
    """Every document-level finding the brake can report, as flat strings."""
    findings = [v.message for v in ri.row_status_violations(text)]
    findings += [v.message for v in ri.ledger_sequence_violations(text)]
    findings += list(ri.vacuity_violations(text))
    if ri.legend_declares_two_values(text) is not True:
        findings.append("legend does not declare the two-value vocabulary")
    return findings


# ---------------------------------------------------------------------------
# EB1: every status cell is exactly `open` or `shipped`
# ---------------------------------------------------------------------------

def test_eb1_oracle_finds_rows_in_the_committed_roadmap() -> None:
    """Anti-vacuity: every later assertion about rows is empty talk without this.

    Deliberately lag-tolerant. The document states that row numbers are stable
    identifiers and rows are appended, so unique-and-ascending is the invariant; asserting
    a contiguous 1..N would turn a legitimate future row removal into a false failure.
    """
    rows = _oracle_table_rows(REAL)
    assert len(rows) >= 10, "too few rows parsed for any later row assertion to mean anything"
    ids = [int(row_id) for row_id, _ in rows]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_eb1_committed_statuses_are_only_the_two_allowed_values() -> None:
    offenders = [(rid, status) for rid, status in _oracle_table_rows(REAL)
                 if status not in ALLOWED_STATUSES]
    assert offenders == []


def test_eb1_check_agrees_with_the_oracle_on_the_committed_document() -> None:
    assert ri.row_status_violations(REAL) == []
    assert [rid for rid, _ in ri.table_rows(REAL)] == [rid for rid, _ in _oracle_table_rows(REAL)]


def test_eb1_check_fires_on_the_real_document_with_one_status_reverted() -> None:
    """The strongest known-bad control available: the committed document, minus the fix."""
    assert _oracle_table_rows(BAD_STATUS_PADDED)[18] == ("19", "iter 04")
    assert ri.row_status_violations(BAD_STATUS_PADDED) == [("19", "iter 04")]


def test_eb1_violation_is_a_row_number_and_offending_status_pair() -> None:
    row_id, status = ri.row_status_violations(BAD_STATUS_TIGHT)[0]
    assert row_id == "19"
    assert status == "iter 04"


# ---------------------------------------------------------------------------
# EB2: ledger numbers are two-digit, unique, strictly ascending
# ---------------------------------------------------------------------------

def test_eb2_oracle_finds_ledger_rows_and_scopes_them_to_the_section() -> None:
    digits = _oracle_ledger_rows(REAL)
    assert len(digits) >= 4
    assert digits == sorted(digits)
    assert all(len(d) == 2 for d in digits)
    assert len(set(digits)) == len(digits)


def test_eb2_check_agrees_with_the_oracle_on_the_committed_document() -> None:
    assert ri.ledger_sequence_violations(REAL) == []
    assert [d for d, _ in ri.ledger_iterations(REAL)] == _oracle_ledger_rows(REAL)


@pytest.mark.parametrize(
    "document, kind",
    [
        (BAD_LEDGER_DUPLICATE, "duplicate"),
        (BAD_LEDGER_ORDER, "not-ascending"),
        (BAD_LEDGER_ONE_DIGIT, "not-two-digit"),
    ],
)
def test_eb2_each_violation_class_is_reachable_from_the_real_ledger(document: str, kind: str) -> None:
    kinds = [v.kind for v in ri.ledger_sequence_violations(document)]
    assert kinds, "no violation reported, so this class is unproven"
    assert kind in kinds
    assert kind in ri.SEQUENCE_VIOLATION_KINDS


def test_eb2_the_not_ascending_fixture_does_not_also_duplicate() -> None:
    """Overlapping classes: without this, the `not-ascending` branch may never run."""
    digits = _oracle_ledger_rows(BAD_LEDGER_ORDER)
    assert len(set(digits)) == len(digits), "fixture duplicates, so it cannot isolate order"
    assert digits != sorted(digits), "fixture is still ascending, so it is not a bad fixture"
    assert [v.kind for v in ri.ledger_sequence_violations(BAD_LEDGER_ORDER)] == ["not-ascending"]


def test_eb2_kinds_are_confined_to_the_declared_vocabulary() -> None:
    assert set(ri.SEQUENCE_VIOLATION_KINDS) == {"not-two-digit", "duplicate", "not-ascending"}


# ---------------------------------------------------------------------------
# EB3: git says shipped, so the ledger says so exactly once -- one direction only
# ---------------------------------------------------------------------------

def test_eb3_committed_ledger_records_every_shipped_iteration() -> None:
    shipped = _shipped_from_git(REPO_ROOT)
    if shipped is None:
        pytest.skip("cannot ask git in this checkout, so the cross-check is unavailable")
    if not shipped:
        pytest.skip("no `(foundry iter NN)` subjects in this history: nothing to cross-check")
    recorded = {int(d) for d in _oracle_ledger_rows(REAL)}
    assert set(shipped) <= recorded
    assert ri.unrecorded_ships(REAL, list(shipped)) == []


def test_eb3_check_agrees_with_an_independent_git_extraction() -> None:
    shipped = _shipped_from_git(REPO_ROOT)
    if shipped is None:
        pytest.skip("cannot ask git in this checkout, so there is nothing to compare against")
    probe = ri.shipped_iterations_from_git(REPO_ROOT)
    assert probe.skip_reason is None
    assert tuple(sorted(probe.iterations)) == shipped


def test_eb3_fires_on_an_iteration_git_shipped_but_never_recorded() -> None:
    highest = int(_oracle_ledger_rows(REAL)[-1])
    assert ri.unrecorded_ships(REAL, [highest + 1]) == [highest + 1]


def test_eb3_is_one_directional_a_ledger_row_ahead_of_git_is_not_a_violation() -> None:
    assert ri.unrecorded_ships(REAL, []) == []
    assert ri.unrecorded_ships(REAL, [1]) == []


def test_eb3_exactly_one_row_a_twice_recorded_iteration_is_not_recorded() -> None:
    assert _oracle_ledger_rows(BAD_LEDGER_DUPLICATE).count("03") == 2
    assert ri.unrecorded_ships(BAD_LEDGER_DUPLICATE, [3]) == [3]


# ---------------------------------------------------------------------------
# EB4: the git probe SKIPS with a stated reason -- it never silently passes
# ---------------------------------------------------------------------------

def test_eb4_skips_when_dot_git_is_absent(tmp_path: pathlib.Path) -> None:
    probe = ri.shipped_iterations_from_git(tmp_path)
    assert probe.iterations is None
    assert probe.skip_reason and "git" in probe.skip_reason.lower()


def test_eb4_skips_when_git_log_exits_non_zero(tmp_path: pathlib.Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    (tmp_path / ".git").write_text("not a repository\n", encoding="utf-8")
    probe = ri.shipped_iterations_from_git(tmp_path)
    assert probe.iterations is None
    assert probe.skip_reason and "git" in probe.skip_reason.lower()


def test_eb4_skips_when_git_cannot_be_executed(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Black-box unavailability: an empty PATH, not a patched internal."""
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "no-tools-here"))
    probe = ri.shipped_iterations_from_git(tmp_path)
    assert probe.iterations is None
    assert probe.skip_reason and "git" in probe.skip_reason.lower()


def test_eb4_unknown_is_distinguishable_from_a_history_with_no_ships(tmp_path: pathlib.Path) -> None:
    """`None` (could not ask) must never be conflated with `()` (asked, nothing shipped)."""
    if shutil.which("git") is None:
        pytest.skip("git executable not available")

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args],
                       capture_output=True, text=True, check=True)

    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    (tmp_path / "f.txt").write_text("no ship tag in this subject\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "docs: untagged, not a ship")
    probe = ri.shipped_iterations_from_git(tmp_path)
    assert probe.iterations == ()
    assert probe.skip_reason is None
    assert ri.unrecorded_ships(REAL, list(probe.iterations)) == []


# ---------------------------------------------------------------------------
# EB5: pure functions over text, proven two-sided
# ---------------------------------------------------------------------------

def test_eb5_every_check_is_two_sided_on_this_module_s_own_fixtures() -> None:
    pairs = [
        (lambda t: ri.row_status_violations(t), REAL, BAD_STATUS_PADDED),
        (lambda t: ri.ledger_sequence_violations(t), REAL, BAD_LEDGER_ORDER),
        (lambda t: [] if ri.legend_declares_two_values(t) else ["fired"], REAL, BAD_LEGEND_PARTIAL),
        (lambda t: ri.vacuity_violations(t), REAL, "# Roadmap\n\nno rows at all\n"),
    ]
    for index, (check, good, bad) in enumerate(pairs):
        assert check(good) == [], f"check {index} fired on the known-good document"
        assert check(bad) != [], f"check {index} stayed silent on the known-bad document"


def test_eb5_results_depend_only_on_the_argument_not_on_the_committed_file() -> None:
    assert ri.row_status_violations(REAL) == []
    assert ri.row_status_violations(BAD_STATUS_PADDED) != []
    assert ri.row_status_violations(REAL) == []


def test_eb5_checks_are_deterministic_and_write_nothing() -> None:
    before = ROADMAP.read_bytes()
    first = _all_document_findings(BAD_STATUS_PADDED)
    second = _all_document_findings(BAD_STATUS_PADDED)
    assert first == second
    assert ri.unrecorded_ships(REAL, [1, 2, 3]) == ri.unrecorded_ships(REAL, [1, 2, 3])
    assert ROADMAP.read_bytes() == before


# ---------------------------------------------------------------------------
# EB6: detection is spacing-insensitive, in BOTH directions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("document", [BAD_STATUS_PADDED, BAD_STATUS_TIGHT])
def test_eb6_a_bad_status_is_found_whatever_the_padding(document: str) -> None:
    assert ri.row_status_violations(document) == [("19", "iter 04")]


def test_eb6_a_legal_status_with_odd_padding_is_not_a_violation() -> None:
    """The inverse control: a check that does not strip would report this one."""
    assert "|    shipped    |" in GOOD_STATUS_PADDED
    assert ri.row_status_violations(GOOD_STATUS_PADDED) == []


# ---------------------------------------------------------------------------
# EB7: every message names the offending identifier verbatim
# ---------------------------------------------------------------------------

def test_eb7_status_message_names_the_row_and_the_offending_value() -> None:
    message = ri.row_status_violations(BAD_STATUS_PADDED)[0].message
    assert "19" in message
    assert "iter 04" in message


def test_eb7_sequence_messages_name_their_iteration() -> None:
    for document in (BAD_LEDGER_DUPLICATE, BAD_LEDGER_ORDER, BAD_LEDGER_ONE_DIGIT):
        violations = ri.ledger_sequence_violations(document)
        assert violations
        for violation in violations:
            assert violation.iteration in violation.message
            assert violation.kind in violation.message


def test_eb7_unrecorded_ship_message_names_the_iteration() -> None:
    highest = int(_oracle_ledger_rows(REAL)[-1])
    missing = highest + 1
    messages = ri.unrecorded_ship_messages([missing])
    assert len(messages) == 1
    assert f"{missing:02d}" in messages[0]


# ---------------------------------------------------------------------------
# EB8: the document states its own vocabulary, re-wrapping tolerated
# ---------------------------------------------------------------------------

def test_eb8_oracle_finds_the_legend_on_normalised_text() -> None:
    assert _norm(LEGEND) in _norm(REAL)


def test_eb8_the_oracle_normaliser_is_what_makes_rewrapping_pass() -> None:
    """Fail-open control on the oracle itself: unnormalised matching misses the wrap."""
    assert LEGEND not in GOOD_LEGEND_REWRAPPED
    assert _norm(LEGEND) in _norm(GOOD_LEGEND_REWRAPPED)


def test_eb8_committed_document_declares_its_status_vocabulary() -> None:
    assert ri.legend_declares_two_values(REAL) is True


def test_eb8_rewrapping_the_legend_does_not_break_the_check() -> None:
    assert ri.legend_declares_two_values(GOOD_LEGEND_REWRAPPED) is True


@pytest.mark.parametrize("document", [BAD_LEGEND_PARTIAL, BAD_LEGEND_ABSENT])
def test_eb8_a_legend_without_the_no_third_value_clause_fails(document: str) -> None:
    assert ri.legend_declares_two_values(document) is False


# ---------------------------------------------------------------------------
# the brake is load-bearing: each planted defect turns the committed suite red
# ---------------------------------------------------------------------------

def test_committed_document_reports_no_findings_at_all() -> None:
    findings = _all_document_findings(REAL)
    assert findings == [], "; ".join(findings)


@pytest.mark.parametrize(
    "document, label",
    [
        (BAD_STATUS_PADDED, "a third status value"),
        (BAD_LEDGER_DUPLICATE, "a duplicated ledger row"),
        (BAD_LEDGER_ORDER, "a ledger out of order"),
        (BAD_LEDGER_ONE_DIGIT, "a one-digit ledger row"),
        (BAD_LEGEND_PARTIAL, "a legend missing its no-third-value clause"),
    ],
)
def test_a_regressed_roadmap_would_fail_this_suite(document: str, label: str) -> None:
    """Silence on the real document is only evidence because these fire."""
    assert _all_document_findings(document) != [], label
