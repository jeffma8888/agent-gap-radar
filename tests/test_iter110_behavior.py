"""Iteration 110 behaviors: `list --json` publishes `strongest_source` and `needs`.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every shape claim was measured by
RUNNING the tool (`radar --help`, `radar list --help`, `radar list . --json` at floors 2
and 6, `radar report . --floor 5` and `--floor 6`, `radar taxonomy`) or by reading files
under `tests/` as data. The two oracles are IMPORTED and CALLED as functions, which is what
the spec names as the oracle; their bodies were not read.

Structural notes, so this file cannot lie later:

* **The key-order claim is spelled ONCE.** `RECORD_KEYS` is DERIVED as
  `PRE_EXISTING_RECORD_KEYS + ["strongest_source", "needs"]`, so one passing assertion
  proves both halves at once: every pre-existing key keeps its absolute index, and the two
  new keys are last, in that order. There is no second literal that can drift.
* **No live-register count and no live per-id value is pinned.** `gaps/` is grown by an
  unattended research pass, so a keyed expectation over it would red on a CORRECT register.
  Live tests assert only properties that must hold for ANY register, and each guards
  against a vacuous domain (empty record list, single-valued census) FIRST.
* **Both sides of every biconditional are exercised.** Behaviors 3 and 5 sweep floors 0..6
  and then ASSERT that both branches were actually observed, so an implementation that
  always emits `null`, always emits `[]`, or always emits a non-empty array fails.
* **The ladder is IMPORTED, never written down.** `CLASSES` / `RUNG` come from
  `tests/test_iter07_behavior.py`, which parses them out of `radar taxonomy`'s own output,
  so a ladder change lands here without an edit.
* **The "not alphabet" claims are two-sided by construction.** A synthetic record is built
  whose alphabetically-first AND alphabetically-last citation class are both the WRONG
  answer, and a synthetic floor is chosen at which the correct `needs` order is NOT the
  alphabetical order.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every synthetic register is built under pytest's `tmp_path`.

ONE SPEC AMBIGUITY, also carried in the tester report: behavior 7 says the strings
`strongest_source` / `needs` "appear in no markdown document". Taken as a bare substring
that is FALSE on a correct tree -- `radar list .` and `radar report .` both contain the
lowercase word `needs` inside a committed record's own prose ("...exfiltration needs no
tool call..."). The reasonable reading, tested here, is that the machine KEY spellings did
not leak: `strongest_source` in any spelling, and `needs` in its quoted JSON-key form.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import promotion_options, strongest_source
from test_iter02_behavior import _record, _write_register
from test_iter07_behavior import CLASSES, RUNG, WEIGHT

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: The live register, loaded once through the public loader. Used only for properties.
LIVE = load_all(GAPS_DIR)

#: The register default floor `list` applies when `--floor` is absent (from
#: `radar list --help`: "confidence floor for the ranking (default 2)").
DEFAULT_FLOOR = 2

#: Behavior 1. The eight per-record keys that pre-date this iteration, in emitted order.
PRE_EXISTING_RECORD_KEYS = [
    "gap_id", "title", "layer", "gap_type", "status", "priority", "confidence",
    "below_floor",
]
#: ...and the whole ordered set after this iteration APPENDS two. Derived, never re-typed.
RECORD_KEYS = PRE_EXISTING_RECORD_KEYS + ["strongest_source", "needs"]

#: Behavior 1. The top-level and `counts` shapes, which this iteration must NOT touch.
TOP_LEVEL_KEYS = ["confidence_floor", "counts", "records"]
COUNTS_KEYS = ["total", "ranked", "below_floor"]

#: Behavior 4/5. The floors swept. 6 exceeds the maximum reachable confidence (the ladder's
#: top weight, asserted below), so it is the unreachable case; 0 admits everything.
FLOORS = (0, 1, 2, 3, 4, 5, 6)
UNREACHABLE_FLOOR = 6

#: Behavior 4. The class the prescription may never propose.
FORBIDDEN_CLASS = "model-output"

#: Behavior 7. The markdown/JSON key spellings that must not leak into a document.
LEAKED_SPELLINGS = ("strongest_source", '"needs"')

#: Behavior 7. The two `Needs` cell wordings the markdown table must keep.
NEEDS_CELL_REACHABLE_PREFIX = "weight >= "
NEEDS_CELL_UNREACHABLE = "no single citation reaches floor {floor}"
BELOW_FLOOR_HEADING = "## Below confidence floor"


# --------------------------------------------------------------------------- helpers

def _run(argv: list[str]) -> tuple[int, str, str]:
    """Drive the CLI in-process; observe only exit code, stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _payload(argv: list[str]) -> dict:
    code, out, err = _run(argv)
    assert code == 0, (argv, code, err)
    assert err == "", (argv, err)
    return json.loads(out)


