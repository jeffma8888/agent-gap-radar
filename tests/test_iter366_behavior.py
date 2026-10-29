"""Iteration 366 behaviors: ``radar list --match TEXT`` searches the builder's own words.

The PM stage died this iteration (``pm.md`` is a placeholder), so the Expected
Behaviors are taken from the lead-ranked scout candidate (``pm_scout_a.md``
A1), the PRODUCT.md done-ledger row for iteration 366, and the published
``docs/CONSUMER_CONTRACT.md`` ``radar list`` row:

  EB1  ``--match TEXT`` narrows the record domain to records whose ``title``,
       ``problem``, ``symptom``, ``why_now``, ``existing``, ``build_hypothesis``
       or ``tags`` contain TEXT; evidence quotes are not searched.
  EB2  the test is a case-folded LITERAL substring: never a regex, no
       word-boundary semantics (``eval`` also matches ``retrieval``).
  EB3  ranked order is unchanged: the narrowed listing is the unfiltered
       listing with non-matching lines removed.
  EB4  a matching below-floor record is still displayed and still flagged.
  EB5  no match is exit 0 and an empty document (the same as an empty
       ``--layer``); a blank TEXT is exit 2 with an ``Error: `` line.
  EB6  it composes with ``--layer``, ``--floor`` and ``--json``.
  EB7  under ``--json`` a ``match`` key echoing TEXT sits directly after
       ``layer`` ONLY when the flag is given.
  EB8  every document ends in exactly one newline.

THE ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or reviewer's notes, or any diff. Behavior is driven
through the public ``main()`` entry point and compared against an oracle
computed from the register's own JSON data files.

Ambiguities, recorded: (1) the record ``id`` is not in the named field set, so
whether ``--match GAP-0`` matches is left unpinned; (2) "blank" is read as
empty-or-whitespace-only.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
REGISTER_DIR = REPO / "gaps"
SEARCHED = ("title", "problem", "symptom", "why_now", "existing", "build_hypothesis", "tags")

BASE = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "existing": ["no product ships"], "build_hypothesis": "b", "tags": ["plain"],
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _record(gap_id: str, **overrides) -> dict:
    rec = copy.deepcopy(BASE)
    rec["id"] = gap_id
    rec.update(overrides)
    return rec


def _write(tmp_path: pathlib.Path, *records: dict) -> pathlib.Path:
    d = tmp_path / "gaps"
    d.mkdir()
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return tmp_path


def run(capsys, argv):
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def ids_md(out: str) -> list[str]:
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def oracle(needle: str) -> set[str]:
    """Records of the LIVE register whose searched prose contains ``needle``."""
    hits = set()
    for path in sorted(REGISTER_DIR.glob("GAP-*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for field in SEARCHED:
            value = rec.get(field)
            if isinstance(value, list):
                parts.extend(str(v) for v in value)
            elif value is not None:
                parts.append(str(value))
        if any(needle.casefold() in p.casefold() for p in parts):
            hits.add(rec["id"])
    return hits


# EB1 -- each named field is searched -------------------------------------


def _set_token(field: str, token: str) -> dict:
    if field in ("existing", "tags"):
        return {field: [*BASE[field], token]}
    return {field: f"{BASE[field]} {token}"}


@pytest.mark.parametrize("field", SEARCHED)
def test_eb1_each_named_field_is_searched(tmp_path, capsys, field):
    token = "zqxtoken"
    root = _write(tmp_path, _record("GAP-001", **_set_token(field, token)), _record("GAP-002"))
    code, out, err = run(capsys, ["list", root, "--match", token])
    assert code == 0, err
    assert ids_md(out) == ["GAP-001"], out


def test_eb1_evidence_quote_is_not_searched(tmp_path, capsys):
    rec = _record("GAP-001")
    rec["evidence"][0]["quote"] = "the verbatim zqxquote line"
    root = _write(tmp_path, rec, _record("GAP-002"))
    code, out, err = run(capsys, ["list", root, "--match", "zqxquote"])
    assert code == 0, err
    assert ids_md(out) == [], out


@pytest.mark.parametrize("needle", ["eval", "memory", "budget", "replay", "sandbox"])
def test_eb1_live_register_matches_the_field_oracle(capsys, needle):
    code, out, err = run(capsys, ["list", REPO, "--match", needle])
    assert code == 0, err
    expected = oracle(needle)
    assert expected, f"oracle found nothing for {needle!r}; the needle set is stale"
    assert set(ids_md(out)) == expected
    assert len(ids_md(out)) == len(expected), "a record was listed twice"


def test_eb1_prose_search_finds_more_than_titles(capsys):
    """The scout's measured point: `eval` hits more records than titles alone."""
    code, out, _ = run(capsys, ["list", REPO, "--json", "--match", "eval"])
    assert code == 0
    payload = json.loads(out)
    titles = [r for r in payload["records"] if "eval" in r["title"].casefold()]
    assert len(payload["records"]) > len(titles) > 0


