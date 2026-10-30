"""Iteration 367 behaviors: a gap id typed into a register-path slot says so.

Expected Behaviors (from the iteration-367 PM spec):

  EB1  a register-path argument that is not an existing directory and is shaped
       like a gap id (``^(?:gap-)?0*(\\d+)$`` case-insensitively, 1..999) gets
       exactly one stderr line:
       ``Error: not a directory: <arg> (that looks like gap id <GAP-NNN>; try
       'radar show <GAP-NNN>' or 'radar prd --gap <GAP-NNN>')``, empty stdout,
       exit 2.
  EB2  ``prd``/``list``/``report``/``validate GAP-001`` each give that line.
  EB3  loose ids (``7``, ``gap-12``) are canonicalized in the hint only.
  EB4  a swapped ``show . GAP-001`` gives the EB1 line for ``GAP-001``.
  EB5  non-id-shaped arguments keep the old line byte-for-byte, no hint.
  EB6  a real id-shaped directory is never second-guessed; the hint never
       rides on any other refusal (``no such gap:``, ``cannot scan target:``).
  EB7  success paths are unchanged.

THE ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or reviewer's notes, or any diff.  Behavior is driven
through the public in-process ``main()`` entry point with ``capsys``.

EB7 note: the byte-identical-to-HEAD comparison was MEASURED by the tester
against an archived HEAD tree (see tester.md) and is deliberately not
committed as a frozen-sha arm.  What is committed is that every success path
is exit 0, deterministic across runs, ends in one newline, never carries the
hint, and does not depend on how the register path is spelled.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
REGISTER_DIR = REPO / "gaps"
HINT_MARK = "that looks like gap id"


def run(capsys, argv):
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def hint_line(arg: str, gap: str) -> str:
    return (
        f"Error: not a directory: {arg} (that looks like gap id {gap}; "
        f"try 'radar show {gap}' or 'radar prd --gap {gap}')\n"
    )


@pytest.fixture
def empty_cwd(tmp_path, monkeypatch):
    """A cwd in which no id-shaped name exists as a directory."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


# --- EB1 / EB2 -----------------------------------------------------------------

@pytest.mark.parametrize("verb", ["prd", "list", "report", "validate"])
def test_eb2_each_register_verb_names_the_right_command(verb, empty_cwd, capsys):
    code, out, err = run(capsys, [verb, "GAP-001"])
    assert code == 2
    assert out == ""
    assert err == hint_line("GAP-001", "GAP-001")


def test_eb1_line_is_one_line_with_one_newline_and_error_prefix(empty_cwd, capsys):
    code, out, err = run(capsys, ["prd", "GAP-042"])
    assert (code, out) == (2, "")
    assert err.startswith("Error: ")
    assert err.endswith("\n") and not err.endswith("\n\n")
    assert err.count("\n") == 1
    assert err == hint_line("GAP-042", "GAP-042")


@pytest.mark.parametrize("typed,canon", [
    ("GAP-1", "GAP-001"), ("gap-001", "GAP-001"), ("Gap-99", "GAP-099"),
    ("999", "GAP-999"), ("0007", "GAP-007"), ("GAP-0120", "GAP-120"),
])
def test_eb1_grammar_positive_cases_get_the_canonical_hint(typed, canon, empty_cwd, capsys):
    code, out, err = run(capsys, ["list", typed])
    assert (code, out) == (2, "")
    assert err == hint_line(typed, canon)


# --- EB3 -----------------------------------------------------------------------

def test_eb3_spec_literal_bare_number(empty_cwd, capsys):
    code, out, err = run(capsys, ["prd", "7"])
    assert (code, out) == (2, "")
    assert err == ("Error: not a directory: 7 (that looks like gap id GAP-007; "
                   "try 'radar show GAP-007' or 'radar prd --gap GAP-007')\n")


def test_eb3_spec_literal_lowercase_prefix_keeps_typed_form(empty_cwd, capsys):
    code, out, err = run(capsys, ["list", "gap-12"])
    assert (code, out) == (2, "")
    assert err == hint_line("gap-12", "GAP-012")
    # the typed form is echoed verbatim, the canonical form only in the hint
    assert err.startswith("Error: not a directory: gap-12 (")


# --- EB4 -----------------------------------------------------------------------

def test_eb4_swapped_show_arguments_name_the_correct_show_command(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    code, out, err = run(capsys, ["show", ".", "GAP-001"])
    assert (code, out) == (2, "")
    assert err == hint_line("GAP-001", "GAP-001")
    # and the named command is in fact the correct one
    code2, out2, err2 = run(capsys, ["show", "GAP-001"])
    assert code2 == 0 and err2 == "" and out2.strip()


# --- EB5 -----------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["list", "nope"],
    ["prd", "GAP-000"],
    ["prd", "0"],
    ["prd", "GAP-1000"],
    ["list", "sub/GAP-001"],
    ["list", "GAP-1a"],
    ["list", "GAP_001"],
    ["list", "GAP-"],
    ["list", "1000"],
])
def test_eb5_not_id_shaped_keeps_the_old_line_byte_for_byte(argv, empty_cwd, capsys):
    code, out, err = run(capsys, argv)
    assert (code, out) == (2, "")
    assert err == f"Error: not a directory: {argv[1]}\n"
    assert HINT_MARK not in err


