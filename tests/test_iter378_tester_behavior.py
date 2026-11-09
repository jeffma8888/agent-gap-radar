"""Iteration 378 (tester, black-box): ``radar prd --layer L / --match TEXT``.

Every fixture here is built so the narrowed selection DIFFERS from the bare one, so a
build that ignores a selector, or falls back to the global top, goes red rather than
passing by coincidence. The byte oracle for a selected record is always
``radar prd --gap <ID>`` on the same register, never a hand-written document.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from agent_gap_radar.cli import main

NEEDLE = "quokka"

EV = {"source_class": "first-party-field", "title": "INC-1",
      "locator": "https://example.invalid/inc1", "date": "2026-01-02",
      "quote": "the verbatim line"}

BASE = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "existing": ["no product ships"], "build_hypothesis": "b", "tags": ["plain"],
    "severity": 3, "frequency": 3, "tractability": 3, "evidence": [EV],
}


def _ev(source_class: str) -> list[dict]:
    return [{**EV, "source_class": source_class}]


def _register(tmp_path: pathlib.Path, *records: dict) -> pathlib.Path:
    root = tmp_path / "reg"
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    for overrides in records:
        rec = copy.deepcopy(BASE)
        rec.update(overrides)
        (gaps / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return root


def _run(capsys, argv: list) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _selected(capsys, root, flags: list) -> str:
    """Which record's prd did the narrowed call emit? Found by byte-equality with --gap."""
    code, out, err = _run(capsys, ["prd", root, *flags])
    assert (code, err) == (0, ""), err
    assert out.endswith("\n") and not out.endswith("\n\n")
    ids = sorted(p.name[:-5] for p in (pathlib.Path(root) / "gaps").glob("*.json"))
    hits = [i for i in ids if _run(capsys, ["prd", root, "--gap", i])[1] == out]
    assert len(hits) == 1, hits
    return hits[0]


def _refusal(capsys, argv: list) -> str:
    code, out, err = _run(capsys, argv)
    assert (code, out) == (2, ""), (code, out, err)
    return err.splitlines()[-1]


# --- behavior 3: every published match field, and the quote exclusion ----------------

FIELDS = [
    ("title", f"A {NEEDLE} title"),
    ("problem", f"problem with {NEEDLE}"),
    ("symptom", f"symptom {NEEDLE}"),
    ("why_now", f"why {NEEDLE} now"),
    ("existing", ["nothing", f"a {NEEDLE} tool"]),
    ("build_hypothesis", f"build a {NEEDLE}"),
    ("tags", ["plain", NEEDLE]),
]


@pytest.mark.parametrize("field, value", FIELDS, ids=[f for f, _ in FIELDS])
def test_b3_each_match_field_selects_the_lower_ranked_record(tmp_path, capsys, field, value):
    root = _register(
        tmp_path,
        {"id": "GAP-001", "severity": 5, "frequency": 5, "tractability": 5},
        {"id": "GAP-002", "severity": 2, "frequency": 2, "tractability": 2, field: value},
    )
    assert _selected(capsys, root, []) == "GAP-001"
    assert _selected(capsys, root, ["--match", NEEDLE]) == "GAP-002"
    assert _selected(capsys, root, ["--match", NEEDLE.upper()]) == "GAP-002"
    assert _selected(capsys, root, ["--match", "QuOkK"]) == "GAP-002"


def test_b3_a_needle_only_in_an_evidence_quote_matches_nothing(tmp_path, capsys):
    root = _register(
        tmp_path,
        {"id": "GAP-001"},
        {"id": "GAP-002", "evidence": [{**EV, "quote": f"a {NEEDLE} said so"}]},
    )
    assert _refusal(capsys, ["prd", root, "--match", NEEDLE]) == (
        f"Error: no gap record matches --match {NEEDLE}")