# EB2 -- case-folded literal substring --------------------------------------


@pytest.mark.parametrize("needle", ["THING", "thing", "tHiNg", "BROKEN"])
def test_eb2_match_is_case_folded(tmp_path, capsys, needle):
    root = _write(tmp_path, _record("GAP-001"), _record("GAP-002", title="Unrelated words"))
    code, out, err = run(capsys, ["list", root, "--match", needle])
    assert code == 0, err
    assert ids_md(out) == ["GAP-001"]


def test_eb2_case_folding_is_full_casefold(tmp_path, capsys):
    root = _write(tmp_path, _record("GAP-001", title="Broken on the strasse"))
    code, out, _ = run(capsys, ["list", root, "--match", "STRAßE"])
    assert code == 0
    assert ids_md(out) == ["GAP-001"]


@pytest.mark.parametrize("needle", ["a.c", "thing.*broken", "^A", "broken$", "[ab]"])
def test_eb2_regex_metacharacters_are_literal(tmp_path, capsys, needle):
    root = _write(tmp_path, _record("GAP-001", title="A thing is broken abc"))
    code, out, err = run(capsys, ["list", root, "--match", needle])
    assert code == 0, err
    assert ids_md(out) == [], f"{needle!r} was interpreted as a regex: {out!r}"


@pytest.mark.parametrize("needle", ["(", "[", "a+b(c", "*"])
def test_eb2_metacharacters_match_themselves_and_never_error(tmp_path, capsys, needle):
    root = _write(
        tmp_path,
        _record("GAP-001", title=f"Literal {needle} inside"),
        _record("GAP-002", title="Nothing special"),
    )
    code, out, err = run(capsys, ["list", root, "--match", needle])
    assert code == 0, err
    assert err == ""
    assert ids_md(out) == ["GAP-001"]


def test_eb2_no_word_boundary_semantics(tmp_path, capsys):
    root = _write(tmp_path, _record("GAP-001", title="Retrieval is unscoped"))
    code, out, _ = run(capsys, ["list", root, "--match", "eval"])
    assert code == 0
    assert ids_md(out) == ["GAP-001"]


# EB3 -- ranked order unchanged ----------------------------------------------


@pytest.mark.parametrize("needle", ["eval", "memory", "tenant"])
def test_eb3_narrowed_listing_is_a_line_subsequence_of_the_full_listing(capsys, needle):
    code_all, full, _ = run(capsys, ["list", REPO])
    code, narrowed, _ = run(capsys, ["list", REPO, "--match", needle])
    assert code_all == code == 0
    keep = oracle(needle)
    expected = [line for line in full.splitlines() if line.strip() and line.split()[0] in keep]
    assert [line for line in narrowed.splitlines() if line.strip()] == expected


def test_eb3_json_records_are_the_full_json_records_filtered(capsys):
    _, full, _ = run(capsys, ["list", REPO, "--json"])
    _, narrowed, _ = run(capsys, ["list", REPO, "--json", "--match", "budget"])
    keep = oracle("budget")
    expected = [r for r in json.loads(full)["records"] if r["gap_id"] in keep]
    assert json.loads(narrowed)["records"] == expected


# EB4 -- below-floor matches are displayed and flagged ------------------------


def test_eb4_below_floor_match_is_displayed_and_flagged_markdown(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--floor", "6", "--match", "sandbox"])
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip()]
    assert {line.split()[0] for line in lines} == oracle("sandbox")
    assert all(line.endswith("[below-floor]") for line in lines), out


def test_eb4_default_floor_below_floor_record_is_still_listed(capsys):
    _, full, _ = run(capsys, ["list", REPO, "--json"])
    below = [r for r in json.loads(full)["records"] if r["below_floor"]]
    assert below, "live register has no below-floor record; pick another fixture"
    target = below[0]
    code, out, _ = run(capsys, ["list", REPO, "--json", "--match", target["title"]])
    assert code == 0
    payload = json.loads(out)
    got = [r for r in payload["records"] if r["gap_id"] == target["gap_id"]]
    assert got == [target]
    assert payload["counts"]["below_floor"] >= 1


