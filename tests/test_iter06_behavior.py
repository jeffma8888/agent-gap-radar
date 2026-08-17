"""Iteration 06 behaviors: `radar validate` refuses a domain it never examined.

Black-box. Nothing here imports or reads the implementation source, the engineer's
notes, or a diff -- every assertion drives `agent_gap_radar.cli.main` and observes only
the exit code, stdout and stderr. The two committed documents behavior 6 pins are read
as TEXT because they ARE the artifact under test there.

Two habits this file keeps on purpose:

* the zero-record stderr line is asserted as a FIXED string, and its path rendering is
  cross-checked against the pre-existing `Error: not a directory:` message so "rendered
  the same way" is MEASURED rather than assumed;
* the two-sided partner (behavior 3) derives the record count from the filesystem and
  asserts that count is non-zero first, so it can never pass vacuously over an emptied
  register -- which is the exact failure this iteration exists to make impossible.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
README_DOC = REPO_ROOT / "README.md"

ZERO_RECORD_PREFIX = "Error: no gap records found in "
NOT_A_DIRECTORY_PREFIX = "Error: not a directory: "
PRD_FLOOR_ERROR = "Error: no gap clears the confidence floor\n"

#: One schema-valid record, matching the shape the existing suite already uses.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _zero_record_line(examined: pathlib.Path) -> str:
    """The one line stderr must carry, naming the directory actually examined."""
    return f"{ZERO_RECORD_PREFIX}{examined}\n"


@pytest.fixture()
def empty_dir(tmp_path):
    """An existing directory holding no gap records and no `gaps/` subdirectory."""
    d = tmp_path / "register"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Behavior 1 -- an existing directory holding zero gap records is a FAILURE
# ---------------------------------------------------------------------------

def test_b1_empty_directory_exits_2_with_exactly_one_stderr_line(empty_dir, capsys):
    assert main(["validate", str(empty_dir)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _zero_record_line(empty_dir)
    assert captured.err.count("\n") == 1


def test_b1_empty_gaps_directory_names_the_directory_examined(tmp_path, capsys):
    """The argument is a root; the domain examined is its empty `gaps/`."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _zero_record_line(gaps)


