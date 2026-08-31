"""Iteration 90 behaviors: the harness that PROVES this suite can fail becomes reachable
from the release path.

`tools/verify_mutations.py` is this product's only evidence that `uv run pytest` can go
red -- it plants 20 real defects one at a time and requires a named test to fail. Until this
iteration nothing in the suite touched it, so a refactor that retired an anchor, or a
cap-killed run that left a planted defect in a tracked file, could disarm it silently. These
tests bind its pre-flight to the suite: `anchor_defects`, `residue_defects` and
`oracle_defects` are asserted two-sided over synthetic mutation lists this file owns, then
asserted SILENT against the live tree.

ISOLATION CONTRACT HONORED. Nothing here reads `src/` or `tools/` implementation text, the
engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured by CALLING
or INTROSPECTING the public interface -- `verify_mutations.read_source`, `.anchor_defects`,
`.residue_defects`, `.oracle_defects`, `.main`, `.MUTATIONS`, `.REPO` -- over literal strings
and stub callables declared in this module.

STRUCTURAL NOTES, so this file cannot lie later:

* **The message texts are the contract, so they are quoted ONCE each as a module constant**
  and asserted with `==` against a whole message, never against a positional token of one.
  Index arithmetic over a formatted string is a second, unverified copy of that format: it
  can only agree with the real message by luck, and when it disagrees the accusation lands on
  correct code.
* **Behavior 7 drives a tool that MUTATES TRACKED FILES, so the test double is a write
  vector and is treated as one.** The patched reader returns text in which NO anchor resolves
  at all, which is the one substitution that cannot survive the pre-flight; a reader whose
  text resolved an anchor exactly once would make `main()` write the substitution back over a
  tracked file. Two tripwires are armed for EVERY test in this module before any of them
  runs -- `subprocess.run` and `Path.write_text` both raise -- so if a future refactor stops
  honouring the bare-name `read_source` seam and `main()` sails past its pre-flight into the
  planting loop, that surfaces as a loud failure here instead of a mutated repository. One
  test proves both tripwires are actually armed rather than merely installed.
* **Behavior 7's oracle is built from `MUTATIONS` data plus the spec's message text**, not
  from what the tool happened to print: the expected stderr line is composed from
  `MUTATIONS[0]`'s own name and file, so a `main()` that hardcoded `return 2` or reported a
  different entry cannot pass.
* **Behavior 7 asserts the seam BITES, not merely that the exit code is 2.** The stub reader
  records every path it is handed, and that record must be non-empty -- the falsifiable form
  of "resolved as a module attribute". Without it, a `main()` that ignored the patch and read
  the real files would return 0 and the test would still be free to claim the seam works.
* **The pre-flight WIRING is pinned separately from its verdict.** One test substitutes
  `anchor_defects` itself with a stub returning an invented message and requires that message
  on stderr, so "the pre-flight runs through `anchor_defects`" is asserted rather than assumed;
  a `main()` keeping its own inline count would fall through to the planting loop and trip the
  wires instead of passing quietly.
* **The live-tree assertions are the brake and they start GREEN.** They assert the harness is
  ARMED (every anchor resolves exactly once, no mutated form is on disk, every oracle file
  exists), never that it still CATCHES: running the 20 planted defects is out of scope, and
  this module never claims that coverage.
* **No test here spawns a subprocess, writes any file, or reaches the network.** Every
  mutation list except the live one is synthetic, and its file names (`a.py`, `b.py`, `c.py`)
  are never opened -- they are only ever keys handed to a stub reader.
* **No absolute machine path and no personal or employer identifier appears here.** The repo
  root is derived from `__file__`.
"""

from __future__ import annotations

import hashlib
import inspect
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

import verify_mutations  # noqa: E402

# --- the spec's synthetic mutation list and its message texts, verbatim -------------------

SYNTHETIC = [("m1", "a.py", "ANCHOR", "MUTANT", "tests/t.py")]

ANCHOR_MSG_0 = "anchor for m1 occurs 0 times in a.py"
ANCHOR_MSG_2 = "anchor for m1 occurs 2 times in a.py"
RESIDUE_MSG = "mutated form of m1 is present in a.py"
ORACLE_MSG = "oracle test file tests/t.py for m1 is missing"