def test_b3_match_is_a_literal_substring_not_a_regex(tmp_path, capsys):
    root = _register(
        tmp_path,
        {"id": "GAP-001", "severity": 5, "frequency": 5, "tractability": 5,
         "title": "aXb plain"},
        {"id": "GAP-002", "severity": 2, "frequency": 2, "tractability": 2,
         "title": "literal a.b here"},
    )
    assert _selected(capsys, root, ["--match", "a.b"]) == "GAP-002"


# --- behavior 2: layer, and layer x match intersection --------------------------------

def _three(tmp_path):
    return _register(
        tmp_path,
        {"id": "GAP-001", "severity": 5, "frequency": 5, "tractability": 5,
         "title": f"{NEEDLE} high"},
        {"id": "GAP-002", "severity": 4, "frequency": 4, "tractability": 4,
         "layer": "cost-governance"},
        {"id": "GAP-003", "severity": 2, "frequency": 2, "tractability": 2,
         "layer": "cost-governance", "title": f"{NEEDLE} low"},
    )


@pytest.mark.parametrize("flags, expected", [
    ([], "GAP-001"),
    (["--match", NEEDLE], "GAP-001"),
    (["--layer", "cost-governance"], "GAP-002"),
    (["--layer", "cost-governance", "--match", NEEDLE], "GAP-003"),
    (["--match", NEEDLE, "--layer", "cost-governance"], "GAP-003"),
])
def test_b2_layer_and_match_intersect(tmp_path, capsys, flags, expected):
    assert _selected(capsys, _three(tmp_path), flags) == expected


def test_b2_selection_agrees_with_list_json_under_the_same_flags(tmp_path, capsys):
    root = _three(tmp_path)
    for flags in (["--layer", "cost-governance"], ["--match", NEEDLE],
                  ["--layer", "cost-governance", "--match", NEEDLE]):
        code, out, _ = _run(capsys, ["list", root, *flags, "--json"])
        assert code == 0
        first = next(r["gap_id"] for r in json.loads(out)["records"]
                     if not r["below_floor"] and r["status"] in ("open", "partially-addressed"))
        assert _selected(capsys, root, flags) == first


# --- behavior 4: the floor applies inside the narrowed domain -------------------------

def test_b4_a_below_floor_match_beside_an_above_floor_non_match_refuses(tmp_path, capsys):
    root = _register(
        tmp_path,
        {"id": "GAP-001", "title": f"{NEEDLE} only here",
         "severity": 5, "frequency": 5, "tractability": 5, "evidence": _ev("model-output")},
        {"id": "GAP-002", "severity": 2, "frequency": 2, "tractability": 2},
    )
    assert _selected(capsys, root, []) == "GAP-002"
    assert _refusal(capsys, ["prd", root, "--match", NEEDLE]) == (
        "Error: no gap clears the confidence floor 2")
    # displayed, never dropped: list under the same flag still shows it, marked
    code, out, _ = _run(capsys, ["list", root, "--match", NEEDLE])
    assert code == 0 and "GAP-001" in out and "[below-floor]" in out
    # and lowering the floor inside the domain selects it
    assert _selected(capsys, root, ["--match", NEEDLE, "--floor", "0"]) == "GAP-001"


def test_b4_the_floor_moves_the_narrowed_selection(tmp_path, capsys):
    root = _register(
        tmp_path,
        {"id": "GAP-001", "severity": 5, "frequency": 5, "tractability": 5},
        {"id": "GAP-002", "title": f"{NEEDLE} c3", "evidence": _ev("practitioner-report"),
         "severity": 4, "frequency": 4, "tractability": 4},
        {"id": "GAP-003", "title": f"{NEEDLE} c5",
         "severity": 2, "frequency": 2, "tractability": 2},
    )
    assert _selected(capsys, root, ["--match", NEEDLE]) == "GAP-002"
    assert _selected(capsys, root, ["--match", NEEDLE, "--floor", "4"]) == "GAP-003"
    assert _refusal(capsys, ["prd", root, "--match", NEEDLE, "--floor", "6"]) == (
        "Error: no gap clears the confidence floor 6")


# --- behavior 5: an empty narrowed domain names exactly the flags given ---------------

