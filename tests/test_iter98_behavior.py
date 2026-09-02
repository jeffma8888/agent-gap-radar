"""Iteration 98 behaviours: the Done ledger admits iteration 100 and beyond.

WHAT THIS ITERATION CLAIMS, IN BEHAVIOURAL TERMS
`ledger_sequence_violations` used to judge a ledger iteration number by exact LENGTH two, so
`- iter 100` was a `not-two-digit` violation and the ledger could not record iteration 100.
The rule is now CANONICAL ZERO-PADDED FORM: a number is well formed when its raw text equals
its own value rendered with a minimum width of two. That admits `100` and every longer number
while still refusing `2` (unpadded) and `0100` (over-padded), and it leaves the published
vocabulary `not-two-digit` untouched.

WHY THIS IS A RELEASE PRECONDITION AND NOT A NICETY
Two committed tests DERIVE future ledger rows from the live document rather than hard-coding
them -- `test_iter62_behavior._future_rows` takes `ceiling + 1, ceiling + 2` and
`test_iter31_behavior.test_b8_the_floor_admits_a_later_well_formed_row` appends one more on top
of that -- so the chain reaches `live_max + 3`. With the live maximum at 98 that chain is
99, 100, 101, and under the old length rule every iteration from 97 onward was unshippable.
Behaviour 2 drives that REAL chain rather than a re-statement of it.

ISOLATION. This module honours the tester's isolation contract: it reads `pm.md`, this repo's
`tests/` conventions, and the product's own behaviour by CALLING its public interface. It does
not read `src/`, `tools/roadmap_integrity.py`, the engineer's or reviewer's notes,
`IMPLEMENTATION.patch`, or any diff. Every claim below is a call and an assertion on the
returned value.

ANTI-VACUITY -- WHY EVERY GREEN CLAIM CARRIES A CONTROL
`ledger_sequence_violations(text) == []` is the assertion this iteration is about, and it is
also the easiest assertion in the repo to pass for the wrong reason: a fixture whose rows the
row parser never RECOGNISES has no numbers to judge, so it is silent at any rule. So every
`== []` claim in this module first asserts, through `ledger_iterations`, exactly which raw
number texts were seen. And every admitted form is paired with a REFUSED near-neighbour built
from the same shape:

* behaviour 3 (`100` admitted) is paired with behaviour 4 (`0100` refused), which differs from
  it by one leading zero -- so a rule that had simply stopped checking anything would fail;
* behaviour 5 (`2` refused) is paired with the same VALUE in canonical form (`02` admitted), so
  the refusal is shown to be about the TEXT and not about the number being small;
* behaviour 7 (`98, 99, 100, 101` ascending) records the measurement that makes it
  discriminating: `"100" < "99"` is True as strings, so a text comparison would have reported
  `not-ascending` on that exact fixture.

ONE DELIBERATE NON-ASSERTION, NAMED SO A LATER ITERATION DOES NOT "FIX" IT
The `not-two-digit` kind NAME is now a slight misnomer for a canonical-form rule. Renaming it
is `Out of Scope` in `pm.md` and is a published vocabulary other modules pin, so behaviour 8
pins the tuple UNCHANGED on purpose.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Read PER CALL through this handle, never snapshotted at import time, so the iteration-62
#: durability sweep can repoint this module at a later ship commit's document.
ROADMAP = REPO_ROOT / "PRODUCT.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

#: The live ledger maximum at the time this iteration shipped. A FLOOR, never a ceiling: the
#: ledger only grows, so a later clean clone still satisfies every claim keyed on it.
LEDGER_MAX_AT_SHIP = 98


def _document(*rows: str) -> str:
    """A minimal roadmap whose ONLY ledger rows are `rows`, each given as the text that
    follows `- iter `."""
    body = "".join(f"- iter {row}\n" for row in rows)
    return f"# Roadmap\n\n## Done ledger\n\n{body}"


def _raw_numbers(text: str) -> list[str]:
    """The raw number TEXT of every row the product recognises as a ledger record.

    This is the anti-vacuity probe: it is what distinguishes "the judge saw these numbers and
    found nothing wrong" from "the judge was handed no numbers at all".
    """
    return [raw for raw, _ in ri.ledger_iterations(text)]


def _values(text: str) -> list[int]:
    return [value for _, value in ri.ledger_iterations(text)]


# ---------------------------------------------------------------------------
# Behaviour 1 -- the committed document, whose ledger now carries the row for this iteration
# ---------------------------------------------------------------------------


def test_b1_the_committed_ledger_is_admitted_by_the_sequence_judge() -> None:
    """Behaviour 1. The shipped `PRODUCT.md` yields no sequence violations.

    Zero-argument and reading through the module-level `ROADMAP` handle on purpose: that is the
    seam iteration 62's durability sweep repoints, so this pin is measured against a LATER ship
    commit's grown ledger as well as against the working tree's.
    """
    text = ROADMAP.read_text(encoding="utf-8")
    values = _values(text)

    assert len(values) >= 30, (
        f"anti-vacuity: the roadmap parsed as {len(values)} ledger row(s), so a silent judge "
        "would prove nothing"
    )
    assert max(values) >= LEDGER_MAX_AT_SHIP, (
        f"the ledger maximum {max(values)} is below the row this iteration ships"
    )
    assert ri.ledger_sequence_violations(text) == []


# ---------------------------------------------------------------------------
# Behaviour 2 -- the REAL derived-future-row chain, which is what reverted iteration 97
# ---------------------------------------------------------------------------


def test_b2_the_derived_future_row_chain_stays_green_across_the_hundred_boundary() -> None:
    """Behaviour 2. Two sparse rows above the live maximum, then one more above those.

    The helpers are the COMMITTED ones from iteration 62 and the append is iteration 31's, so
    this drives the chain that actually reds a clean clone rather than a re-statement of it.
    Imported inside the function: iteration 62 imports every module named in its sweep tuple at
    ITS import time, and a module-level import back into it would touch a partially initialised
    module.
    """
    import test_iter62_behavior as it62

    live = it62._live()
    grown = it62._grown(live)
    grown_values = _values(grown)
    derived = it62._future_rows(live)

    assert derived == [max(_values(live)) + 1, max(_values(live)) + 2], (
        f"premise: the derived rows must sit above the live ceiling, got {derived}"
    )
    assert max(derived) >= 100, (
        "premise: this behaviour is about crossing 100, and the derived rows "
        f"{derived} do not reach it -- the live ledger maximum is {max(_values(live))}"
    )
    assert _raw_numbers(grown)[-len(derived) :] == [f"{value:02d}" for value in derived], (
        "premise: the grown document's last rows are not the derived ones"
    )
    assert ri.ledger_sequence_violations(grown) == []

    last_line = it62._ledger_line(grown, max(grown_values))
    one_more = max(grown_values) + 1
    twice_grown = it62._mutate(
        grown, last_line, f"{last_line}\n- iter {one_more:02d} a later row"
    )

    assert one_more > 100, f"premise: the third derived row must be past 100, got {one_more}"
    assert _values(twice_grown) == grown_values + [one_more]
    assert ri.ledger_sequence_violations(twice_grown) == []


# ---------------------------------------------------------------------------
# Behaviours 3, 4, 5 -- the form rule, each admitted case paired with a refused neighbour
# ---------------------------------------------------------------------------


def test_b3_a_three_digit_row_after_two_digit_rows_is_admitted() -> None:
    """Behaviour 3. `- iter 100` following ascending two-digit rows is not a violation."""
    text = _document("98 a", "99 b", "100 c")

    assert _raw_numbers(text) == ["98", "99", "100"], "premise: the rows were not recognised"
    assert ri.ledger_sequence_violations(text) == []


def test_b4_an_over_padded_number_is_still_refused() -> None:
    """Behaviour 4. `0100` is exactly one `not-two-digit` finding -- the control for
    behaviour 3, differing from it by a single leading zero."""
    text = _document("0100 a")

    assert _raw_numbers(text) == ["0100"], "premise: the row was not recognised"
    assert ri.ledger_sequence_violations(text) == [("not-two-digit", "0100")]


def test_b5_a_bare_single_digit_number_is_still_refused() -> None:
    """Behaviour 5. `2` is exactly one `not-two-digit` finding -- unchanged."""
    text = _document("2 a")

    assert _raw_numbers(text) == ["2"], "premise: the row was not recognised"
    assert ri.ledger_sequence_violations(text) == [("not-two-digit", "2")]


def test_b5_the_same_value_in_canonical_form_is_admitted() -> None:
    """Control for behaviour 5: the refusal is about the TEXT, not about the value.

    `02` carries the same number as the refused `2` above and is admitted, so a rule that had
    started refusing small iterations outright would fail here.
    """
    text = _document("02 a")

    assert _values(text) == [2], "premise: the row was not recognised"
    assert ri.ledger_sequence_violations(text) == []


def test_b3_the_rule_admits_numbers_past_the_derived_chain_and_beyond() -> None:
    """Behaviour 3, the `and beyond` half of this iteration's claim.

    Behaviour 3 pins `100` and behaviour 2's derived chain reaches 101; measured on this
    worktree, NO test in the repo exercised a number past 101, so the roadmap headline
    "iteration 100 and beyond" was the one part of the claim nothing drove. A four-digit row is
    the case that separates a canonical-FORM rule from a widened LENGTH allowance: a judge that
    had been changed to admit two-or-three characters passes every other fixture here.
    """
    text = _document("98 a", "99 b", "100 c", "101 d", "1000 e")

    assert _raw_numbers(text) == ["98", "99", "100", "101", "1000"], (
        "premise: the rows were not recognised"
    )
    assert _values(text) == [98, 99, 100, 101, 1000]
    assert ri.ledger_sequence_violations(text) == []


def test_b4_an_over_padded_four_digit_number_is_refused() -> None:
    """The control for the test above, differing from it by one leading zero.

    Paired with it so the four-digit admission is shown to be canonical form rather than "any
    long number is fine now": `01000` carries the same VALUE as the admitted `1000`.
    """
    text = _document("01000 a")

    assert _raw_numbers(text) == ["01000"], "premise: the row was not recognised"
    assert _values(text) == [1000], "premise: the same value as the admitted four-digit row"
    assert ri.ledger_sequence_violations(text) == [("not-two-digit", "01000")]


def test_b5_a_zero_padded_two_digit_number_is_refused() -> None:
    """The canonical-form rule, measured on the mirror of behaviour 4.

    `099` carries the value 99, whose canonical form is `99`, so the leading zero is refused
    for the same reason `0100` is. Recorded because it is the case that shows the rule is
    canonical FORM rather than a hard-coded three-character allowance.
    """
    text = _document("099 a")

    assert _raw_numbers(text) == ["099"], "premise: the row was not recognised"
    assert ri.ledger_sequence_violations(text) == [("not-two-digit", "099")]


# ---------------------------------------------------------------------------
# Behaviours 6 and 7 -- the other two kinds still judge three-digit numbers, by VALUE
# ---------------------------------------------------------------------------


def test_b6_a_repeated_three_digit_row_is_a_duplicate() -> None:
    """Behaviour 6, first half. Admitting `100` must not stop the duplicate rule seeing it."""
    text = _document("100 a", "100 b")

    assert _raw_numbers(text) == ["100", "100"], "premise: the rows were not recognised"
    assert ri.ledger_sequence_violations(text) == [("duplicate", "100")]


def test_b6_a_descending_three_digit_pair_is_not_ascending() -> None:
    """Behaviour 6, second half. `100` then `99` descends and is reported on the LATER row."""
    text = _document("100 a", "99 b")

    assert _raw_numbers(text) == ["100", "99"], "premise: the rows were not recognised"
    assert ri.ledger_sequence_violations(text) == [("not-ascending", "99")]


def test_b7_ordering_compares_values_and_not_text() -> None:
    """Behaviour 7. `98, 99, 100, 101` is ascending.

    The measurement that makes this discriminating rather than decorative is on the second
    line: compared as TEXT, `100` sorts BELOW `99`, so a judge that had compared the raw
    strings would report `not-ascending` on this exact fixture.
    """
    assert "100" < "99", "premise: text order must disagree with value order here"

    text = _document("98 a", "99 b", "100 c", "101 d")

    assert _raw_numbers(text) == ["98", "99", "100", "101"], "premise: rows not recognised"
    assert _values(text) == [98, 99, 100, 101]
    assert ri.ledger_sequence_violations(text) == []


# ---------------------------------------------------------------------------
# Behaviour 8 -- the published vocabulary is unchanged
# ---------------------------------------------------------------------------


def test_b8_the_published_violation_kinds_are_unchanged() -> None:
    """Behaviour 8. Widening the form rule renames nothing.

    Pinned as an ordered tuple because other modules index this vocabulary, and paired with a
    sweep asserting no finding this module produced carries a kind outside it -- so the tuple
    is shown to be the real domain rather than a constant nobody consults.
    """
    assert ri.SEQUENCE_VIOLATION_KINDS == ("not-two-digit", "duplicate", "not-ascending")

    produced = {
        kind
        for text in (
            _document("0100 a"),
            _document("2 a"),
            _document("099 a"),
            _document("100 a", "100 b"),
            _document("100 a", "99 b"),
        )
        for kind, _ in ri.ledger_sequence_violations(text)
    }
    assert produced == set(ri.SEQUENCE_VIOLATION_KINDS), (
        f"the fixtures in this module exercise {sorted(produced)}, which does not cover the "
        f"published vocabulary {sorted(ri.SEQUENCE_VIOLATION_KINDS)}"
    )