# The one substitution that cannot survive the pre-flight: no anchor resolves in it.
NO_ANCHOR_TEXT = "this stub text holds no anchor of any kind"


def _live_files() -> list[str]:
    """Every distinct file named in the LIVE mutation list."""
    return sorted({m[1] for m in verify_mutations.MUTATIONS})


def _shas() -> dict[str, str]:
    return {
        rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in _live_files()
    }


def _exists(rel: str) -> bool:
    """The real oracle-existence seam: resolve a repo-relative path against the repo root."""
    return (REPO / rel).exists()


@pytest.fixture(autouse=True)
def _no_writes_and_no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nail both doors the planting loop needs, for every test in this module."""

    def _boom_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test in this module reached subprocess.run")

    def _boom_write(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test in this module reached Path.write_text")

    monkeypatch.setattr(verify_mutations.subprocess, "run", _boom_run)
    monkeypatch.setattr(verify_mutations.Path, "write_text", _boom_write)


def test_the_two_tripwires_are_armed_not_merely_installed(tmp_path: Path) -> None:
    """A tripwire nobody proves is a tripwire nobody has."""
    assert verify_mutations.subprocess is subprocess
    assert verify_mutations.Path is pathlib.Path
    with pytest.raises(AssertionError):
        verify_mutations.subprocess.run(["/nonexistent-by-design"])
    with pytest.raises(AssertionError):
        (tmp_path / "never-written.txt").write_text("x", encoding="utf-8")
    assert not (tmp_path / "never-written.txt").exists()


# --- behavior 1: the exposed surface -----------------------------------------------------


def test_b1_the_four_names_are_exposed_with_the_specified_signatures() -> None:
    for name in ("read_source", "anchor_defects", "residue_defects", "oracle_defects"):
        assert callable(getattr(verify_mutations, name, None)), name

    assert list(inspect.signature(verify_mutations.read_source).parameters) == ["rel"]
    assert list(inspect.signature(verify_mutations.anchor_defects).parameters) == [
        "mutations",
        "read",
    ]
    assert list(inspect.signature(verify_mutations.residue_defects).parameters) == [
        "mutations",
        "read",
    ]
    assert list(inspect.signature(verify_mutations.oracle_defects).parameters) == [
        "mutations",
        "exists",
    ]


def test_b1_read_source_returns_the_utf8_text_of_a_repo_relative_path() -> None:
    for rel in ("README.md", "VISION.md"):
        assert verify_mutations.read_source(rel) == (REPO / rel).read_text(encoding="utf-8")


def test_b1_the_predicates_accept_any_iterable_and_return_a_list() -> None:
    assert verify_mutations.anchor_defects((m for m in SYNTHETIC), lambda rel: "x y") == [
        ANCHOR_MSG_0
    ]
    assert verify_mutations.residue_defects(
        (m for m in SYNTHETIC), lambda rel: "x MUTANT y"
    ) == [RESIDUE_MSG]
    assert verify_mutations.oracle_defects((m for m in SYNTHETIC), lambda rel: False) == [
        ORACLE_MSG
    ]
    for empty in (
        verify_mutations.anchor_defects([], lambda rel: ""),
        verify_mutations.residue_defects([], lambda rel: ""),
        verify_mutations.oracle_defects([], lambda rel: True),
    ):
        assert isinstance(empty, list) and empty == []


def test_b1_the_predicates_write_nothing_and_spawn_nothing() -> None:
    """Purity, measured: the tripwires above are armed and the tree does not move."""
    before = _shas()
    verify_mutations.anchor_defects(SYNTHETIC, lambda rel: "x y")
    verify_mutations.residue_defects(SYNTHETIC, lambda rel: "x MUTANT y")
    verify_mutations.oracle_defects(SYNTHETIC, lambda rel: False)
    assert _shas() == before


# --- behavior 2: anchor resolution, both directions ---------------------------------------


def test_b2_anchor_defects_is_silent_when_the_anchor_resolves_exactly_once() -> None:
    assert verify_mutations.anchor_defects(SYNTHETIC, lambda rel: "x ANCHOR y") == []


def test_b2_anchor_defects_reports_a_vanished_anchor() -> None:
    assert verify_mutations.anchor_defects(SYNTHETIC, lambda rel: "x y") == [ANCHOR_MSG_0]


def test_b2_anchor_defects_reports_a_duplicated_anchor() -> None:
    assert verify_mutations.anchor_defects(SYNTHETIC, lambda rel: "ANCHOR and ANCHOR") == [
        ANCHOR_MSG_2
    ]


# --- behavior 3: residue, both directions -------------------------------------------------


def test_b3_residue_defects_is_silent_on_an_unmutated_file() -> None:
    assert verify_mutations.residue_defects(SYNTHETIC, lambda rel: "x ANCHOR y") == []


def test_b3_residue_defects_reports_a_planted_defect_left_on_disk() -> None:
    assert verify_mutations.residue_defects(SYNTHETIC, lambda rel: "x MUTANT y") == [
        RESIDUE_MSG
    ]


def test_b3_residue_defects_reports_one_message_per_mutation_not_per_occurrence() -> None:
    assert verify_mutations.residue_defects(SYNTHETIC, lambda rel: "MUTANT MUTANT") == [
        RESIDUE_MSG
    ]


# --- behavior 4: oracle existence, both directions ----------------------------------------


def test_b4_oracle_defects_is_silent_when_the_oracle_file_exists() -> None:
    assert verify_mutations.oracle_defects(SYNTHETIC, lambda rel: True) == []


def test_b4_oracle_defects_reports_a_missing_oracle_file() -> None:
    assert verify_mutations.oracle_defects(SYNTHETIC, lambda rel: False) == [ORACLE_MSG]


# --- behavior 5: ordering and arity --------------------------------------------------------

THREE = [
    ("m1", "a.py", "A1", "X1", "tests/t1.py"),
    ("m2", "b.py", "A2", "X2", "tests/t2.py"),
    ("m3", "c.py", "A3", "X3", "tests/t3.py"),
]


def test_b5_all_three_predicates_report_in_the_order_the_mutations_were_given() -> None:
    assert verify_mutations.anchor_defects(THREE, lambda rel: "nothing here") == [
        "anchor for m1 occurs 0 times in a.py",
        "anchor for m2 occurs 0 times in b.py",
        "anchor for m3 occurs 0 times in c.py",
    ]
    mutated = {"a.py": "X1", "b.py": "X2", "c.py": "X3"}
    assert verify_mutations.residue_defects(THREE, lambda rel: mutated[rel]) == [
        "mutated form of m1 is present in a.py",
        "mutated form of m2 is present in b.py",
        "mutated form of m3 is present in c.py",
    ]
    assert verify_mutations.oracle_defects(THREE, lambda rel: False) == [
        "oracle test file tests/t1.py for m1 is missing",
        "oracle test file tests/t2.py for m2 is missing",
        "oracle test file tests/t3.py for m3 is missing",
    ]


def test_b5_a_healthy_entry_between_two_broken_ones_is_skipped_not_shifted() -> None:
    """`at most one message per mutation` has to mean healthy entries produce NONE."""
    text = {"a.py": "no anchor", "b.py": "A2 appears once", "c.py": "no anchor"}
    assert verify_mutations.anchor_defects(THREE, lambda rel: text[rel]) == [
        "anchor for m1 occurs 0 times in a.py",
        "anchor for m3 occurs 0 times in c.py",
    ]
    assert verify_mutations.oracle_defects(THREE, lambda rel: rel == "tests/t2.py") == [
        "oracle test file tests/t1.py for m1 is missing",
        "oracle test file tests/t3.py for m3 is missing",
    ]


# --- behavior 6: silent against the LIVE tree ---------------------------------------------


def test_b6_the_live_mutation_list_has_at_least_20_well_shaped_entries() -> None:
    assert len(verify_mutations.MUTATIONS) >= 20
    for entry in verify_mutations.MUTATIONS:
        assert isinstance(entry, tuple), entry
        assert len(entry) == 5, entry
        assert all(isinstance(field, str) for field in entry), entry


def test_b6_the_harness_is_armed_against_the_live_tree() -> None:
    """The brake itself: every anchor resolves once, no residue on disk, every oracle there."""
    assert verify_mutations.REPO == REPO
    assert (
        verify_mutations.anchor_defects(verify_mutations.MUTATIONS, verify_mutations.read_source)
        == []
    )
    assert (
        verify_mutations.residue_defects(
            verify_mutations.MUTATIONS, verify_mutations.read_source
        )
        == []
    )
    assert verify_mutations.oracle_defects(verify_mutations.MUTATIONS, _exists) == []


def test_b6_running_all_three_against_the_live_tree_moves_no_byte_of_it() -> None:
    before = _shas()
    assert before, "the live mutation list must name at least one file"
    verify_mutations.anchor_defects(verify_mutations.MUTATIONS, verify_mutations.read_source)
    verify_mutations.residue_defects(verify_mutations.MUTATIONS, verify_mutations.read_source)
    verify_mutations.oracle_defects(verify_mutations.MUTATIONS, _exists)
    assert _shas() == before


# --- behavior 7: main() still fails closed, now testably ----------------------------------


def test_b7_main_fails_closed_on_a_drifted_anchor_without_touching_a_tracked_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _shas()
    seen: list[str] = []

    def _reader(rel: str) -> str:
        seen.append(rel)
        return NO_ANCHOR_TEXT

    monkeypatch.setattr(verify_mutations, "read_source", _reader)

    rc = verify_mutations.main([])
    captured = capsys.readouterr()

    assert rc == 2
    # The seam BITES: the substitution was reached by bare-name lookup.
    assert seen, "main() never called read_source as a module attribute"

    # Oracle built from MUTATIONS data plus the spec's message text, not from the output.
    name0, rel0 = verify_mutations.MUTATIONS[0][0], verify_mutations.MUTATIONS[0][1]
    expected = f"Error: anchor for {name0} occurs 0 times in {rel0}"
    assert captured.err == expected + "\n"
    assert len(captured.err.splitlines()) == 1
    assert captured.out == ""

    # Nothing on disk moved, and the tripwires above prove nothing was planted or shelled out.
    assert _shas() == before


def test_b7_the_preflight_routes_through_anchor_defects_by_bare_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The acceptance criterion says the pre-flight RUNS THROUGH `anchor_defects`.

    Substituting the module attribute is the falsifiable form: a `main()` that kept its own
    inline anchor count would read the healthy live tree, find nothing wrong, and fall through
    into the planting loop -- where the autouse tripwires stop it loudly. So this test cannot
    pass by accident in either direction, and it writes nothing either way.
    """
    before = _shas()
    sentinel = "anchor for a_mutation_this_test_invented occurs 0 times in nowhere.py"

    def _stub(*args: object, **kwargs: object) -> list[str]:
        return [sentinel]

    monkeypatch.setattr(verify_mutations, "anchor_defects", _stub)

    rc = verify_mutations.main([])
    captured = capsys.readouterr()

    assert rc == 2
    assert captured.err == f"Error: {sentinel}\n"
    assert captured.out == ""
    assert _shas() == before