@pytest.mark.parametrize("flags, spelled", [
    (["--match", "ZzzQqq"], "--match ZzzQqq"),
    (["--layer", "multi-agent"], "--layer multi-agent"),
    (["--layer", "cost-governance", "--match", "absent-word"],
     "--layer cost-governance --match absent-word"),
])
def test_b5_empty_domain_in_a_populated_register(tmp_path, capsys, flags, spelled):
    root = _three(tmp_path)
    assert _refusal(capsys, ["prd", root, *flags]) == f"Error: no gap record matches {spelled}"


# --- behavior 6: an all-terminal narrowed domain is the existing refusal --------------

def test_b6_terminal_domain_line_equals_the_bare_all_terminal_line(tmp_path, capsys):
    all_terminal = _register(tmp_path / "a", {"id": "GAP-001", "status": "retired"})
    existing = _refusal(capsys, ["prd", all_terminal])
    assert existing.startswith("Error: every gap record carries a terminal status; ")
    root = _register(
        tmp_path / "b",
        {"id": "GAP-001", "severity": 2, "frequency": 2, "tractability": 2},
        {"id": "GAP-002", "layer": "cost-governance", "status": "addressed",
         "severity": 5, "frequency": 5, "tractability": 5},
        {"id": "GAP-003", "layer": "cost-governance", "status": "retired"},
    )
    assert _selected(capsys, root, []) == "GAP-001"
    assert _refusal(capsys, ["prd", root, "--layer", "cost-governance"]) == existing


# --- behavior 7/8/9: refusals before the register is read -----------------------------

GAP_COMBINED = "Error: --gap names the record, so it cannot be combined with --layer or --match"


@pytest.mark.parametrize("flags", [["--layer", "cost-governance"], ["--match", NEEDLE]])
def test_b7_gap_with_selector_is_refused_even_when_both_would_agree(tmp_path, capsys, flags):
    root = _three(tmp_path)
    assert _refusal(capsys, ["prd", root, "--gap", "GAP-003", *flags]) == GAP_COMBINED
    assert _refusal(capsys, ["prd", root, *flags, "--gap", "GAP-003"]) == GAP_COMBINED


def test_b8_unknown_layer_with_match_is_the_list_line(tmp_path, capsys):
    absent = tmp_path / "nothing-here"
    prd = _refusal(capsys, ["prd", absent, "--layer", "Cost-Governance", "--match", NEEDLE])
    lst = _refusal(capsys, ["list", absent, "--layer", "Cost-Governance"])
    assert prd.startswith("Error: unknown layer 'Cost-Governance'; the layer vocabulary is closed: ")
    assert prd == lst


@pytest.mark.parametrize("needle", ["\t", " \n "])
def test_b9_whitespace_only_match_is_refused_on_a_real_register(tmp_path, capsys, needle):
    root = _three(tmp_path)
    assert _refusal(capsys, ["prd", root, "--match", needle]) == (
        "Error: --match needs non-blank TEXT; omit the flag to select from every record")


# --- behavior 10: unflagged prd still selects the global top -------------------------
# Iteration 389 gave `scan` the `--match` flag this node used to prove absent; it is
# re-pinned to the blank-TEXT refusal, which is what still makes `--match` exit 2 there.

def test_b10_scan_match_refuses_blank_text(tmp_path, capsys):
    root = _three(tmp_path)
    code, out, err = _run(capsys, ["scan", root, "--gaps", root, "--prd", "--match", "  "])
    assert (code, out) == (2, "")
    assert "--match" in err.splitlines()[-1]
    assert err.splitlines()[-1].startswith("Error: ")


@pytest.mark.parametrize("extra", [[], ["--floor", "0"], ["--project", "demo"]])
def test_b10_unflagged_prd_is_the_global_top(tmp_path, capsys, extra):
    root = _three(tmp_path)
    code, out, err = _run(capsys, ["prd", root, *extra])
    assert (code, err) == (0, "")
    assert (code, out, err) == _run(capsys, ["prd", root, "--gap", "GAP-001", *extra])
