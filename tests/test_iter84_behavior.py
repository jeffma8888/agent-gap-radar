"""Iteration 84 behaviors: `radar list --layer L` narrows the listing to one layer.

The feature under test: one new option on the `list` subparser that filters the loaded
record domain to a single layer of the CLOSED taxonomy, on both the text and the `--json`
surface, and that drops nothing -- a below-floor record survives the filter still flagged,
and the eleven per-layer listings partition the flat listing exactly.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, the engineer's notes, the
reviewer's notes, `IMPLEMENTATION.patch`, or any diff. The oracles are

* `agent_gap_radar.taxonomy.LAYERS` -- the published closed vocabulary, imported so no
  layer name and no count of layers is hand-copied anywhere in this file,
* the committed register JSON read the way a CONSUMER reads it (`gaps/*.json`), which is
  how `tests/test_iter01_behavior.py` already derives its expectations, and
* the bytes `agent_gap_radar.cli.main` writes to stdout / stderr, plus its exit code.

STRUCTURAL NOTES, so this file cannot lie later:

* **No gap id, layer name, layer count or register size is a literal here.** The live
  register is grown by an unattended research pass, so every live-register expectation is
  DERIVED from `gaps/*.json` at test time (roadmap row 28's landmine).
* **The filter's oracle is the UNFILTERED document, not a re-implementation.** Behavior 1
  builds the expected filtered listing by selecting lines out of the flagless document, so
  a test pass cannot depend on this module agreeing with the renderer about a row's format.
* **Behavior 2 is a multiset equality in BOTH directions**, so a filter that duplicated a
  record into two layers reds just as loudly as one that dropped it.
* **Behavior 4's message is BUILT from `taxonomy.LAYERS`**, never restated, so the test
  cannot pass a stale vocabulary and cannot pin a count of layers.
* **Behavior 8 imports iteration 01's committed literals rather than restating them**, so
  this module is structurally unable to re-baseline the pins whose stated job is refusing a
  changed unfiltered surface or a new JSON key.
* **No absolute machine path and no personal or employer identifier appears here**; every
  synthetic fixture is written under pytest's `tmp_path`.
"""

from __future__ import annotations

import collections
import json
import pathlib

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTER = REPO_ROOT / "gaps"

MARKER = "  [below-floor]"

#: `taxonomy.LAYERS` is the published mapping `layer -> gloss`; its KEY ORDER is the closed
#: vocabulary's own order. Named once here, derived, so no layer name and no count of layers
#: is hand-copied anywhere below.
LAYER_NAMES: tuple[str, ...] = tuple(taxonomy.LAYERS)

#: The one line `radar list` writes over a register holding zero records. Behavior 6
#: states this value is INHERITED from the empty document, not decided by the filter.
EMPTY_DOCUMENT = "\n"


def _unknown_layer_message(value: str) -> str:
    """Behavior 4's message, built from the published vocabulary rather than restated."""
    return (f"Error: unknown layer '{value}'; the layer vocabulary is closed: "
            f"{', '.join(LAYER_NAMES)}\n")


# --- consumer-side reads of the live register -------------------------------

def _live_layer_of() -> dict[str, str]:
    """`gap_id -> layer`, read from the committed register the way a consumer would."""
    out: dict[str, str] = {}
    for path in sorted(REGISTER.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        out[record["id"]] = record["layer"]
    return out


def _lines(document: str) -> list[str]:
    return [line for line in document.split("\n") if line.strip()]


def _gap_id(line: str) -> str:
    return line.split()[0]


def _run(capsys, argv: list[str]) -> str:
    """Run the CLI, assert exit 0 and an empty stderr, return stdout."""
    assert main(argv) == 0, argv
    captured = capsys.readouterr()
    assert captured.err == "", (argv, captured.err)
    return captured.out


# --- synthetic fixtures ----------------------------------------------------

_BASE = {
    "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "the symptom text",
    "why_now": "w", "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"],
    "build_hypothesis": "build a small wrapper",
}