def test_eb5_missing_absolute_path_keeps_the_old_line(tmp_path, capsys):
    missing = tmp_path / "does-not-exist"
    code, out, err = run(capsys, ["list", missing])
    assert (code, out) == (2, "")
    assert err.startswith("Error: not a directory: ")
    assert err.endswith("does-not-exist\n")
    assert err.count("\n") == 1
    assert HINT_MARK not in err


# --- EB6 -----------------------------------------------------------------------

def _valid_record(gap_id: str) -> dict:
    return {
        "id": gap_id, "title": "A thing is broken", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "existing": ["no product ships"], "build_hypothesis": "b", "tags": ["plain"],
        "severity": 5, "frequency": 4, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                      "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                      "quote": "the verbatim line"}],
    }


def test_eb6_real_id_shaped_directory_is_never_second_guessed(tmp_path, monkeypatch, capsys):
    reg = tmp_path / "7"
    reg.mkdir()
    (reg / "GAP-001.json").write_text(json.dumps(_valid_record("GAP-001")), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code, out, err = run(capsys, ["list", "7"])
    assert code == 0, err
    assert HINT_MARK not in err and err == ""
    assert "GAP-001" in out
    for other in (reg, f".{os.sep}7", f"7{os.sep}"):
        code2, out2, err2 = run(capsys, ["list", other])
        assert (code2, err2) == (0, "")
        assert out2 == out
    # validate also accepts it as a directory, not as an id
    code3, _out3, err3 = run(capsys, ["validate", "7"])
    assert code3 == 0, err3
    assert HINT_MARK not in err3


def test_eb6_scan_refusal_is_unchanged(empty_cwd, capsys):
    code, out, err = run(capsys, ["scan", "GAP-001"])
    assert (code, out) == (2, "")
    assert err == "Error: cannot scan target: GAP-001\n"


def test_eb6_no_such_gap_refusal_carries_no_hint(capsys):
    code, out, err = run(capsys, ["show", "GAP-999", REGISTER_DIR])
    assert (code, out) == (2, "")
    assert err.startswith("Error: no such gap:")
    assert HINT_MARK not in err
    assert err.count("\n") == 1


def test_eb6_corrupt_register_refusal_carries_no_hint(tmp_path, capsys):
    reg = tmp_path / "GAP-001"  # an id-shaped name that IS a directory
    reg.mkdir()
    (reg / "GAP-001.json").write_text("{not json", encoding="utf-8")
    code, out, err = run(capsys, ["list", reg])
    assert (code, out) == (2, "")
    assert err.startswith("Error: ")
    assert HINT_MARK not in err
    assert "not a directory" not in err


# --- EB7 -----------------------------------------------------------------------

SUCCESS_ARGVS = [
    ["show", "GAP-001"],
    ["prd", "--gap", "GAP-001"],
    ["list"],
    ["prd"],
]


@pytest.mark.parametrize("argv", SUCCESS_ARGVS, ids=lambda a: " ".join(a))
def test_eb7_success_paths_exit_zero_deterministic_and_hint_free(argv, capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    code, out, err = run(capsys, argv)
    assert code == 0, err
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert HINT_MARK not in out
    code2, out2, err2 = run(capsys, argv)
    assert (code2, out2, err2) == (code, out, err)
    # spelling the register path explicitly gives the same bytes
    code3, out3, err3 = run(capsys, [*argv, REGISTER_DIR])
    assert (code3, out3, err3) == (code, out, err)


def test_eb7_prd_gap_document_is_json_for_the_named_gap(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    code, out, err = run(capsys, ["prd", "--gap", "GAP-001"])
    assert (code, err) == (0, "")
    doc = json.loads(out)
    assert "GAP-001" in json.dumps(doc)


def test_eb1_hint_names_commands_that_actually_work(empty_cwd, capsys, monkeypatch):
    """Following the hint verbatim (with the live register) succeeds."""
    code, out, err = run(capsys, ["prd", "gap-3"])
    assert code == 2
    m = re.search(r"try 'radar (show GAP-\d{3})' or 'radar (prd --gap GAP-\d{3})'", err)
    assert m, err
    monkeypatch.chdir(REPO)
    for cmd in m.groups():
        c, o, e = run(capsys, cmd.split())
        assert (c, e) == (0, ""), (cmd, e)
        assert o.strip()
