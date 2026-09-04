"""Iteration 01 behaviors: `radar list` displays below-floor records, plus `--json`.

Black-box. Every assertion drives the public CLI entry point and reads observable
stdout / stderr / exit code, or reads the committed register JSON the way a consumer
would. Nothing here imports the CLI's internals or asserts an implementation detail.

Expected numbers are DERIVED, not copied from the tool's output. The priority mapping
is pinned by tests/test_scoring.py: (1,1,1) -> 2.0, (5,5,5) -> 10.0, and the weights are
ordered severity > frequency > tractability. The one mapping satisfying all three is
weighted = 3*severity + 2*frequency + 1*tractability, priority = weighted / 3, rounded
to one decimal. Confidence is the strongest evidence class's ceiling, plus one for a
second DISTINCT non-`model-output` class, capped at 5.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTER = REPO_ROOT / "gaps"

MARKER = "  [below-floor]"

#: GAP-003: severity 5, frequency 4, tractability 4 -> (15+8+4)/3 = 9.0.
#: This is a FORMAT sample, not the top-ranked row -- higher-priority records
#: have since been promoted above it.
#: Two citations of the SAME class (first-party-field) are one kind of evidence,
#: so confidence is the ceiling 5 with no corroboration bonus.
LITERAL_RANKED_ROW = (
    "GAP-003  p= 9.0  c=5  "
    "No checkpoint-first contract for steps running under a hard wall-clock cap"
)

#: GAP-010: severity 2, frequency 4, tractability 2 -> (6+8+2)/3 = 5.333 -> 5.3.
#: One `secondary-summary` citation -> confidence 1, below the default floor of 2.
#: NOTE: pm.md behavior 4 pins this row as `p= 4.0`. That literal does not survive
#: the derivation above, so this test asserts the derived value.
LITERAL_BELOW_FLOOR_ROW = (
    "GAP-010  p= 5.3  c=1  "
    "Pilot-to-production conversion for enterprise agents is reported as very low, "
    "but the measurement is unaudited" + MARKER
)

#: Re-baselined 8 -> 10 in iteration 110: `strongest_source` and `needs` were APPENDED
#: as the two new last keys, both DERIVED (`scoring.strongest_source` and
#: `scoring.promotion_options`). The pin's intent is "no key renamed, removed or
#: reordered" -- every pre-existing key keeps its absolute index here, so this literal
#: still refuses the changes it exists to refuse while documenting growth by appending.
#: Also read by `tests/test_iter84_behavior.py`, which imports it rather than restating
#: it, so there is exactly one place to re-baseline.
RECORD_KEYS = ["gap_id", "title", "layer", "gap_type", "status",
               "priority", "confidence", "below_floor",
               "strongest_source", "needs"]


def register_size() -> int:
    """Derived, never a literal: a research cycle promotes records on a schedule."""
    return len(list(REGISTER.glob("*.json")))


def _record(gid, sev=3, freq=3, tract=3, classes=("first-party-field",)):
    return {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}
                     for c in classes],
    }


def _write_register(root, records):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return root


@pytest.fixture()
def repo(tmp_path):
    return _write_register(tmp_path, [_record("GAP-001", sev=5, freq=4, tract=3)])


#: Equal priority with different confidence, equal priority AND confidence, and two
#: below-floor records whose priority is the HIGHEST in the set -- so the ordering
#: assertions cannot pass by accident.
ORDERED_RECORDS = [
    _record("GAP-104", sev=5, freq=5, tract=5),                            # p 10.0 c5
    _record("GAP-101", sev=3, freq=3, tract=3),                            # p  6.0 c5
    _record("GAP-103", sev=3, freq=3, tract=3),                            # p  6.0 c5
    _record("GAP-102", sev=3, freq=3, tract=3, classes=("survey-aggregate",)),  # 6.0 c3
    _record("GAP-106", sev=5, freq=5, tract=5, classes=("model-output",)),  # p 10.0 c0
    _record("GAP-105", sev=5, freq=5, tract=5, classes=("model-output",)),  # p 10.0 c0
]
EXPECTED_ORDER = ["GAP-104", "GAP-101", "GAP-103", "GAP-102", "GAP-105", "GAP-106"]


def _ids(out):
    return [line.split(" ", 1)[0] for line in out.splitlines()]


# ---------------------------------------------------------------------------
# Behavior 1 -- no record is dropped.
# ---------------------------------------------------------------------------

def test_b1_list_prints_one_line_for_every_record_in_the_register(capsys):
    """The regression net: this printed 15 lines for a 16-record register."""
    assert main(["list", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    assert captured.out.count("\n") == register_size()
    assert captured.err == ""


def test_b1_the_below_floor_record_is_present_by_id(capsys):
    assert main(["list", str(REPO_ROOT)]) == 0
    assert "GAP-010" in _ids(capsys.readouterr().out)


def test_b1_list_and_report_agree_about_membership(capsys):
    """Two renderers of one register may not disagree about which records exist."""
    assert main(["list", str(REPO_ROOT)]) == 0
    listed = set(_ids(capsys.readouterr().out))
    assert main(["report", str(REPO_ROOT)]) == 0
    reported = capsys.readouterr().out
    for gid in listed:
        assert gid in reported, gid
    for path in REGISTER.glob("*.json"):
        gid = json.loads(path.read_text(encoding="utf-8"))["id"]
        assert gid in listed, gid


# ---------------------------------------------------------------------------
# Behavior 2 -- total, deterministic order: ranked rows then below-floor rows.
# ---------------------------------------------------------------------------

def test_b2_order_is_priority_then_confidence_then_id_with_below_floor_last(
        tmp_path, capsys):
    _write_register(tmp_path, ORDERED_RECORDS)
    assert main(["list", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert _ids("\n".join(lines)) == EXPECTED_ORDER
    assert [MARKER in ln for ln in lines] == [False, False, False, False, True, True]


def test_b2_committed_register_marks_only_a_trailing_run_of_rows(capsys):
    """Marked rows form one suffix: no marked row may appear among ranked rows."""
    assert main(["list", str(REPO_ROOT)]) == 0
    marked = [MARKER in ln for ln in capsys.readouterr().out.splitlines()]
    assert marked == sorted(marked), "below-floor rows must all come last"


def test_b2_below_floor_rows_are_id_ascending(tmp_path, capsys):
    _write_register(tmp_path, ORDERED_RECORDS)
    assert main(["list", str(tmp_path)]) == 0
    marked = [ln.split(" ", 1)[0] for ln in capsys.readouterr().out.splitlines()
              if MARKER in ln]
    assert marked == sorted(marked)
    assert marked == ["GAP-105", "GAP-106"]


# ---------------------------------------------------------------------------
# Behavior 3 -- a ranked row is byte-identical to the shipped format.
# ---------------------------------------------------------------------------

def test_b3_ranked_row_is_byte_identical_to_the_literal(capsys):
    """The FORMAT of a ranked row is pinned, byte for byte.

    Anchored to GAP-003's own row rather than to `lines[0]`. Which record ranks
    first is a property of the register's CONTENTS, and the register grows: pinning
    rank 1 made a correct promotion (a record scoring 9.7 landing above this one)
    read as a formatting regression. The byte-level guarantee is unchanged, and
    every row's shape is still checked by the next test.
    """
    assert main(["list", str(REPO_ROOT)]) == 0
    lines = capsys.readouterr().out.splitlines()
    rows = [ln for ln in lines if ln.startswith("GAP-003  ")]
    assert rows == [LITERAL_RANKED_ROW], rows


def test_b3_no_ranked_row_carries_a_new_token(capsys):
    """The marker is the only token this iteration adds, and only below the floor."""
    assert main(["list", str(REPO_ROOT), "--floor", "0"]) == 0
    for line in capsys.readouterr().out.splitlines():
        assert MARKER not in line
        assert line.count("  ") == 3, line


# ---------------------------------------------------------------------------
# Behavior 4 -- a below-floor row is the same row plus exactly one suffix token.
# ---------------------------------------------------------------------------

def test_b4_below_floor_row_is_byte_identical_to_the_literal(capsys):
    assert main(["list", str(REPO_ROOT)]) == 0
    rows = {ln.split(" ", 1)[0]: ln for ln in capsys.readouterr().out.splitlines()}
    assert rows["GAP-010"] == LITERAL_BELOW_FLOOR_ROW


def test_b4_marker_is_a_pure_suffix_of_the_unmarked_row(tmp_path, capsys):
    """Same record, floor 0 vs floor 6: the row gains the marker and nothing else."""
    _write_register(tmp_path, [_record("GAP-001", sev=5, freq=4, tract=3)])
    assert main(["list", str(tmp_path), "--floor", "0"]) == 0
    plain = capsys.readouterr().out
    assert main(["list", str(tmp_path), "--floor", "6"]) == 0
    marked = capsys.readouterr().out
    assert marked == plain.rstrip("\n") + MARKER + "\n"


# ---------------------------------------------------------------------------
# Behavior 5 -- the floor changes MARKING, never membership.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("floor", ["0", "2", "6"])
def test_b5_line_count_is_the_register_size_at_every_floor(floor, capsys):
    assert main(["list", str(REPO_ROOT), "--floor", floor]) == 0
    assert capsys.readouterr().out.count("\n") == register_size()


def test_b5_floor_zero_marks_nothing_and_floor_six_marks_everything(capsys):
    assert main(["list", str(REPO_ROOT), "--floor", "0"]) == 0
    at_zero = capsys.readouterr().out.splitlines()
    assert sum(MARKER in ln for ln in at_zero) == 0
    assert main(["list", str(REPO_ROOT), "--floor", "6"]) == 0
    at_six = capsys.readouterr().out.splitlines()
    assert sum(MARKER in ln for ln in at_six) == register_size()
    assert len(at_six) == len(at_zero) == register_size()


def test_b5_default_floor_is_two_and_marks_the_weakly_sourced_record(capsys):
    assert main(["list", str(REPO_ROOT)]) == 0
    default = capsys.readouterr().out
    assert main(["list", str(REPO_ROOT), "--floor", "2"]) == 0
    assert capsys.readouterr().out == default
    assert LITERAL_BELOW_FLOOR_ROW in default.splitlines()


# ---------------------------------------------------------------------------
# Behavior 6 -- `--json` is a parseable document on stdout, one trailing newline.
# ---------------------------------------------------------------------------
def test_text_renderer_ends_in_exactly_one_newline(capsys):
    """Quality bar: every renderer ends in exactly ONE newline."""
    assert main(["list", str(REPO_ROOT)]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")



def test_b6_json_parses_exits_zero_and_writes_only_the_document(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    json.loads(captured.out)


def test_b6_json_ends_in_exactly_one_newline(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    out = capsys.readouterr().out
    assert out.endswith("}\n") and not out.endswith("\n\n")


def test_b6_json_serialisation_mirrors_scan_json(capsys):
    """indent=2, sort_keys=False, exactly one trailing newline."""
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    out = capsys.readouterr().out
    reserialised = json.dumps(json.loads(out), indent=2, sort_keys=False) + "\n"
    assert out == reserialised


def test_b6_json_flag_position_does_not_change_the_document(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    leading = capsys.readouterr().out
    assert main(["list", str(REPO_ROOT), "--json"]) == 0
    assert capsys.readouterr().out == leading


# ---------------------------------------------------------------------------
# Behavior 7 -- one flat record list, fixed key order, text order preserved.
# ---------------------------------------------------------------------------

def test_b7_top_level_shape_and_key_order(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == ["confidence_floor", "counts", "records"]
    assert isinstance(payload["confidence_floor"], int)
    assert list(payload["counts"]) == ["total", "ranked", "below_floor"]
    assert isinstance(payload["records"], list)


def test_b7_counts_are_consistent_with_the_register_and_the_records(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    counts, records = payload["counts"], payload["records"]
    assert counts["total"] == register_size() == len(records)
    assert counts["ranked"] + counts["below_floor"] == counts["total"]
    assert counts["below_floor"] == sum(r["below_floor"] for r in records)


def test_b7_every_record_object_has_the_fixed_key_order_and_types(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    for rec in json.loads(capsys.readouterr().out)["records"]:
        assert list(rec) == RECORD_KEYS, rec.get("gap_id")
        assert isinstance(rec["priority"], float)
        assert isinstance(rec["confidence"], int) and not isinstance(
            rec["confidence"], bool)
        assert isinstance(rec["below_floor"], bool)


def test_b7_records_are_one_flat_list_not_two(capsys):
    """A second list would structurally re-create the drop this iteration fixes."""
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    for key in ("ranked", "below_floor", "below_floor_records", "ranked_records"):
        assert not isinstance(payload.get(key), list), key
    assert sum(isinstance(v, list) for v in payload.values()) == 1


def test_b7_json_order_equals_the_text_order(capsys):
    assert main(["list", str(REPO_ROOT)]) == 0
    text_ids = _ids(capsys.readouterr().out)
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [r["gap_id"] for r in payload["records"]] == text_ids


def test_b7_json_below_floor_flag_matches_the_text_marker(capsys):
    assert main(["list", str(REPO_ROOT)]) == 0
    marked = {ln.split(" ", 1)[0] for ln in capsys.readouterr().out.splitlines()
              if MARKER in ln}
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {r["gap_id"] for r in payload["records"] if r["below_floor"]} == marked


def test_b7_synthetic_register_json_order_matches_the_documented_ranking(
        tmp_path, capsys):
    _write_register(tmp_path, ORDERED_RECORDS)
    assert main(["list", "--json", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [r["gap_id"] for r in payload["records"]] == EXPECTED_ORDER
    assert payload["counts"] == {"total": 6, "ranked": 4, "below_floor": 2}


# ---------------------------------------------------------------------------
# Behavior 8 -- no blended score.
# ---------------------------------------------------------------------------

def test_b8_no_score_key_anywhere_in_the_json(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "score" not in payload
    assert "score" not in payload["counts"]
    for rec in payload["records"]:
        assert "score" not in rec, "a blended score would launder the invariant"
    assert '"score"' not in out


# ---------------------------------------------------------------------------
# Behavior 9 -- deterministic, and independent of file creation order.
# ---------------------------------------------------------------------------

def test_b9_json_is_byte_stable_across_two_invocations(capsys):
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    first = capsys.readouterr().out
    assert main(["list", "--json", str(REPO_ROOT)]) == 0
    assert capsys.readouterr().out == first


def test_b9_json_is_independent_of_the_order_records_were_written(
        tmp_path, capsys):
    forward = _write_register(tmp_path / "fwd", sorted(
        ORDERED_RECORDS, key=lambda r: r["id"]))
    reverse = _write_register(tmp_path / "rev", sorted(
        ORDERED_RECORDS, key=lambda r: r["id"], reverse=True))
    assert main(["list", "--json", str(forward)]) == 0
    a = capsys.readouterr().out
    assert main(["list", "--json", str(reverse)]) == 0
    assert capsys.readouterr().out == a


def test_b9_text_is_independent_of_the_order_records_were_written(
        tmp_path, capsys):
    forward = _write_register(tmp_path / "fwd", sorted(
        ORDERED_RECORDS, key=lambda r: r["id"]))
    reverse = _write_register(tmp_path / "rev", sorted(
        ORDERED_RECORDS, key=lambda r: r["id"], reverse=True))
    assert main(["list", str(forward)]) == 0
    a = capsys.readouterr().out
    assert main(["list", str(reverse)]) == 0
    assert capsys.readouterr().out == a


# ---------------------------------------------------------------------------
# Behavior 10 -- the failure path is unchanged, with and without `--json`.
# ---------------------------------------------------------------------------

@pytest.fixture()
def broken_repo(tmp_path):
    d = tmp_path / "gaps"
    d.mkdir()
    good = _record("GAP-001")
    (d / "GAP-001.json").write_text(json.dumps(good), encoding="utf-8")
    bad = {**_record("GAP-002"), "severity": 99}
    (d / "GAP-002.json").write_text(json.dumps(bad), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("argv_extra", [[], ["--json"]])
def test_b10_schema_invalid_record_exits_2_with_stderr_and_no_stdout(
        argv_extra, broken_repo, capsys):
    assert main(["list", str(broken_repo), *argv_extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")


@pytest.mark.parametrize("argv_extra", [[], ["--json"]])
def test_b10_unparseable_json_record_exits_2(argv_extra, tmp_path, capsys):
    d = tmp_path / "gaps"
    d.mkdir()
    (d / "bad.json").write_text("{nope", encoding="utf-8")
    assert main(["list", str(tmp_path), *argv_extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")


# ---------------------------------------------------------------------------
# `--layer` was DEFERRED to roadmap row 16, and iteration 84 shipped that row. The
# pin here was iteration 01's own scope fence -- "this iteration did not sneak row
# 16 in" -- so it is SPENT rather than weakened, and it is INVERTED instead of
# deleted so the line keeps an assertion: a deleted fence is indistinguishable from
# a forgotten one. The flag's own behaviors belong to
# `tests/test_iter84_behavior.py`; what this file still owns is that a `list`
# argument error keeps iteration 01's published SHAPE. That shape changed in one way
# worth pinning: before iteration 84 argparse refused an unknown OPTION with its own
# usage block and `SystemExit`, and now `cli._fail` refuses an unknown VALUE with one
# `Error: ` line on stderr, empty stdout and exit 2 -- the refusal vocabulary
# `docs/CONSUMER_CONTRACT.md` publishes. Same code, a published message instead of a
# usage dump, so this asserts `main()`'s RETURN VALUE and no longer `SystemExit`.
# ---------------------------------------------------------------------------

def test_layer_flag_ships_and_refuses_an_unknown_value_through_the_error_site(
        repo, capsys):
    # The fixture's one record sits in `orchestration`, so a valid layer is a
    # document and not an accident of an empty domain.
    assert main(["list", str(repo), "--layer", "orchestration"]) == 0
    first = capsys.readouterr()
    assert first.out.strip() and first.err == ""
    assert main(["list", str(repo), "--layer", "orchestraton"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: unknown layer 'orchestraton';")


# ---------------------------------------------------------------------------
# Behaviors 11 and 12 -- committed documents must not promise what ships.
# ---------------------------------------------------------------------------

def _lines(relpath):
    return (REPO_ROOT / relpath).read_text(encoding="utf-8").splitlines()


def test_b12a_contract_signature_names_layer_and_keeps_the_never_omitted_promise():
    """The `list` row names every flag that ships, and still carries behavior 1's rule.

    The `--layer` assertion is INVERTED from iteration 01, not dropped, and the
    direction it flipped is the point: iteration 01 required the row to promise no
    flag the CLI lacked, and iteration 84 shipped the flag, so the same rule now
    requires the row to NAME it. `tests/test_iter10_behavior.py` enforces that
    correspondence generally, in both directions, derived from `build_parser()`; this
    stays because the general oracle reads the invocation cell only and cannot see the
    `never omitted` promise, which is the one sentence `radar list` exists to keep.
    """
    rows = [ln for ln in _lines("docs/CONSUMER_CONTRACT.md")
            if ln.startswith("| `radar list")]
    assert len(rows) == 1, rows
    assert "--layer" in rows[0]
    assert "--json" in rows[0] and "--floor" in rows[0]
    assert "never omitted" in rows[0]


def test_b12b_quickstart_does_not_claim_one_line_per_ranked_gap():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "one line per ranked gap" not in readme
    quickstart = [ln for ln in _lines("README.md") if ln.startswith("uv run radar list")]
    assert len(quickstart) == 1, quickstart
    assert "one line per record" in quickstart[0]


def test_b12c_the_counts_and_sections_claim_is_attributed_to_report_not_list():
    claim = "prints the count, the ranking, and the below-floor section separately"
    hits = [ln for ln in _lines("README.md") if claim in ln]
    assert len(hits) == 1, hits
    line = hits[0]
    assert line.index("radar report") < line.index(claim)
    assert "one line per record" in line
    assert "below-floor rows flagged" in line


def test_b11_readme_carries_the_layer_blockquote_directly_under_the_h1():
    lines = _lines("README.md")
    assert lines[0] == "# agent-gap-radar"
    assert lines[1] == ""
    assert lines[2] == (
        "> **Layer: an instrument above the stack.** It names where in an agent "
        "stack a gap lives and ranks it by evidence class; it implements no layer "
        "itself."
    )