def _live_list_json(*extra: str) -> dict:
    return _payload(["list", str(REPO_ROOT), "--json", *extra])


def _by_id(records) -> dict:
    return {gap.id: gap for gap in records}


def _weak_register(root) -> str:
    """A register whose ONE record is below the default floor with a reachable remedy.

    A lone `secondary-summary` citation is the register's weakest non-zero rung, so the
    record is below the default floor at floor 2 (remedy reachable => non-empty `needs`)
    and still below it at floor 6 (no single citation reaches it => `needs == []`). The
    same fixture therefore exercises BOTH array cases, which is what behavior 5 demands.
    """
    _write_register(root, [_record("GAP-901", classes=("secondary-summary",))])
    return str(root)


def _mixed_register(root) -> str:
    """A register whose record makes both alphabetical readings of behavior 2 wrong.

    Citation classes `first-party-field`, `incident-postmortem`, `model-output`: the
    alphabetically FIRST is `first-party-field`, the alphabetically LAST is `model-output`,
    and the ladder-strongest is `incident-postmortem` -- three different answers.
    """
    classes = ("first-party-field", "incident-postmortem", FORBIDDEN_CLASS)
    _write_register(root, [_record("GAP-902", classes=classes)])
    return str(root)


# --------------------------------------------------------------------------- premises

def test_the_domain_is_not_vacuous_and_the_unreachable_floor_really_is_unreachable():
    """Every claim below rests on these; a green result over an empty domain is a lie."""
    assert LIVE, "the live register loaded zero records"
    assert len(CLASSES) >= 2 and RUNG[CLASSES[0]] == 0, CLASSES
    assert UNREACHABLE_FLOOR > max(WEIGHT.values()), (UNREACHABLE_FLOOR, WEIGHT)
    assert FORBIDDEN_CLASS in CLASSES and WEIGHT[FORBIDDEN_CLASS] == 0


# --------------------------------------------------------------------------- behavior 1

@pytest.mark.parametrize("extra", ([], ["--floor", "6"], ["--floor", "0"],
                                   ["--layer", "orchestration"]))
def test_b1_every_record_carries_exactly_the_ten_keys_in_exactly_that_order(extra):
    payload = _live_list_json(*extra)
    assert list(payload) == TOP_LEVEL_KEYS, (extra, list(payload))
    assert list(payload["counts"]) == COUNTS_KEYS, (extra, list(payload["counts"]))
    rows = payload["records"]
    assert rows, (extra, payload["counts"])
    for row in rows:
        assert list(row) == RECORD_KEYS, (extra, row["gap_id"], list(row))


def test_b1_the_two_new_keys_are_APPENDED_so_no_pre_existing_index_moved(tmp_path):
    """Spelled against the derived literal, and re-checked on a synthetic register."""
    for argv in (["list", str(REPO_ROOT), "--json"],
                 ["list", _weak_register(tmp_path), "--json"]):
        rows = _payload(argv)["records"]
        assert rows, argv
        for row in rows:
            assert list(row)[:len(PRE_EXISTING_RECORD_KEYS)] == PRE_EXISTING_RECORD_KEYS
            assert list(row)[-2:] == ["strongest_source", "needs"], list(row)


# --------------------------------------------------------------------------- behavior 2

@pytest.mark.parametrize("extra", ([], ["--floor", "6"]))
def test_b2_strongest_source_equals_the_scoring_oracle_for_every_record(extra):
    """The oracle is the FUNCTION over every record, not a per-id census."""
    payload = _live_list_json(*extra)
    records = _by_id(LIVE)
    seen: set[str] = set()
    for row in payload["records"]:
        gap = records[row["gap_id"]]
        assert row["strongest_source"] == strongest_source(gap), row["gap_id"]
        assert isinstance(row["strongest_source"], str) and row["strongest_source"]
        assert row["strongest_source"] in CLASSES, row
        seen.add(row["strongest_source"])
    assert len(seen) >= 2, f"census collapsed to {seen}; the claim would be vacuous"