_STRONG = {"source_class": "first-party-field", "title": "INC-1",
           "locator": "https://example.invalid/inc1", "date": "2026-01-02",
           "quote": "the verbatim line"}

#: A single `secondary-summary` citation yields confidence 1, below the default floor of 2.
_WEAK = {"source_class": "secondary-summary", "title": "A summary",
         "locator": "https://example.invalid/summary", "date": "2026-02-03",
         "quote": "the summarised line"}


def _rec(gap_id: str, layer: str, *, weak: bool = False, title: str | None = None) -> dict:
    return {**_BASE, "id": gap_id, "layer": layer,
            "title": title if title is not None else f"Record {gap_id}",
            "evidence": [dict(_WEAK if weak else _STRONG)]}


def _register(root: pathlib.Path, records) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for record in records:
        (d / f"{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def _two_layers() -> tuple[str, str]:
    """Two DISTINCT valid layers, taken from the published vocabulary."""
    assert len(LAYER_NAMES) >= 2
    return LAYER_NAMES[0], LAYER_NAMES[1]


# ---------------------------------------------------------------------------
# behavior 1 -- the filtered text surface
# ---------------------------------------------------------------------------

def test_b1_layer_listing_is_exactly_the_unfiltered_lines_of_that_layer(capsys):
    layer_of = _live_layer_of()
    unfiltered = _lines(_run(capsys, ["list", str(REPO_ROOT)]))
    assert unfiltered, "the live register must hold records for this test to mean anything"
    listings: dict[str, list[str]] = {}

    for layer in LAYER_NAMES:
        expected = [line for line in unfiltered if layer_of[_gap_id(line)] == layer]
        got = _lines(_run(capsys, ["list", "--layer", layer, str(REPO_ROOT)]))
        assert got == expected, layer
        assert all(layer_of[_gap_id(line)] == layer for line in got), layer
        listings[layer] = got

    # premise, so the equality above cannot pass by comparing every line to itself:
    # a filtered listing must be STRICTLY shorter than the flat one, and the layer
    # listings must not all be the same document.
    assert any(len(v) < len(unfiltered) for v in listings.values()), "nothing narrowed"
    assert len({tuple(v) for v in listings.values()}) > 1, "every layer rendered the same"
    assert max(len(v) for v in listings.values()) < len(unfiltered)


def test_b1_the_layer_option_takes_exactly_one_value(capsys):
    """Out of Scope: repeatable and comma-separated values are NOT the surface."""
    layer_a, layer_b = _two_layers()
    # Two values in one flag is an argparse error (exit 2), never a two-layer listing.
    code = main(["list", "--layer", f"{layer_a},{layer_b}", str(REPO_ROOT)])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == _unknown_layer_message(f"{layer_a},{layer_b}")


# ---------------------------------------------------------------------------
# behavior 2 -- never-drop across the whole partition
# ---------------------------------------------------------------------------

def test_b2_the_layer_listings_partition_the_flat_listing_exactly(capsys):
    """Multiset equality both ways: a dropped record and a duplicated one both red."""
    unfiltered = _lines(_run(capsys, ["list", str(REPO_ROOT)]))
    assert unfiltered, "the live register must hold records"

    concatenated: list[str] = []
    for layer in LAYER_NAMES:
        concatenated.extend(_lines(_run(capsys, ["list", "--layer", layer, str(REPO_ROOT)])))

    assert collections.Counter(concatenated) == collections.Counter(unfiltered)
    assert len(concatenated) == len(unfiltered)

    ids = [_gap_id(line) for line in concatenated]
    assert len(set(ids)) == len(ids), "a record appeared under more than one layer"
    assert sorted(ids) == sorted(_gap_id(line) for line in unfiltered)


def test_b2_no_layer_listing_leaks_a_record_from_another_layer(capsys):
    """The complement of behavior 2: each listing is a SUBSET of its own layer."""
    layer_of = _live_layer_of()
    for layer in LAYER_NAMES:
        got = _lines(_run(capsys, ["list", "--layer", layer, str(REPO_ROOT)]))
        strangers = [line for line in got if layer_of[_gap_id(line)] != layer]
        assert strangers == [], (layer, strangers)


# ---------------------------------------------------------------------------
# behavior 3 -- a below-floor record survives the filter, still flagged
# ---------------------------------------------------------------------------

def test_b3_a_below_floor_record_survives_the_filter_and_keeps_its_flag(tmp_path, capsys):
    layer, other = _two_layers()
    root = _register(tmp_path, [_rec("GAP-001", layer, title="A ranked thing"),
                                _rec("GAP-002", layer, weak=True, title="A weak thing"),
                                _rec("GAP-003", other, title="Another layer")])

    unfiltered = _lines(_run(capsys, ["list", str(root)]))
    flagged = [line for line in unfiltered if line.endswith(MARKER)]
    # premise: the fixture really does produce exactly one below-floor record
    assert len(flagged) == 1, unfiltered
    assert _gap_id(flagged[0]) == "GAP-002", flagged

    filtered = _lines(_run(capsys, ["list", "--layer", layer, str(root)]))
    # byte-identical line, flag included, and it is the SAME line object bytes
    assert flagged[0] in filtered, filtered
    assert [line for line in filtered if line.endswith(MARKER)] == flagged
    assert filtered == [line for line in unfiltered
                        if _gap_id(line) in {"GAP-001", "GAP-002"}]


def test_b3_the_filter_does_not_move_the_below_floor_flag(tmp_path, capsys):
    """A layer holding ONLY the below-floor record still flags it."""
    layer, other = _two_layers()
    root = _register(tmp_path, [_rec("GAP-001", other, title="A ranked thing"),
                                _rec("GAP-002", layer, weak=True, title="A weak thing")])
    filtered = _lines(_run(capsys, ["list", "--layer", layer, str(root)]))
    assert len(filtered) == 1, filtered
    assert filtered[0].endswith(MARKER), filtered
    payload = json.loads(_run(capsys, ["list", "--layer", layer, "--json", str(root)]))
    assert [r["gap_id"] for r in payload["records"]] == ["GAP-002"]
    assert payload["records"][0]["below_floor"] is True
    assert payload["counts"] == {"total": 1, "ranked": 0, "below_floor": 1}


# ---------------------------------------------------------------------------
# behavior 4 -- an unknown layer is a user error, not an empty answer
# ---------------------------------------------------------------------------

def test_b4_an_unknown_layer_exits_two_with_the_closed_vocabulary(capsys):
    known = LAYER_NAMES[0]
    bogus_values = [
        "nope",
        known.upper(),          # the vocabulary is closed: no case-insensitive match
        known[:3],              # no prefix match
        f" {known}",            # no trimming
        "",                     # the empty string is not a layer either
    ]
    for value in bogus_values:
        code = main(["list", "--layer", value, str(REPO_ROOT)])
        captured = capsys.readouterr()
        assert code == 2, value
        assert captured.out == "", (value, captured.out)
        assert captured.err == _unknown_layer_message(value), value


def test_b4_the_error_names_every_accepted_value_and_no_count(capsys):
    assert main(["list", "--layer", "nope", str(REPO_ROOT)]) == 2
    err = capsys.readouterr().err
    for layer in LAYER_NAMES:
        assert layer in err, layer
    assert err.endswith("\n") and not err.endswith("\n\n")
    assert err.count("\n") == 1
    assert err.startswith("Error: ")
    # the message publishes the vocabulary, not a count of it
    assert str(len(LAYER_NAMES)) not in err


# ---------------------------------------------------------------------------
# behavior 5 -- the layer is validated before the register is read
# ---------------------------------------------------------------------------

def test_b5_a_bogus_layer_over_a_path_holding_no_register_is_the_layer_error(tmp_path, capsys):
    empty = tmp_path / "no-register"
    empty.mkdir()
    # control: with no filter this path is not an error at all, it is an empty document
    assert main(["list", str(empty)]) == 0
    control = capsys.readouterr()
    assert control.err == ""
    assert control.out == EMPTY_DOCUMENT

    code = main(["list", "--layer", "nope", str(empty)])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == _unknown_layer_message("nope")


def test_b5_a_bogus_layer_outranks_an_unreadable_register(tmp_path, capsys):
    """The ordering claim, made provable: an unreadable register must NOT be reported first."""
    root = tmp_path / "broken"
    (root / "gaps").mkdir(parents=True)
    (root / "gaps" / "GAP-001.json").write_text("{not json", encoding="utf-8")

    # premise: this register really is unreadable, and says so on its own
    assert main(["list", str(root)]) == 2
    registry_err = capsys.readouterr().err
    assert registry_err.startswith("Error: "), registry_err
    assert "unknown layer" not in registry_err

    # a bogus layer is diagnosed FIRST -- the register is never reached
    assert main(["list", "--layer", "nope", str(root)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _unknown_layer_message("nope")
    assert captured.err != registry_err

    # and a VALID layer still surfaces the register's own error, so the ordering
    # test above is not passing because the register error was swallowed
    assert main(["list", "--layer", LAYER_NAMES[0], str(root)]) == 2
    assert capsys.readouterr().err == registry_err


# ---------------------------------------------------------------------------
# behavior 6 -- a valid layer holding zero records is an empty document
# ---------------------------------------------------------------------------

def test_b6_a_valid_empty_layer_is_exit_zero_and_the_empty_document(tmp_path, capsys):
    layer, other = _two_layers()
    root = _register(tmp_path, [_rec("GAP-001", layer), _rec("GAP-002", layer)])

    out = _run(capsys, ["list", "--layer", other, str(root)])
    assert out == EMPTY_DOCUMENT
    assert out.endswith("\n") and not out.endswith("\n\n")

    # INHERITED, not decided here: the same bytes a zero-record register renders
    zero = _register(tmp_path / "zero", [])
    assert _run(capsys, ["list", str(zero)]) == out

    # premise: the fixture's own layer is NOT empty, so the assertion above is
    # about the filter and not about a register that renders nothing either way
    assert len(_lines(_run(capsys, ["list", "--layer", layer, str(root)]))) == 2


def test_b6_an_empty_layer_json_payload_is_an_empty_record_list(tmp_path, capsys):
    layer, other = _two_layers()
    root = _register(tmp_path, [_rec("GAP-001", layer)])
    payload = json.loads(_run(capsys, ["list", "--layer", other, "--json", str(root)]))
    assert list(payload) == ["confidence_floor", "counts", "records"]
    assert payload["records"] == []
    assert payload["counts"] == {"total": 0, "ranked": 0, "below_floor": 0}


# ---------------------------------------------------------------------------
# behavior 7 -- `--json` filters the same domain and gains no key
# ---------------------------------------------------------------------------

def test_b7_json_filters_the_same_domain_in_the_same_order(capsys):
    unfiltered_floor = json.loads(
        _run(capsys, ["list", "--json", str(REPO_ROOT)]))["confidence_floor"]

    for layer in LAYER_NAMES:
        text_ids = [_gap_id(line) for line
                    in _lines(_run(capsys, ["list", "--layer", layer, str(REPO_ROOT)]))]
        payload = json.loads(
            _run(capsys, ["list", "--layer", layer, "--json", str(REPO_ROOT)]))

        assert list(payload) == ["confidence_floor", "counts", "records"], sorted(payload)
        assert [r["gap_id"] for r in payload["records"]] == text_ids, layer
        assert all(r["layer"] == layer for r in payload["records"]), layer

        counts = payload["counts"]
        assert list(counts) == ["total", "ranked", "below_floor"], layer
        assert counts["total"] == len(payload["records"]), layer
        assert counts["ranked"] + counts["below_floor"] == counts["total"], layer
        assert counts["below_floor"] == sum(r["below_floor"] for r in payload["records"])
        assert payload["confidence_floor"] == unfiltered_floor, layer


def test_b7_no_record_object_gains_a_key_under_the_filter(capsys):
    import test_iter01_behavior as it01

    layer = LAYER_NAMES[0]
    payload = json.loads(_run(capsys, ["list", "--layer", layer, "--json", str(REPO_ROOT)]))
    assert payload["records"], payload
    for record in payload["records"]:
        assert list(record) == it01.RECORD_KEYS, record.get("gap_id")


def test_b7_json_output_is_byte_stable_and_ends_in_one_newline(capsys):
    layer = LAYER_NAMES[0]
    argv = ["list", "--layer", layer, "--json", str(REPO_ROOT)]
    first = _run(capsys, argv)
    assert _run(capsys, list(argv)) == first
    assert first.endswith("\n") and not first.endswith("\n\n")


# ---------------------------------------------------------------------------
# behavior 8 -- omitting `--layer` changes nothing
# ---------------------------------------------------------------------------

def test_b8_the_unfiltered_text_surface_still_matches_iteration_01s_pins(capsys):
    """Imported, not restated, so this module cannot re-baseline a committed pin."""
    import test_iter01_behavior as it01

    lines = _lines(_run(capsys, ["list", str(REPO_ROOT)]))
    assert it01.LITERAL_RANKED_ROW in lines
    assert it01.LITERAL_BELOW_FLOOR_ROW in lines
    assert it01.LITERAL_BELOW_FLOOR_ROW.endswith(it01.MARKER)
    assert len(lines) == it01.register_size()


def test_b8_the_unfiltered_json_surface_keeps_its_key_set_and_every_layer(capsys):
    import test_iter01_behavior as it01

    payload = json.loads(_run(capsys, ["list", str(REPO_ROOT), "--json"]))
    assert list(payload) == ["confidence_floor", "counts", "records"], sorted(payload)
    for record in payload["records"]:
        assert list(record) == it01.RECORD_KEYS, record.get("gap_id")
    # no default filtering: every layer the register uses is represented
    assert ({r["layer"] for r in payload["records"]}
            == set(_live_layer_of().values()))
    assert payload["counts"]["total"] == it01.register_size()


# ---------------------------------------------------------------------------
# behavior 9 -- `--layer` and `--floor` are independent
# ---------------------------------------------------------------------------

def test_b9_the_below_floor_flag_is_unchanged_by_the_layer_filter(capsys):
    floors = (1, 3, 5)
    seen: list[frozenset[str]] = []

    for floor in floors:
        base = json.loads(
            _run(capsys, ["list", "--floor", str(floor), "--json", str(REPO_ROOT)]))
        assert base["confidence_floor"] == floor
        flag = {r["gap_id"]: r["below_floor"] for r in base["records"]}
        seen.append(frozenset(gid for gid, low in flag.items() if low))

        for layer in LAYER_NAMES:
            payload = json.loads(_run(capsys, [
                "list", "--layer", layer, "--floor", str(floor), "--json", str(REPO_ROOT)]))
            assert payload["confidence_floor"] == floor, (layer, floor)
            for record in payload["records"]:
                assert record["below_floor"] == flag[record["gap_id"]], (
                    layer, floor, record["gap_id"])

            text = _lines(_run(capsys, [
                "list", "--layer", layer, "--floor", str(floor), str(REPO_ROOT)]))
            for line in text:
                assert line.endswith(MARKER) == flag[_gap_id(line)], (layer, floor, line)

    # premise: `--floor` really does change the flag over this register, so the
    # equality above is not trivially true for every floor
    assert len(set(seen)) > 1, seen
    assert seen == sorted(seen, key=len), seen


def test_b9_the_filtered_domain_is_the_same_at_every_floor(capsys):
    """`--floor` moves flags, never membership -- so a layer's line count is floor-free."""
    layer = LAYER_NAMES[0]
    counts = set()
    for floor in (1, 3, 5):
        ids = tuple(sorted(_gap_id(line) for line in _lines(_run(
            capsys, ["list", "--layer", layer, "--floor", str(floor), str(REPO_ROOT)]))))
        counts.add(ids)
    assert len(counts) == 1, counts


# ---------------------------------------------------------------------------
# behavior 10 -- the published surface stays true
# ---------------------------------------------------------------------------

def test_b10_the_consumer_contract_and_the_parser_agree_in_both_directions():
    from _surface_contract import contract_text, surface_violations

    assert surface_violations(contract_text()) == []


def test_b10_the_contract_row_for_list_names_the_new_option():
    from _surface_contract import contract_text, invocation_verb, surface_table_cells

    cells = [cell for cell in surface_table_cells(contract_text())
             if invocation_verb(cell) == "list"]
    assert len(cells) == 1, cells
    assert "--layer" in cells[0], cells[0]


def test_b10_list_help_lists_the_new_option(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["list", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--layer" in out, out


def test_b10_the_option_is_on_the_list_subparser_only(capsys):
    """Out of Scope: `report`, `scan`, `show` and `prd` do not gain `--layer`."""
    layer = LAYER_NAMES[0]
    for argv in (["report", "--layer", layer, str(REPO_ROOT)],
                 ["scan", "--layer", layer, str(REPO_ROOT)],
                 ["show", "GAP-003", "--layer", layer, str(REPO_ROOT)],
                 ["prd", "--layer", layer, str(REPO_ROOT)]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2, argv
        assert "--layer" in capsys.readouterr().err, argv


# ---------------------------------------------------------------------------
# module self-check -- is this file discriminating at all?
# ---------------------------------------------------------------------------

def test_the_oracle_can_fail(capsys):
    """A control: the comparisons above are capable of going red.

    `_live_layer_of` is the oracle every live-register expectation is built from. If it
    ever returned a constant, behaviors 1, 2 and 7 would all pass while measuring
    nothing. This asserts the oracle really distributes the register over more than one
    layer, that a deliberately WRONG expected listing does not match, and that the
    unknown-layer message really is sensitive to its argument.
    """
    layer_of = _live_layer_of()
    assert len(set(layer_of.values())) > 1, "the oracle collapsed to one layer"
    assert set(layer_of.values()) <= set(LAYER_NAMES), sorted(set(layer_of.values()))

    a, b = LAYER_NAMES[0], LAYER_NAMES[1]
    listing_a = _lines(_run(capsys, ["list", "--layer", a, str(REPO_ROOT)]))
    wrong = [line for line in _lines(_run(capsys, ["list", str(REPO_ROOT)]))
             if layer_of[_gap_id(line)] == b]
    assert listing_a != wrong, "two different layers rendered the same listing"

    assert _unknown_layer_message("x") != _unknown_layer_message("y")


# ---------------------------------------------------------------------------
# Out of Scope, asserted rather than assumed: a repeatable flag is NOT the surface
# ---------------------------------------------------------------------------

def test_repeating_the_flag_never_unions_two_layers(capsys):
    """`--layer A --layer B` must not answer with both layers.

    The spec does NOT decide what repeating the flag MEANS (argparse's default is
    last-wins), so this pins only the half `## Out of Scope` does decide -- "repeatable
    ... are NOT the surface" -- and deliberately leaves last-wins unpinned. Whatever the
    answer is, it must be ONE layer's listing, never the union.
    """
    a, b = _two_layers()
    only_a = _lines(_run(capsys, ["list", "--layer", a, str(REPO_ROOT)]))
    only_b = _lines(_run(capsys, ["list", "--layer", b, str(REPO_ROOT)]))
    # premise: the two layers are genuinely different non-empty listings, so "union"
    # is a distinguishable outcome at all
    assert only_a and only_b and only_a != only_b
    union = collections.Counter(only_a + only_b)

    both = _lines(_run(capsys, ["list", "--layer", a, "--layer", b, str(REPO_ROOT)]))
    assert collections.Counter(both) != union, both
    assert both in (only_a, only_b), both


def test_the_flag_may_follow_the_path(capsys):
    """Option order is not part of the meaning: the same bytes either side of the path."""
    layer = LAYER_NAMES[0]
    before = _run(capsys, ["list", "--layer", layer, str(REPO_ROOT)])
    after = _run(capsys, ["list", str(REPO_ROOT), "--layer", layer])
    assert after == before
    assert before.endswith("\n") and not before.endswith("\n\n")