# --- behavior 8: --list is unchanged ------------------------------------------------------


def test_b8_list_returns_zero_and_prints_one_line_per_mutation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = verify_mutations.main(["--list"])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == len(verify_mutations.MUTATIONS)
    for line, (name, rel, _old, _new, test) in zip(
        lines, verify_mutations.MUTATIONS, strict=True
    ):
        assert name in line, line
        assert rel in line, line
        assert test in line, line


# --- live-data controls: the synthetic fixtures above are NOT in the discriminating range --
#
# Behaviors 2-5 are driven by the spec's synthetic list, whose anchor is the literal
# `"ANCHOR"`. That string is regex-safe, single-line and 6 characters long, so it passes
# under a counting implementation that is literal AND under one that is pattern-based --
# a control that cannot separate the two proves nothing about either. Measured against the
# LIVE list in this stage: 17 of 20 real anchors contain regex metacharacters, 8 are
# multi-line, their lengths run 20-155 characters, TWO are not valid regexes at all, and 15
# of 20 would report a different count under `re.findall` than under `str.count` in a text
# holding the anchor twice. So the tests below re-run behaviors 2-4 over every real entry,
# where the two readings genuinely diverge.
#
# Every reader here is still a stub over strings built from `MUTATIONS` data. Nothing is
# opened, nothing is written, and the live files are never handed to the tool -- so these
# controls cost no I/O and cannot mutate the repository.