def test_b2_the_published_class_is_the_strongest_RUNG_of_the_records_own_citations():
    """Independent of the oracle: it must be the minimum-rung class actually cited."""
    for gap in LIVE:
        cited = [c.source_class for c in gap.evidence]
        assert cited, gap.id
        assert strongest_source(gap) == min(cited, key=lambda name: RUNG[name]), gap.id


def test_b2_it_is_the_ladder_and_not_the_alphabet(tmp_path):
    payload = _payload(["list", _mixed_register(tmp_path), "--json"])
    row, = payload["records"]
    cited = ("first-party-field", "incident-postmortem", FORBIDDEN_CLASS)
    assert row["strongest_source"] == "incident-postmortem", row
    assert row["strongest_source"] != min(cited), row
    assert row["strongest_source"] != max(cited), row


# --------------------------------------------------------------------------- behavior 3

@pytest.mark.parametrize("floor", FLOORS)
def test_b3_needs_is_null_if_and_only_if_the_record_is_not_below_floor(floor):
    payload = _live_list_json("--floor", str(floor))
    assert payload["confidence_floor"] == floor, payload["confidence_floor"]
    rows = payload["records"]
    assert rows, floor
    for row in rows:
        assert "strongest_source" in row and "needs" in row, row["gap_id"]
        if row["below_floor"]:
            assert isinstance(row["needs"], list), (floor, row["gap_id"], row["needs"])
        else:
            assert row["needs"] is None, (floor, row["gap_id"], row["needs"])


def test_b3_both_branches_of_the_biconditional_are_reachable_over_the_swept_floors():
    """Otherwise the sweep above could pass while one side never occurred."""
    kinds = set()
    for floor in FLOORS:
        for row in _live_list_json("--floor", str(floor))["records"]:
            kinds.add(row["below_floor"])
    assert kinds == {True, False}, kinds


# --------------------------------------------------------------------------- behavior 4

@pytest.mark.parametrize("floor", FLOORS)
def test_b4_needs_equals_promotion_options_at_the_applied_floor(floor):
    payload = _live_list_json("--floor", str(floor))
    records = _by_id(LIVE)
    for row in payload["records"]:
        if not row["below_floor"]:
            continue
        gap = records[row["gap_id"]]
        assert row["needs"] == list(promotion_options(gap, floor)), (floor, row["gap_id"])
        assert FORBIDDEN_CLASS not in row["needs"], (floor, row["gap_id"], row["needs"])


def test_b4_the_default_floor_is_the_applied_floor_when_no_flag_is_given():
    payload = _live_list_json()
    assert payload["confidence_floor"] == DEFAULT_FLOOR
    records = _by_id(LIVE)
    for row in payload["records"]:
        if row["below_floor"]:
            expected = list(promotion_options(records[row["gap_id"]], DEFAULT_FLOOR))
            assert row["needs"] == expected, row["gap_id"]


def test_b4_needs_is_ordered_by_LADDER_RUNG_and_not_alphabetically(tmp_path):
    """At floor 5 the remedy names three classes whose rung order is NOT their
    alphabetical order -- so this distinguishes the two sorts. Measured, not assumed:
    the members come from the oracle, and only the ORDER is claimed here."""
    register = _weak_register(tmp_path)
    payload = _payload(["list", register, "--json", "--floor", "5"])
    row, = payload["records"]
    assert row["below_floor"] is True, row
    gap, = load_all(pathlib.Path(register) / "gaps")
    needs = row["needs"]
    assert needs == list(promotion_options(gap, 5)), needs
    assert len(needs) >= 2, needs
    assert needs == sorted(needs, key=lambda name: RUNG[name]), needs
    assert needs != sorted(needs), f"{needs} is also the alphabetical order"
    assert FORBIDDEN_CLASS not in needs, needs


# --------------------------------------------------------------------------- behavior 5

