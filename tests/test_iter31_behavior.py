"""Iteration 31 behaviors: the Done ledger records iterations 30 and 31, roadmap row 60
reads `shipped`, and the re-landed walked-branch containment rule is LIVE.

Iteration 30 built the row-60 containment rule, earned `VERDICT: APPROVE` and
`RESULT: PASS`, and was reverted at the clean-clone pre-ship gate because no `- iter 30`
ledger row existed. Iteration 31 re-lands that payload unchanged and writes the two rows.
So this iteration has two claims, and this file measures both:

* the LEDGER claim (behaviors 7-9), which is what actually failed last time, and
* the PAYLOAD claim -- that the re-landed code is present and enforcing -- which is
  attested here INDEPENDENTLY of the re-landed `tests/test_iter30_behavior.py`, because
  "the payload came back" is not proved by a file that arrived in the same patch.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every claim is measured by CALLING a
public interface (`tools/roadmap_integrity`, `agent_gap_radar.checks`) over the committed
`PRODUCT.md` or over a fixture built under pytest's `tmp_path`.

Structural notes, so this file cannot lie later:

* **Every check over the live document is proved two-sided IN THIS FILE.** A pure function
  returning `[]` is evidence only when the same function is shown to fire, so each live
  assertion is paired with a known-bad fixture MUTATED FROM THE LIVE TEXT ITSELF, and every
  mutation asserts its own premise -- a silently no-op `replace` would turn a known-bad
  fixture into a copy of the good document and the test would pass measuring nothing.
* **Behavior 9 is asserted BOTH ways: against a SIMULATED ship list and against real git.**
  The simulated list `[1..31]` is the only form that can fail BEFORE this iteration's ship
  commit exists, and `test_b9_...can_fail...` proves it fires by extending the same list to
  `[1..32]`. The real `git log` cross-check asks the product's own one-directional judge,
  `unrecorded_ships`, so its verdict is IDENTICAL before and after any ship commit -- it is
  no longer a subset-of-a-literal-range claim, which was green by construction pre-commit
  and red from every later iteration's clean clone.
* **Nothing here is true only before the commit, and nothing here bounds the ledger ABOVE.**
  These tests must also pass from a clean clone of a LATER iteration's ship commit -- that
  gate reverted iteration 30, and iteration 60 died on these very pins -- so no assertion
  compares a ledger row count, a ledger value list or the real git ship list to a literal
  iteration number as an equality or a maximum. The historical run `1..31` is asserted as an
  ordered PREFIX over a floor that can only grow; values above it are governed solely by
  `ledger_sequence_violations`, which permits GAPS because an iteration that ships nothing
  writes no row.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__` and every fixture lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

from agent_gap_radar import checks

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

#: The iteration this file is named for, and its immediate predecessor. These remain the
#: file's SUBJECT -- the row-30 and row-31 witnesses below are keyed on them -- and they no
#: longer bound the ledger as a whole.
THIS_ITER = 31
PRIOR_ITER = 30

#: The ledger's HISTORICAL RUN: the iterations already recorded when this file was written.
#: A FLOOR and a PREFIX, never a ceiling. Later iterations append rows, and an iteration
#: that ships nothing appends none, so the live ledger may be both LONGER and SPARSE.
HISTORICAL_RUN: tuple[int, ...] = tuple(range(1, THIS_ITER + 1))


def _roadmap_text() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _mutate(text: str, old: str, new: str) -> str:
    """Replace `old` once, asserting it was there: guards against a vacuous fixture."""
    assert old in text, f"fixture premise broken: {old!r} is not in the live document"
    assert old != new, "fixture premise broken: the mutation changes nothing"
    return text.replace(old, new, 1)


def _table_row_line(text: str, row_id: str) -> str:
    """The one `| <id> | ... |` line for a roadmap row, asserted unique."""
    prefix = f"| {row_id} |"
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected exactly one row {row_id}, found {len(matches)}"
    return matches[0]


def _ledger_row_line(text: str, iteration: int) -> str:
    """The one `- iter NN ...` ledger line, asserted unique."""
    pattern = re.compile(rf"^- iter {iteration:02d}\b.*$", re.MULTILINE)
    matches = pattern.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one ledger row for iteration {iteration:02d}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _ledger_values(text: str) -> list[int]:
    """Done-ledger iteration values in file order."""
    return [value for _, value in ri.ledger_iterations(text)]


def _historical_shortfall(text: str) -> list[int]:
    """Historical iterations the ledger no longer records exactly once -- the SIZE claim.

    Stated as a floor over `HISTORICAL_RUN` rather than as a row COUNT so that it can only
    grow: a longer ledger is correct by construction, while a ledger that has LOST one of
    these rows names the loss. A pure function so a known-bad fixture can arm it.
    """
    values = _ledger_values(text)
    return [n for n in HISTORICAL_RUN if values.count(n) != 1]


def _historical_prefix(text: str) -> list[int]:
    """The first `len(HISTORICAL_RUN)` ledger values -- the ORDER claim, returned as data."""
    return _ledger_values(text)[: len(HISTORICAL_RUN)]


# ---------------------------------------------------------------------------
# Behavior 7 -- row 60's Status cell reads exactly `shipped`, and no cell holds
# a third vocabulary
# ---------------------------------------------------------------------------

def test_b7_row_60_status_cell_reads_exactly_shipped() -> None:
    """Behavior 7. The row whose payload this iteration lands is marked shipped.

    `shipped` is asserted EXACTLY, so `shipped (partly)` or a padded third value fails.
    """
    rows = dict(ri.table_rows(_roadmap_text()))
    assert rows, "anti-vacuity: no roadmap rows parsed, so the next assertion is empty"
    assert "60" in rows, f"row 60 is absent; parsed row ids: {sorted(rows)[:5]}..."
    status = rows["60"][2].strip()
    assert status == "shipped", f"row 60 Status cell reads {status!r}"


def test_b7_row_status_check_is_silent_over_the_live_roadmap() -> None:
    """Behavior 7. No cell was left holding a third vocabulary anywhere."""
    text = _roadmap_text()
    assert ri.table_rows(text), "anti-vacuity: no rows parsed, so this check is vacuous"
    violations = ri.row_status_violations(text)
    assert violations == [], "; ".join(v.message for v in violations)


def test_b7_row_status_check_fires_on_a_third_vocabulary_in_row_60() -> None:
    """Two-sided control for behavior 7, built by mutating the LIVE row 60.

    Without this, `row_status_violations() == []` over the real document is compatible
    with a parser that finds no rows at all.
    """
    text = _roadmap_text()
    good_line = _table_row_line(text, "60")
    assert "| shipped |" in good_line, "premise: row 60's status cell is `shipped`"
    bad_line = good_line.replace("| shipped |", "| iter 30 |", 1)
    bad_text = _mutate(text, good_line, bad_line)

    assert ri.row_status_violations(bad_text) == [("60", "iter 30")]
    message = ri.row_status_violations(bad_text)[0].message
    assert "60" in message and "iter 30" in message


# ---------------------------------------------------------------------------
# Behavior 8 -- exactly one ledger row for 30 and one for 31; the historical run 1..31
# is an ordered prefix over a growing floor, two-digit, unique and strictly ascending;
# and the row for 30 explains itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("iteration", [PRIOR_ITER, THIS_ITER])
def test_b8_ledger_holds_exactly_one_row_for_each_of_30_and_31(iteration: int) -> None:
    """Behavior 8. Counted over the WHOLE document: a duplicate anywhere is a broken
    record, and `unrecorded_ships` reports a twice-recorded iteration as unrecorded."""
    text = _roadmap_text()
    whole_file = len(re.findall(rf"^- iter {iteration:02d}\b", text, re.MULTILINE))
    assert whole_file == 1, f"`- iter {iteration:02d}` appears {whole_file} times"

    in_ledger = [it for it, _ in ri.ledger_iterations(text)].count(f"{iteration:02d}")
    assert in_ledger == 1, (
        f"the Done-ledger SECTION holds {in_ledger} rows for iteration {iteration:02d}"
    )


def test_b8_ledger_keeps_the_historical_run_as_an_ordered_prefix_over_a_growing_floor() -> None:
    """Behavior 8. The run 1..31 is intact and in order at the FRONT of the ledger, the
    ledger is allowed to be longer, and the sequence check is silent over the whole of it.

    Why the row count is now a floor and the order claim now covers only the historical run:
    an equality on the row count and a contiguity claim over the WHOLE ledger both bound the
    document by this file's own iteration number, so every LATER iteration's ship commit made
    its own clean clone RED. Floor and prefix are derived from the run this file WITNESSED,
    so they can only grow, and values above the run are governed by
    `ledger_sequence_violations` alone -- which permits gaps, because an iteration that ships
    nothing writes no row.
    """
    text = _roadmap_text()
    entries = ri.ledger_iterations(text)
    assert entries, "anti-vacuity: no ledger rows parsed, so every assertion below is empty"

    shortfall = _historical_shortfall(text)
    assert shortfall == [], (
        f"the ledger has lost historical rows {shortfall}: it may grow, never shrink"
    )
    assert len(entries) >= len(HISTORICAL_RUN), (
        f"expected at least {len(HISTORICAL_RUN)} ledger rows, found {len(entries)}: "
        f"{[it for it, _ in entries]}"
    )
    assert _historical_prefix(text) == list(HISTORICAL_RUN), (
        f"the historical run {HISTORICAL_RUN[0]}..{HISTORICAL_RUN[-1]} is not the ledger's "
        f"ordered prefix: {_historical_prefix(text)}"
    )

    violations = ri.ledger_sequence_violations(text)
    assert violations == [], "; ".join(v.message for v in violations)


def test_b8_the_floor_fires_when_a_historical_ledger_row_is_deleted() -> None:
    """Two-sided control for the SIZE claim, built by deleting a LIVE historical row.

    `_historical_shortfall() == []` over the real document is otherwise compatible with a
    helper that reads nothing at all.
    """
    text = _roadmap_text()
    victim = HISTORICAL_RUN[len(HISTORICAL_RUN) // 2]
    good_line = _ledger_row_line(text, victim)
    bad_text = _mutate(text, good_line + "\n", "")

    assert _historical_shortfall(bad_text) == [victim], (
        f"deleting the row for {victim:02d} produced {_historical_shortfall(bad_text)!r}"
    )
    assert len(ri.ledger_iterations(bad_text)) == len(ri.ledger_iterations(text)) - 1


def test_b8_the_floor_admits_a_later_well_formed_row() -> None:
    """The PASS side of the SIZE claim: a further row for a HIGHER iteration is accepted.

    This is the case the retired row-count equality rejected, and rejecting it is what
    reverted a green iteration from its own clean clone.
    """
    text = _roadmap_text()
    values = _ledger_values(text)
    later = max(values) + 1
    last_line = _ledger_row_line(text, max(values))
    grown = _mutate(text, last_line, f"{last_line}\n- iter {later:02d} a later row")

    assert _historical_shortfall(grown) == []
    assert _historical_prefix(grown) == list(HISTORICAL_RUN)
    assert ri.ledger_sequence_violations(grown) == []
    assert len(ri.ledger_iterations(grown)) == len(values) + 1


def test_b8_the_prefix_claim_fires_when_two_historical_rows_are_transposed() -> None:
    """Two-sided control for the ORDER claim, built by transposing two LIVE historical rows.

    Order is what survives of the retired contiguity pin, so it needs its own armed control.
    `ledger_sequence_violations` would also catch this transposition; the point here is that
    the PREFIX check catches it independently.
    """
    text = _roadmap_text()
    first, second = HISTORICAL_RUN[6], HISTORICAL_RUN[7]
    line_a = _ledger_row_line(text, first)
    line_b = _ledger_row_line(text, second)
    bad_text = _mutate(text, f"{line_a}\n{line_b}", f"{line_b}\n{line_a}")

    prefix = _historical_prefix(bad_text)
    assert prefix != list(HISTORICAL_RUN), "transposition left the prefix unchanged"
    assert prefix.index(second) < prefix.index(first)
    assert _historical_shortfall(bad_text) == [], "premise: no row was lost, only reordered"


def test_b8_sequence_check_fires_on_a_duplicated_live_iteration_31_row() -> None:
    """Two-sided control for behavior 8, built by duplicating the LIVE `- iter 31` row."""
    text = _roadmap_text()
    good_line = _ledger_row_line(text, THIS_ITER)
    bad_text = _mutate(text, good_line, good_line + "\n" + good_line)

    violations = ri.ledger_sequence_violations(bad_text)
    assert ("duplicate", f"{THIS_ITER:02d}") in violations, (
        f"a duplicated row 31 produced {list(violations)!r}"
    )
    for violation in violations:
        assert violation.kind in ri.SEQUENCE_VIOLATION_KINDS
        assert violation.iteration in violation.message


def test_b8_the_iteration_30_row_explains_a_ship_commit_that_never_landed() -> None:
    """Behavior 8. The ledger is the ONLY place a failed iteration can be explained,
    because `unrecorded_ships` is one-directional -- so the row for 30 must say that the
    payload was built, reviewed and tested green and was reverted for a missing row.

    Asserted on required TOKENS rather than on a pinned sentence: the substance is
    contractual, the wording is the PM's.
    """
    text = _roadmap_text()
    assert "one-directional" in text, (
        "premise: the ledger preamble states why a failed iteration must self-explain"
    )
    row = _ledger_row_line(text, PRIOR_ITER)
    lowered = row.lower()

    assert "approve" in lowered, f"row 30 does not record the review verdict: {row!r}"
    assert "pass" in lowered, f"row 30 does not record the test verdict: {row!r}"
    assert "revert" in lowered, f"row 30 does not record that it was reverted: {row!r}"
    assert "ledger row" in lowered, (
        f"row 30 does not name the missing ledger row as the cause: {row!r}"
    )
    assert any(token in lowered for token in ("clean-clone", "clean clone",
                                              "fresh checkout", "clean checkout")), (
        f"row 30 does not name the gate that reverted it: {row!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 9 -- no shipped iteration lacks a ledger row, asserted against BOTH a
# simulated ship list and the real `git log`, via `unrecorded_ships`
# ---------------------------------------------------------------------------

def test_b9_simulated_full_ship_list_reports_no_unrecorded_ship() -> None:
    """Behavior 9. `unrecorded_ships(text, [1..31]) == []`."""
    missing = ri.unrecorded_ships(_roadmap_text(), list(range(1, THIS_ITER + 1)))
    assert missing == [], "; ".join(ri.unrecorded_ship_messages(missing))


def test_b9_the_simulated_check_can_fail_over_this_very_document() -> None:
    """Two-sided control for behavior 9. Extending the same list by one iteration that
    has no row MUST produce a finding, or the assertion above proves nothing."""
    text = _roadmap_text()
    beyond = THIS_ITER + 1
    assert ri.unrecorded_ships(text, list(range(1, beyond + 1))) == [beyond]
    assert f"{beyond:02d}" in ri.unrecorded_ship_messages([beyond])[0]


def test_b9_every_iteration_git_calls_shipped_has_exactly_one_ledger_row() -> None:
    """Behavior 9 against REAL git, asked through the product's own one-directional judge.

    The retired form subtracted the real ship set from a literal range, which is a MAXIMUM:
    it could not fail before iteration 31's ship commit existed and it went RED from the
    clean clone of every later iteration that shipped. `unrecorded_ships` asks the only
    question the ledger owes an answer to -- does each shipped iteration have exactly one
    row -- so its verdict is IDENTICAL on both sides of any ship commit, including this
    iteration's own. It still SKIPs, with a stated reason, when git cannot be asked.
    """
    ships = ri.shipped_iterations_from_git(REPO_ROOT)
    if ships.iterations is None:
        pytest.skip(f"cannot ask git: {ships.skip_reason}")
    if not ships.iterations:
        pytest.skip("no ship commits in this history: the comparison has nothing to say")
    missing = ri.unrecorded_ships(_roadmap_text(), ships.iterations)
    assert missing == [], "; ".join(ri.unrecorded_ship_messages(missing))


def test_b9_the_real_git_cross_check_can_fail_over_this_very_document() -> None:
    """Two-sided control for the derived cross-check: the REAL ship list plus one synthetic
    iteration that has no ledger row must name exactly that iteration.

    Without this, a silent `unrecorded_ships(text, real_ships)` is compatible with a ledger
    reader that returns nothing, and the relaxation would have traded a landmine for a check
    that cannot fail at all.
    """
    ships = ri.shipped_iterations_from_git(REPO_ROOT)
    if ships.iterations is None:
        pytest.skip(f"cannot ask git: {ships.skip_reason}")
    text = _roadmap_text()
    synthetic = max([*ships.iterations, *_ledger_values(text)]) + 1
    assert ri.unrecorded_ships(text, [synthetic]) == [synthetic], (
        f"premise: iteration {synthetic:02d} must have no ledger row"
    )
    assert ri.unrecorded_ships(text, [*ships.iterations, synthetic]) == [synthetic]
    assert f"{synthetic:02d}" in ri.unrecorded_ship_messages([synthetic])[0]


# ---------------------------------------------------------------------------
# The PAYLOAD claim -- an INDEPENDENT witness that the re-landed containment rule
# is live, measured by a reference-walk differential
# ---------------------------------------------------------------------------

def _escaping_tree(root: pathlib.Path) -> pathlib.Path:
    """A NON-GIT target holding `pkg/inside.py` plus a `pkg/escape.py` symlink whose
    `resolve()` lands outside the target root."""
    outside = root / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("# outside the target\n", encoding="utf-8")

    target = root / "target"
    (target / "pkg").mkdir(parents=True)
    (target / "pkg" / "inside.py").write_text("# inside the target\n", encoding="utf-8")
    (target / "pkg" / "escape.py").symlink_to(outside / "secret.py")
    return target


def test_payload_relanded_walked_containment_is_live_by_reference_walk(
    tmp_path: pathlib.Path,
) -> None:
    """The re-landed rule, attested WITHOUT reading the re-landed test file.

    The differential is what makes this falsifiable: a bare `Path.glob("**/*.py")` over
    the SAME fixture must surface BOTH entries, so the escaping file is provably
    discoverable and pattern-matching, and its absence from `iter_files` is attributable
    to the containment rule rather than to a walk that returned nothing. The
    non-escaping sibling must still be PRESENT, so the guard cannot pass by rejecting
    everything.
    """
    target = _escaping_tree(tmp_path)

    # premises: the target is NOT a git target, and the entry really does escape
    assert checks.tracked_files(target) is None, (
        "premise: this fixture must take the WALKED branch, not the tracked one"
    )
    link = target / "pkg" / "escape.py"
    assert link.is_symlink(), "premise: the escaping entry must be a symlink"
    assert link.is_file(), "premise: the symlink must resolve to a readable file"
    assert not link.resolve().is_relative_to(target.resolve()), (
        "premise: the symlink must resolve OUTSIDE the target root"
    )

    reference = sorted(
        str(p.relative_to(target)) for p in target.glob("**/*.py") if p.is_file()
    )
    assert reference == ["pkg/escape.py", "pkg/inside.py"], (
        f"control: a plain glob walk must see both entries, saw {reference}"
    )

    got = sorted(
        str(pathlib.Path(p).relative_to(target))
        for p in checks.iter_files(target, ["**/*.py"])
    )
    assert got == ["pkg/inside.py"], (
        f"walked enumeration returned {got}: the escaping entry must be absent and the "
        "in-root sibling present"
    )
