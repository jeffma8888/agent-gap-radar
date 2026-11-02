"""Iteration 378: ``radar prd`` gains ``list``'s narrowing selectors, ``--layer`` and ``--match``.

The narrowed top must be the first row of ``radar list <same flags> --json`` that is
not below the floor and carries a citable status, so ``list`` is the oracle for every
live-register expectation here: a second, hand-written ranking would be a second
source of truth. Refusals (blank TEXT, unknown layer, ``--gap`` combined) fire before
the register is read, and every invocation without the new flags stays as it was.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]

BASE = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "existing": ["no product ships"], "build_hypothesis": "b", "tags": ["plain"],
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _register(tmp_path: pathlib.Path, *records: dict) -> pathlib.Path:
    """A tmp register of BASE copies, so each refusal is reached by a known domain."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for overrides in records:
        rec = copy.deepcopy(BASE)
        rec.update(overrides)
        (gaps / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return tmp_path


def _run(capsys, argv: list[str]) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _oracle_top(capsys, flags: list[str]) -> str:
    """The first ranked, above-floor, citable row of `list <flags> --json`."""
    code, out, _ = _run(capsys, ["list", REPO, *flags, "--json"])
    assert code == 0
    rows = [r for r in json.loads(out)["records"]
            if not r["below_floor"] and r["status"] in ("open", "partially-addressed")]
    assert rows, flags
    return rows[0]["gap_id"]


@pytest.mark.parametrize("flags", [
    ["--match", "sandbox"],
    ["--match", "cost"],
    ["--layer", "cost-governance"],
    ["--layer", "sandbox-isolation", "--match", "sandbox"],
])
def test_narrowed_prd_is_the_prd_of_lists_first_citable_row(capsys, flags):
    gap_id = _oracle_top(capsys, flags)
    code, out, err = _run(capsys, ["prd", REPO, *flags])
    assert (code, err) == (0, "")
    assert (code, out, err) == _run(capsys, ["prd", REPO, "--gap", gap_id])
    assert out.endswith("}\n") and not out.endswith("\n\n")


def test_narrowing_actually_moves_the_selection_off_the_global_top(capsys):
    _, bare, _ = _run(capsys, ["prd", REPO])
    _, narrowed, _ = _run(capsys, ["prd", REPO, "--match", "sandbox"])
    assert bare != narrowed


def test_match_is_case_folded(capsys):
    assert _run(capsys, ["prd", REPO, "--match", "SANDBOX"]) == _run(
        capsys, ["prd", REPO, "--match", "sandbox"])


def test_below_floor_matches_are_never_selected(tmp_path, capsys):
    root = _register(tmp_path, {"id": "GAP-001", "title": "needle here"},
                     {"id": "GAP-002"})
    code, out, err = _run(capsys, ["prd", root, "--match", "needle", "--floor", "6"])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1] == "Error: no gap clears the confidence floor 6"


@pytest.mark.parametrize("flags, spelled", [
    (["--match", "zzzqqq"], "--match zzzqqq"),
    (["--layer", "cost-governance"], "--layer cost-governance"),
    (["--layer", "orchestration", "--match", "zzzqqq"],
     "--layer orchestration --match zzzqqq"),
    (["--match", "zzzqqq", "--layer", "orchestration"],
     "--layer orchestration --match zzzqqq"),
])
def test_an_empty_narrowed_domain_names_the_flags(tmp_path, capsys, flags, spelled):
    root = _register(tmp_path, {"id": "GAP-001"})
    code, out, err = _run(capsys, ["prd", root, *flags])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1] == f"Error: no gap record matches {spelled}"


def test_an_all_terminal_narrowed_domain_is_the_existing_refusal(tmp_path, capsys):
    root = _register(tmp_path, {"id": "GAP-001", "title": "needle", "status": "addressed"},
                     {"id": "GAP-002"})
    code, out, err = _run(capsys, ["prd", root, "--match", "needle"])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1].startswith(
        "Error: every gap record carries a terminal status; the citable statuses are: ")


@pytest.mark.parametrize("flags", [["--layer", "orchestration"], ["--match", "x"],
                                   ["--layer", "orchestration", "--match", "x"]])
def test_gap_with_a_selector_is_refused_before_the_register_is_read(tmp_path, capsys, flags):
    code, out, err = _run(capsys, ["prd", tmp_path / "nothing-here", "--gap", "GAP-001", *flags])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1] == (
        "Error: --gap names the record, so it cannot be combined with --layer or --match")


def test_unknown_layer_is_the_list_refusal(tmp_path, capsys):
    absent = tmp_path / "nothing-here"
    prd = _run(capsys, ["prd", absent, "--layer", "no-such-layer"])
    lst = _run(capsys, ["list", absent, "--layer", "no-such-layer"])
    assert prd[:2] == (2, "")
    assert prd[2].splitlines()[-1].startswith("Error: unknown layer 'no-such-layer'; ")
    assert prd[2].splitlines()[-1] == lst[2].splitlines()[-1]


@pytest.mark.parametrize("needle", ["", "   "])
def test_blank_match_is_refused(tmp_path, capsys, needle):
    code, out, err = _run(capsys, ["prd", tmp_path / "nothing-here", "--match", needle])
    assert (code, out) == (2, "")
    assert err.splitlines()[-1] == (
        "Error: --match needs non-blank TEXT; omit the flag to select from every record")


def test_the_contract_row_and_readme_show_the_new_flags():
    contract = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    assert ("`radar prd [<repo>] [--gap <ID>] [--floor N] [--project NAME] "
            "[--with-fixtures] [--layer L] [--match TEXT]`") in contract
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert any("radar prd" in line and "--layer" in line and "--match" in line
               for line in readme.splitlines())