def test_b5_an_unreachable_floor_reports_every_record_below_floor_with_an_EMPTY_needs():
    payload = _live_list_json("--floor", str(UNREACHABLE_FLOOR))
    rows = payload["records"]
    assert rows, payload["counts"]
    assert payload["counts"]["ranked"] == 0, payload["counts"]
    assert payload["counts"]["below_floor"] == payload["counts"]["total"]
    for row in rows:
        assert row["below_floor"] is True, row["gap_id"]
        assert row["needs"] == [], (row["gap_id"], row["needs"])


def test_b5_the_same_record_reports_a_NON_EMPTY_needs_when_the_floor_is_reachable(tmp_path):
    """The two-sided witness: one fixture, two floors, two different arrays.

    An implementation that always emits `[]` fails the first half; one that always emits a
    non-empty array fails the second.
    """
    register = _weak_register(tmp_path)
    reachable, = _payload(["list", register, "--json"])["records"]
    unreachable, = _payload(
        ["list", register, "--json", "--floor", str(UNREACHABLE_FLOOR)])["records"]
    assert reachable["below_floor"] is True and unreachable["below_floor"] is True
    assert reachable["needs"], reachable
    assert unreachable["needs"] == [], unreachable
    assert reachable["needs"] != unreachable["needs"]


def test_b5_the_live_register_exercises_the_non_empty_array_too():
    """A property, not an id: any below-floor record with a reachable remedy must name it."""
    payload = _live_list_json()
    records = _by_id(LIVE)
    below = [row for row in payload["records"] if row["below_floor"]]
    for row in below:
        expected = list(promotion_options(records[row["gap_id"]], DEFAULT_FLOOR))
        assert row["needs"] == expected, row["gap_id"]
        if expected:
            assert row["needs"], row["gap_id"]


# --------------------------------------------------------------------------- behavior 6

@pytest.mark.parametrize("extra", ([], ["--floor", "6"], ["--layer", "orchestration"]))
def test_b6_the_surface_is_deterministic_pure_and_ends_in_exactly_one_newline(extra):
    argv = ["list", str(REPO_ROOT), "--json", *extra]
    first_code, first_out, first_err = _run(list(argv))
    second_code, second_out, second_err = _run(list(argv))
    assert first_code == 0 and second_code == 0, (extra, first_code, second_code)
    assert first_err == "" and second_err == "", (extra, first_err, second_err)
    assert first_out == second_out, extra
    assert first_out.endswith("\n") and not first_out.endswith("\n\n"), extra
    assert first_out.strip(), extra


# --------------------------------------------------------------------------- behavior 7

#: The surfaces this iteration must not move, each byte-stable and free of the new keys.
OTHER_SURFACES = (
    ("list-markdown", ["list"]),
    ("list-markdown-floor", ["list", "--floor", "6"]),
    ("report", ["report"]),
    ("report-floor", ["report", "--floor", "6"]),
    ("show", ["show", "GAP-001"]),
    ("prd", ["prd"]),
    ("validate", ["validate"]),
    ("scan-json", ["scan", "--json"]),
    ("taxonomy", ["taxonomy"]),
)


def _surface_argv(argv: list[str]) -> list[str]:
    """`scan` takes the TARGET positionally and the register via `--gaps`."""
    if argv[0] == "scan":
        return ["scan", str(REPO_ROOT), "--gaps", str(REPO_ROOT), *argv[1:]]
    if argv[0] == "taxonomy":
        return list(argv)
    verb, *rest = argv
    if verb == "show":
        return [verb, rest[0], str(REPO_ROOT), *rest[1:]]
    return [verb, str(REPO_ROOT), *rest]


@pytest.mark.parametrize("name,argv", OTHER_SURFACES, ids=[n for n, _ in OTHER_SURFACES])
def test_b7_no_other_surface_gained_either_key_and_each_stays_byte_stable(name, argv):
    resolved = _surface_argv(argv)
    first_code, first_out, first_err = _run(list(resolved))
    second_code, second_out, second_err = _run(list(resolved))
    assert first_code == 0, (name, first_code, first_err)
    assert first_err == "" and second_err == "", (name, first_err, second_err)
    assert first_out == second_out, name
    assert first_out.endswith("\n") and not first_out.endswith("\n\n"), name
    for spelling in LEAKED_SPELLINGS:
        assert spelling not in first_out, (name, spelling)