def test_eb4_json_counts_partition_the_matched_records(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json", "--floor", "5", "--match", "memory"])
    assert code == 0
    payload = json.loads(out)
    recs = payload["records"]
    counts = payload["counts"]
    assert counts["total"] == len(recs) == len(oracle("memory"))
    assert counts["below_floor"] == sum(r["below_floor"] for r in recs)
    assert counts["ranked"] + counts["below_floor"] == counts["total"]


# EB5 -- empty result and blank needle ---------------------------------------


def test_eb5_no_match_is_exit_zero_and_the_empty_layer_document(tmp_path, capsys):
    root = _write(tmp_path, _record("GAP-001"))
    code, out, err = run(capsys, ["list", root, "--match", "zz-no-such-words-zz"])
    assert code == 0
    assert err == ""
    code_l, empty_layer, _ = run(capsys, ["list", root, "--layer", "context-memory"])
    assert code_l == 0
    assert out == empty_layer
    assert ids_md(out) == []


def test_eb5_no_match_json_is_a_valid_empty_record_list(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json", "--match", "zz-no-such-words-zz"])
    assert code == 0
    payload = json.loads(out)
    assert payload["records"] == []
    assert payload["counts"]["total"] == 0
    assert payload["match"] == "zz-no-such-words-zz"


@pytest.mark.parametrize("needle", ["", " ", "   ", "\t"])
@pytest.mark.parametrize("as_json", [False, True])
def test_eb5_blank_needle_is_refused(capsys, needle, as_json):
    argv = ["list", REPO, "--match", needle] + (["--json"] if as_json else [])
    code, out, err = run(capsys, argv)
    assert code == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert err.endswith("\n") and not err.endswith("\n\n")


# EB6 -- composition ---------------------------------------------------------


def test_eb6_composes_with_layer_as_an_intersection(capsys):
    _, layer_out, _ = run(capsys, ["list", REPO, "--json", "--layer", "context-memory"])
    layer_ids = {r["gap_id"] for r in json.loads(layer_out)["records"]}
    code, out, _ = run(capsys, ["list", REPO, "--json", "--layer", "context-memory", "--match", "eval"])
    assert code == 0
    payload = json.loads(out)
    assert {r["gap_id"] for r in payload["records"]} == layer_ids & oracle("eval")
    assert payload["layer"] == "context-memory"
    assert payload["match"] == "eval"


def test_eb6_floor_is_echoed_and_applied(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json", "--floor", "6", "--match", "sandbox"])
    assert code == 0
    payload = json.loads(out)
    assert payload["confidence_floor"] == 6
    assert payload["records"] and all(r["below_floor"] for r in payload["records"])


def test_eb6_bad_layer_still_refused_with_match(capsys):
    code, out, err = run(capsys, ["list", REPO, "--layer", "no-such-layer", "--match", "eval"])
    assert code == 2
    assert out == ""
    assert err.startswith("Error: ")


# EB7 -- the JSON `match` key -----------------------------------------------


def test_eb7_match_key_sits_directly_after_layer_and_echoes_text_verbatim(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json", "--match", "SandBox"])
    assert code == 0
    payload = json.loads(out)
    keys = list(payload)
    assert keys.index("match") == keys.index("layer") + 1
    assert keys == ["confidence_floor", "layer", "match", "counts", "records"]
    assert payload["match"] == "SandBox"


def test_eb7_match_key_absent_without_the_flag(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json"])
    assert code == 0
    assert list(json.loads(out)) == ["confidence_floor", "layer", "counts", "records"]


def test_eb7_record_objects_keep_their_published_key_order(capsys):
    code, out, _ = run(capsys, ["list", REPO, "--json", "--match", "eval"])
    assert code == 0
    expected = ["gap_id", "title", "layer", "gap_type", "status", "priority",
                "confidence", "below_floor", "strongest_source", "needs"]
    recs = json.loads(out)["records"]
    assert recs
    assert all(list(r) == expected for r in recs)


# EB8 -- one trailing newline, deterministic ---------------------------------


@pytest.mark.parametrize("argv", [
    ["--match", "eval"],
    ["--json", "--match", "eval"],
    ["--match", "zz-no-such-words-zz"],
    ["--json", "--match", "zz-no-such-words-zz"],
])
def test_eb8_exactly_one_trailing_newline(capsys, argv):
    code, out, _ = run(capsys, ["list", REPO, *argv])
    assert code == 0
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-5:])


def test_eb8_output_is_byte_stable_across_runs(capsys):
    first = run(capsys, ["list", REPO, "--json", "--match", "memory"])
    second = run(capsys, ["list", REPO, "--json", "--match", "memory"])
    assert first == second