def test_b1_empty_gaps_directory_passed_directly_is_the_same_failure(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    assert main(["validate", str(gaps)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _zero_record_line(gaps)


def test_b1_path_renders_the_same_way_the_existing_error_renders_its_path(
    tmp_path, empty_dir, capsys
):
    """Measured parity, not assumed: same rendering as `Error: not a directory:`."""
    not_a_dir = tmp_path / "a-file"
    not_a_dir.write_text("x", encoding="utf-8")
    assert main(["validate", str(not_a_dir)]) == 2
    existing = capsys.readouterr().err
    assert existing == f"{NOT_A_DIRECTORY_PREFIX}{not_a_dir}\n"

    assert main(["validate", str(empty_dir)]) == 2
    new = capsys.readouterr().err
    assert new == f"{ZERO_RECORD_PREFIX}{empty_dir}\n"
    # neither message quotes, repr()s, or relativises the path
    for message, prefix, path in (
        (existing, NOT_A_DIRECTORY_PREFIX, not_a_dir),
        (new, ZERO_RECORD_PREFIX, empty_dir),
    ):
        rendered = message[len(prefix):].rstrip("\n")
        assert rendered == str(path)
        assert "'" not in rendered and '"' not in rendered


def test_b1_a_directory_holding_only_non_record_files_is_still_empty(
    empty_dir, capsys
):
    (empty_dir / "notes.txt").write_text("not a record", encoding="utf-8")
    (empty_dir / "README").write_text("nor this", encoding="utf-8")
    assert main(["validate", str(empty_dir)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _zero_record_line(empty_dir)


# ---------------------------------------------------------------------------
# Behavior 2 -- a root with no `gaps/` subdirectory is the same failure
# ---------------------------------------------------------------------------

def test_b2_root_without_a_gaps_subdirectory_exits_2(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "src").mkdir()
    assert not (tmp_path / "gaps").exists()
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(ZERO_RECORD_PREFIX)
    assert captured.err == _zero_record_line(tmp_path)


def test_b2_a_path_one_level_too_high_no_longer_passes_green(tmp_path, capsys):
    """The `_resolve` fallback made visible: a typo must not certify a register."""
    real = tmp_path / "repo" / "gaps"
    real.mkdir(parents=True)
    (real / "GAP-001.json").write_text(json.dumps(RECORD), encoding="utf-8")
    # the real register is green ...
    assert main(["validate", str(tmp_path / "repo")]) == 0
    assert capsys.readouterr().out == "OK: 1 gap record(s) valid.\n"
    # ... while one level too high is now a refusal, not a green pass
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _zero_record_line(tmp_path)


# ---------------------------------------------------------------------------
# Behavior 3 -- two-sided partner: a non-empty register is untouched
# ---------------------------------------------------------------------------

def _committed_record_count() -> int:
    return len(sorted(GAPS_DIR.glob("*.json")))


def test_b3_the_derived_count_is_non_zero_so_behavior_3_cannot_pass_vacuously():
    assert GAPS_DIR.is_dir()
    assert _committed_record_count() > 0


def test_b3_committed_register_validates_green_with_a_derived_count(capsys):
    expected = f"OK: {_committed_record_count()} gap record(s) valid.\n"
    assert main(["validate", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == expected


def test_b3_repo_root_and_gaps_dir_are_byte_identical_on_stdout(capsys):
    assert main(["validate", str(REPO_ROOT)]) == 0
    root_out = capsys.readouterr().out
    assert main(["validate", str(GAPS_DIR)]) == 0
    gaps_out = capsys.readouterr().out
    assert gaps_out == root_out
    assert root_out.endswith("\n") and not root_out.endswith("\n\n")


def test_b3_a_freshly_built_single_record_register_is_green(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    (gaps / "GAP-001.json").write_text(json.dumps(RECORD), encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "OK: 1 gap record(s) valid.\n"


# ---------------------------------------------------------------------------
# Behavior 4 -- nothing else moved (the guard lives on the verdict verb only)
# ---------------------------------------------------------------------------

def test_b4_list_over_the_same_empty_directory_still_exits_0(empty_dir, capsys):
    assert main(["list", str(empty_dir)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert ZERO_RECORD_PREFIX not in captured.err


def test_b4_report_over_the_same_empty_directory_still_exits_0(empty_dir, capsys):
    assert main(["report", str(empty_dir)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out != ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


def test_b4_taxonomy_still_exits_0(capsys):
    assert main(["taxonomy"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


def test_b4_prd_over_the_same_empty_directory_keeps_its_own_error(empty_dir, capsys):
    assert main(["prd", str(empty_dir)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == PRD_FLOOR_ERROR
    assert ZERO_RECORD_PREFIX not in captured.err


def test_b4_the_new_message_reaches_no_verb_other_than_validate(empty_dir, capsys):
    """If the guard had been pushed into the shared loader, one of these would carry it."""
    for argv in (
        ["list", str(empty_dir)],
        ["report", str(empty_dir)],
        ["prd", str(empty_dir)],
        ["show", "GAP-001", str(empty_dir)],
    ):
        main(argv)
        captured = capsys.readouterr()
        assert ZERO_RECORD_PREFIX not in captured.err, argv
        assert ZERO_RECORD_PREFIX not in captured.out, argv


# ---------------------------------------------------------------------------
# Behavior 5 -- a schema failure is still reported as a schema failure
# ---------------------------------------------------------------------------

def test_b5_unparseable_record_is_not_masked_by_the_new_guard(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    (gaps / "bad.json").write_text("{nope", encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")
    assert ZERO_RECORD_PREFIX not in captured.err


def test_b5_schema_invalid_record_is_not_masked_by_the_new_guard(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    broken = dict(RECORD)
    broken["severity"] = 99
    (gaps / "GAP-001.json").write_text(json.dumps(broken), encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")
    assert ZERO_RECORD_PREFIX not in captured.err


def test_b5_a_missing_required_field_is_not_masked_either(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    broken = {k: v for k, v in RECORD.items() if k != "problem"}
    (gaps / "GAP-001.json").write_text(json.dumps(broken), encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")
    assert ZERO_RECORD_PREFIX not in captured.err


def test_b5_both_failure_classes_share_exit_code_2_no_third_code(tmp_path, capsys):
    """One error code: the zero-record class and the schema class both exit 2."""
    empty = tmp_path / "empty"
    empty.mkdir()
    zero_code = main(["validate", str(empty)])
    capsys.readouterr()

    schema = tmp_path / "schema" / "gaps"
    schema.mkdir(parents=True)
    (schema / "bad.json").write_text("{nope", encoding="utf-8")
    schema_code = main(["validate", str(schema)])
    capsys.readouterr()

    assert zero_code == schema_code == 2


# ---------------------------------------------------------------------------
# Behavior 6 -- the committed contract no longer publishes a false `iff`
# ---------------------------------------------------------------------------

def test_b6_contract_has_exactly_one_validate_row_stating_the_precondition():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| `radar validate ")]
    assert len(rows) == 1, rows
    assert "zero records" in rows[0], rows[0]


def test_b6_contract_no_longer_publishes_the_false_biconditional():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "iff every record parses" not in text


def test_b6_readme_quickstart_line_names_the_zero_record_failure():
    text = README_DOC.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("uv run radar validate")]
    assert len(lines) == 1, lines
    assert "zero record" in lines[0].lower(), lines[0]


def test_b6_the_documented_error_convention_still_holds_for_the_new_path(
    empty_dir, capsys
):
    """The docs promise `Error: ` on stderr + exit 2; the new path must obey it."""
    assert main(["validate", str(empty_dir)]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: ")
    assert captured.err.endswith("\n")
    assert captured.out == ""


# ---------------------------------------------------------------------------
# Acceptance criteria -- determinism on both sides of the new exit-code contract
# ---------------------------------------------------------------------------

def test_ac_validate_is_byte_stable_across_two_identical_invocations(capsys):
    assert main(["validate", str(REPO_ROOT)]) == 0
    first = capsys.readouterr()
    assert main(["validate", str(REPO_ROOT)]) == 0
    second = capsys.readouterr()
    assert (second.out, second.err) == (first.out, first.err)


def test_ac_the_new_failure_path_is_byte_stable_too(empty_dir, capsys):
    assert main(["validate", str(empty_dir)]) == 2
    first = capsys.readouterr()
    assert main(["validate", str(empty_dir)]) == 2
    second = capsys.readouterr()
    assert (second.out, second.err) == (first.out, first.err)


def test_ac_non_empty_register_verbs_still_end_in_exactly_one_newline(tmp_path, capsys):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    (gaps / "GAP-001.json").write_text(json.dumps(RECORD), encoding="utf-8")
    for argv in (
        ["validate", str(tmp_path)],
        ["list", str(tmp_path)],
        ["report", str(tmp_path)],
        ["show", "GAP-001", str(tmp_path)],
    ):
        assert main(argv) == 0, argv
        out = capsys.readouterr().out
        assert out.endswith("\n") and not out.endswith("\n\n"), argv


def test_ac_the_touched_documents_carry_no_absolute_machine_path():
    """Public-repo bar. Scoped to the two docs this iteration edited -- NOT to this
    file, because a scanner whose needles are literals matches itself and reports a
    leak it created (caught live this run: the self-scanning version failed on its
    own assertion line)."""
    for doc in (CONTRACT_DOC, README_DOC):
        text = doc.read_text(encoding="utf-8")
        assert "/Users/" not in text, doc.name
        assert "/home/" not in text, doc.name
        assert "/private/var/" not in text, doc.name


def test_b1_a_relative_argument_is_echoed_as_given_by_both_messages(
    tmp_path, monkeypatch, capsys
):
    """A CI gate passes a relative path. Both messages echo it verbatim -- unresolved,
    unquoted -- so the new line renders its path exactly like the pre-existing one."""
    (tmp_path / "register").mkdir()
    (tmp_path / "a-file").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "register"]) == 2
    assert capsys.readouterr().err == f"{ZERO_RECORD_PREFIX}register\n"
    assert main(["validate", "a-file"]) == 2
    assert capsys.readouterr().err == f"{NOT_A_DIRECTORY_PREFIX}a-file\n"