def test_b2_live_anchor_counting_is_literal_over_every_real_anchor() -> None:
    for name, rel, old, _new, _test in verify_mutations.MUTATIONS:
        doubled = old + "\n\n" + old
        # The fixture asserts its OWN precondition, so a text that failed to hold the anchor
        # exactly twice can never be mistaken for a defect in the predicate.
        assert doubled.count(old) == 2, name

        assert verify_mutations.anchor_defects([(name, rel, old, _new, _test)], lambda r: old) == [], name
        assert verify_mutations.anchor_defects(
            [(name, rel, old, _new, _test)], lambda r: doubled
        ) == [f"anchor for {name} occurs 2 times in {rel}"], name


def test_b3_live_residue_detection_is_literal_over_every_real_mutation() -> None:
    for name, rel, old, new, test in verify_mutations.MUTATIONS:
        # Measured precondition: no entry's mutated form occurs inside its own anchor, so an
        # anchor-only text is a real negative control rather than an accidental positive.
        assert new not in old, name

        assert verify_mutations.residue_defects([(name, rel, old, new, test)], lambda r: old) == [], name
        assert verify_mutations.residue_defects(
            [(name, rel, old, new, test)], lambda r: new
        ) == [f"mutated form of {name} is present in {rel}"], name


def test_b4_live_oracle_message_names_the_real_oracle_path() -> None:
    for entry in verify_mutations.MUTATIONS:
        name, _rel, _old, _new, test = entry
        assert verify_mutations.oracle_defects([entry], lambda r: True) == [], name
        assert verify_mutations.oracle_defects([entry], lambda r: False) == [
            f"oracle test file {test} for {name} is missing"
        ], name