def test_b7_diff_json_gained_neither_key(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    _write_register(old, [_record("GAP-903", classes=("secondary-summary",))])
    _write_register(new, [_record("GAP-903", classes=("first-party-field",)),
                          _record("GAP-904", classes=("peer-reviewed",))])
    for extra in ([], ["--json"]):
        code, out, err = _run(["diff", str(old), str(new), *extra])
        assert code == 0, (extra, code, err)
        assert err == "", (extra, err)
        assert out.endswith("\n") and not out.endswith("\n\n"), extra
        for spelling in LEAKED_SPELLINGS:
            assert spelling not in out, (extra, spelling)


def test_b7_the_markdown_below_floor_table_keeps_its_two_needs_wordings():
    """`weight >= W: a, b` for a reachable floor; the prose sentence for an unreachable one."""
    reachable_rows, unreachable_rows = 0, 0

    code, out, err = _run(["report", str(REPO_ROOT), "--floor", "5"])
    assert code == 0 and err == "", (code, err)
    for cells in _below_floor_rows(out):
        cell = cells[-1]
        assert cell.startswith(NEEDS_CELL_REACHABLE_PREFIX), cell
        head, _, named = cell.partition(": ")
        weight = int(head[len(NEEDS_CELL_REACHABLE_PREFIX):])
        classes = tuple(part.strip() for part in named.split(","))
        assert all(WEIGHT[name] >= weight for name in classes), cell
        reachable_rows += 1

    code, out, err = _run(["report", str(REPO_ROOT), "--floor", str(UNREACHABLE_FLOOR)])
    assert code == 0 and err == "", (code, err)
    for cells in _below_floor_rows(out):
        assert cells[-1] == NEEDS_CELL_UNREACHABLE.format(floor=UNREACHABLE_FLOOR), cells
        unreachable_rows += 1

    assert reachable_rows and unreachable_rows, (reachable_rows, unreachable_rows)


def _below_floor_rows(document: str):
    """Yield the parsed cells of every data row under the below-floor heading."""
    parts = document.split(BELOW_FLOOR_HEADING, 1)
    assert len(parts) == 2, "report published no below-floor section"
    for line in parts[1].splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6 or cells[0].startswith(("ID", "---")):
            continue
        yield cells


# ------------------------------------------------------- retry round: added coverage
#
# Everything below was added by the SECOND tester round of iteration 110 (the first was
# cut by the stage cap). It closes three holes the inherited file left, each measured
# first by RUNNING the tool, never by reading the implementation:
#
#   (a) Acceptance criterion 3 -- "the above-floor value is the DECIDED `null`, never
#       `promotion_options`' at-floor answer" -- was only asserted one-sidedly. Measured:
#       on the live register `promotion_options(gap, 2)` is NON-EMPTY for above-floor
#       records (it answers "what would reach floor F", which an at-floor record can
#       still be handed), so the oracle WOULD have spoken and the payload must still say
#       `null`. That makes the guard two-sided.
#   (b) Nothing asserted on the SERIALIZED bytes, so an omitted key, a swapped pair or a
#       `[]`-for-`null` substitution could only be caught after `json.loads` had already
#       normalised it away.
#   (c) The two new values' member TYPES, and the register's core invariant that
#       below-floor records are DISPLAYED rather than dropped, were untested at the
#       floors this iteration reads.


def test_b3_the_above_floor_null_is_a_DECISION_not_the_oracles_at_floor_answer():
    """`null` must mean "not applicable", not "the oracle returned this".

    Two-sided: it counts the above-floor records for which the oracle's at-floor answer
    is non-empty, and fails if that count is zero (the claim would be vacuous) or if any
    above-floor record published anything other than `null`.
    """
    floor = DEFAULT_FLOOR
    payload = _live_list_json("--floor", str(floor))
    records = _by_id(LIVE)
    oracle_would_have_spoken = 0
    above = 0
    for row in payload["records"]:
        if row["below_floor"]:
            continue
        above += 1
        assert row["needs"] is None, (row["gap_id"], row["needs"])
        if list(promotion_options(records[row["gap_id"]], floor)):
            oracle_would_have_spoken += 1
    assert above, "no above-floor record at the default floor; the claim is vacuous"
    assert oracle_would_have_spoken, (
        "no above-floor record has a non-empty oracle answer, so `null` here would not "
        "distinguish a DECISION from a pass-through"
    )


def test_b3_a_synthetic_above_floor_record_also_publishes_null(tmp_path):
    """The same claim on a fixture whose single citation sits high on the ladder."""
    _write_register(tmp_path, [_record("GAP-905", classes=("peer-reviewed",))])
    row, = _payload(["list", str(tmp_path), "--json", "--floor", "0"])["records"]
    assert row["below_floor"] is False, row
    assert row["needs"] is None, row
    assert row["strongest_source"] == "peer-reviewed", row


def test_b1_the_SERIALIZED_document_emits_both_keys_right_after_below_floor():
    """Raw bytes: json.loads would normalise away an omitted key or a swapped pair."""
    code, out, err = _run(["list", str(REPO_ROOT), "--json"])
    assert code == 0 and err == "", (code, err)
    rows = json.loads(out)["records"]
    assert rows
    records_text = out.split('"records"', 1)
    assert len(records_text) == 2, "payload published no records section"
    records_text = records_text[1]
    assert records_text.count('"strongest_source": ') == len(rows)
    assert records_text.count('"needs": ') == len(rows)
    assert '"needs": null' in records_text, "the decided null never reached the bytes"
    for cls in sorted({row["strongest_source"] for row in rows}):
        assert f'"strongest_source": "{cls}"' in records_text, cls
    for block in records_text.split('"below_floor": ')[1:]:
        following = block.splitlines()[1:3]
        keys = [line.strip().split(":", 1)[0].strip() for line in following]
        assert keys == ['"strongest_source"', '"needs"'], following


@pytest.mark.parametrize("floor", FLOORS)
def test_b2_b4_every_published_value_is_a_ladder_class_string(floor):
    """Types, membership and no duplicate member -- at every floor this iteration reads."""
    for row in _live_list_json("--floor", str(floor))["records"]:
        assert isinstance(row["strongest_source"], str), (floor, row["gap_id"])
        assert row["strongest_source"] in CLASSES, (floor, row["gap_id"])
        if row["needs"] is None:
            continue
        assert isinstance(row["needs"], list), (floor, row["gap_id"])
        for name in row["needs"]:
            assert isinstance(name, str) and name in CLASSES, (floor, row["gap_id"], name)
        assert len(set(row["needs"])) == len(row["needs"]), (floor, row["needs"])


@pytest.mark.parametrize("floor", FLOORS)
def test_b3_below_floor_records_are_DISPLAYED_and_the_counts_still_add_up(floor):
    """The register's core invariant, re-checked on the payload this iteration grows."""
    payload = _live_list_json("--floor", str(floor))
    counts, rows = payload["counts"], payload["records"]
    assert len(rows) == counts["total"], (floor, len(rows), counts)
    assert counts["ranked"] + counts["below_floor"] == counts["total"], (floor, counts)
    observed = sum(1 for row in rows if row["below_floor"])
    assert observed == counts["below_floor"], (floor, observed, counts)
    assert len({row["gap_id"] for row in rows}) == len(rows), floor


@pytest.mark.parametrize("floor", (0, DEFAULT_FLOOR, UNREACHABLE_FLOOR))
def test_b1_b4_the_layer_filter_combined_with_a_floor_keeps_the_whole_contract(floor):
    """A filtered payload is still a payload: 10 keys, both oracles, both `needs` branches."""
    payload = _live_list_json("--layer", "orchestration", "--floor", str(floor))
    rows = payload["records"]
    assert rows, (floor, payload["counts"])
    records = _by_id(LIVE)
    for row in rows:
        assert list(row) == RECORD_KEYS, (floor, row["gap_id"], list(row))
        assert row["layer"] == "orchestration", (floor, row["gap_id"])
        gap = records[row["gap_id"]]
        assert row["strongest_source"] == strongest_source(gap), row["gap_id"]
        expected = list(promotion_options(gap, floor)) if row["below_floor"] else None
        assert row["needs"] == expected, (floor, row["gap_id"], row["needs"])