def test_b5_every_broken_anchor_is_reported_in_mutations_order_not_file_order() -> None:
    """The spec's accepted diagnostic change, pinned so it cannot regress silently.

    `MUTATIONS` interleaves its three files: measured in this stage, the file sequence forms
    SIX consecutive runs over THREE distinct files (promote x9, verify_quotes x5, cli x1,
    promote x1, verify_quotes x2, promote x2). A pre-flight that walked FILES and then the
    mutations within each file could produce at most three runs, so it can never reproduce
    the sequence below -- which is what makes this a real test of "reports the earliest
    `MUTATIONS` entry" rather than a restatement of it.
    """
    expected = [
        f"anchor for {name} occurs 0 times in {rel}"
        for name, rel, _old, _new, _test in verify_mutations.MUTATIONS
    ]
    got = verify_mutations.anchor_defects(
        verify_mutations.MUTATIONS, lambda rel: NO_ANCHOR_TEXT
    )
    assert got == expected
    assert len(got) == len(verify_mutations.MUTATIONS)


def test_b6_the_live_mutation_data_is_not_vacuous() -> None:
    """Beyond the literal spec (behavior 6 fixes shape and arity only), and stated as such.

    A harness entry whose mutated form EQUALS its anchor plants nothing, so its oracle test
    can never go red and the entry is a permanent silent pass -- the same fail-open shape as
    a mitigation credited to a test that merely names a pattern. All four properties below
    were measured true against the live list before being asserted, so this starts green and
    is a brake, not a fix.
    """
    names = [e[0] for e in verify_mutations.MUTATIONS]
    assert len(set(names)) == len(names), "a duplicate name makes a CAUGHT report ambiguous"
    for name, _rel, old, new, test in verify_mutations.MUTATIONS:
        assert old, name
        assert new, name
        assert new != old, f"{name} plants a defect identical to the original"
        assert test.startswith("tests/"), name
