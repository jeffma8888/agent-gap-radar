"""Iteration 390: a `GAP-*` register entry whose name is a near-miss of `*.json` is refused.

Why this matters: the register's core invariant is that no record is silently dropped. A
record whose file name is `GAP-002-x.JSON` (a case-insensitive filesystem, an editor's
backup suffix, a `.jsonc` habit) used to be skipped by enumeration without a word, so
`radar validate` printed a green `OK:` over a smaller register. Now every verb that loads a
register refuses it with one `Error:` clause, exit 2.

NEAR-MISS (from the spec): the name, casefolded, starts with `gap-` AND contains `.json`,
AND does not end with exactly `.json`.

Black-box: drives `agent_gap_radar.cli.main` in-process (and one child process for the
HEAD-bytes control); fixtures are tmp dirs built from copies of committed records. Offline;
every path is derived from this file's location.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

from _iter401_section import without_identical_evidence_section

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"


def _clause(name: str) -> str:
    return f"{name}: looks like a gap record but is not named *.json, so it was not loaded"


def _live(prefix: str) -> pathlib.Path:
    (path,) = sorted(LIVE_GAPS.glob(f"{prefix}-*.json"))
    return path


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _register(tmp_path: pathlib.Path, *near_misses: str, dirname: str = "reg") -> pathlib.Path:
    """A dir holding GAP-001 under its committed name plus GAP-002 under each given name."""
    reg = tmp_path / dirname
    reg.mkdir()
    g1 = _live("GAP-001")
    shutil.copy(g1, reg / g1.name)
    for name in near_misses:
        shutil.copy(_live("GAP-002"), reg / name)
    return reg


def _assert_refused(code: int, out: str, err: str, *names: str) -> str:
    assert code == 2, (code, out, err)
    assert out == "", out
    lines = err.splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("Error: "), err
    for name in names:
        assert _clause(name) in lines[0], err
    return lines[0]


# ---------------------------------------------------------------------------
# Behaviors 1 and 2 -- each near-miss spelling is refused by `validate`.
# ---------------------------------------------------------------------------

NEAR_MISSES = [
    "GAP-002-x.JSON",
    "GAP-002-x.json.bak",
    "GAP-002-x.jsonc",
    "GAP-002-x.Json",
    "gap-002-x.json~",
]


@pytest.mark.parametrize("name", NEAR_MISSES)
def test_b1_b2_validate_refuses_each_near_miss_name(tmp_path, name):
    reg = _register(tmp_path, name)
    _assert_refused(*_run("validate", str(reg)), name)


def test_b1_control_the_same_copy_under_an_exact_json_name_validates(tmp_path):
    """Positive control: the refusal is about the NAME, not the copied record's content."""
    reg = _register(tmp_path, "GAP-002-x.json")
    assert _run("validate", str(reg)) == (0, "OK: 2 gap record(s) valid.\n", "")


# ---------------------------------------------------------------------------
# Behavior 3 -- every register-reading verb refuses.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", ["list", "report", "prd"])
def test_b3_register_reading_verbs_refuse(tmp_path, verb):
    reg = _register(tmp_path, "GAP-002-x.JSON")
    _assert_refused(*_run(verb, str(reg)), "GAP-002-x.JSON")


def test_b3_scan_with_gaps_refuses(tmp_path):
    reg = _register(tmp_path, "GAP-002-x.JSON")
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.py").write_text("print('hello')\n", encoding="utf-8")
    _assert_refused(*_run("scan", str(target), "--gaps", str(reg)), "GAP-002-x.JSON")


# ---------------------------------------------------------------------------
# Behavior 4 -- two near-misses: one line, sorted, `; `-joined, before other clauses.
# ---------------------------------------------------------------------------

def test_b4_two_near_misses_share_one_line_in_sorted_order(tmp_path):
    reg = _register(tmp_path, "GAP-003-y.json.bak", "GAP-002-x.JSON")
    line = _assert_refused(*_run("validate", str(reg)), "GAP-002-x.JSON", "GAP-003-y.json.bak")
    joined = _clause("GAP-002-x.JSON") + "; " + _clause("GAP-003-y.json.bak")
    assert joined in line, line


def test_b4_near_miss_clauses_precede_schema_and_duplicate_clauses(tmp_path):
    reg = _register(tmp_path, "GAP-003-y.json.bak", "GAP-002-x.JSON")
    shutil.copy(_live("GAP-001"), reg / "GAP-001-dup.json")  # duplicate gap id
    (reg / "GAP-004-bad.json").write_text(json.dumps({"id": "GAP-004"}), encoding="utf-8")
    line = _assert_refused(*_run("validate", str(reg)), "GAP-002-x.JSON", "GAP-003-y.json.bak")
    last_near = line.index(_clause("GAP-003-y.json.bak"))
    first_near = line.index(_clause("GAP-002-x.JSON"))
    assert first_near < last_near, line
    assert "GAP-004-bad.json:" in line, line
    assert last_near < line.index("GAP-004-bad.json:"), line
    assert "duplicate gap id" in line, line
    assert last_near < line.index("duplicate gap id"), line


# ---------------------------------------------------------------------------
# Behavior 5 -- reported together with a schema problem, no early exit.
# ---------------------------------------------------------------------------

def test_b5_near_miss_and_schema_invalid_record_in_one_line(tmp_path):
    reg = _register(tmp_path, "GAP-002-x.JSON")
    (reg / "GAP-004-bad.json").write_text(json.dumps({"id": "GAP-004"}), encoding="utf-8")
    line = _assert_refused(*_run("validate", str(reg)), "GAP-002-x.JSON")
    assert "GAP-004-bad.json:" in line, line


def test_b5_control_the_schema_invalid_record_alone_is_named(tmp_path):
    """Control: the GAP-004 fixture really is refused on its own, so b5 tests the join."""
    reg = _register(tmp_path)
    (reg / "GAP-004-bad.json").write_text(json.dumps({"id": "GAP-004"}), encoding="utf-8")
    code, out, err = _run("validate", str(reg))
    assert (code, out) == (2, ""), (code, out, err)
    assert err.startswith("Error: ") and "GAP-004-bad.json:" in err, err
    assert "looks like a gap record" not in err, err


# ---------------------------------------------------------------------------
# Behavior 6 -- non-record names stay ignored.
# ---------------------------------------------------------------------------

def test_b6_non_record_names_stay_ignored(tmp_path):
    reg = _register(tmp_path, "GAP-002-x.json")
    for name in ["README.md", ".DS_Store", "notes.JSON", "GAP-002-notes.md"]:
        (reg / name).write_text("not a record\n", encoding="utf-8")
    assert _run("validate", str(reg)) == (0, "OK: 2 gap record(s) valid.\n", "")


def test_tester_dot_prefixed_editor_swap_file_stays_ignored(tmp_path):
    """Ambiguity note: a vim swap file `.GAP-001-x.json.swp` casefolds to `.gap-...`, which
    does not START with `gap-`, so by the spec's definition it is not a near-miss."""
    reg = _register(tmp_path)
    (reg / ".GAP-001-x.json.swp").write_text("swap\n", encoding="utf-8")
    assert _run("validate", str(reg)) == (0, "OK: 1 gap record(s) valid.\n", "")


# ---------------------------------------------------------------------------
# Behavior 7 -- a dir whose only record-like entry is a near-miss names it.
# ---------------------------------------------------------------------------

def test_b7_only_a_near_miss_is_named_not_just_empty(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    shutil.copy(_live("GAP-001"), reg / "GAP-001-x.JSON")
    _assert_refused(*_run("validate", str(reg)), "GAP-001-x.JSON")


# ---------------------------------------------------------------------------
# Behavior 8 -- the committed register is unchanged.
# ---------------------------------------------------------------------------

def test_b8_committed_register_validates_with_every_json_record():
    count = len(list(LIVE_GAPS.glob("*.json")))
    assert count > 0
    assert _run("validate", str(LIVE_GAPS)) == (0, f"OK: {count} gap record(s) valid.\n", "")


def test_b8_committed_register_has_no_near_miss_names():
    bad = [p.name for p in LIVE_GAPS.iterdir()
           if p.name.casefold().startswith("gap-") and ".json" in p.name.casefold()
           and not p.name.endswith(".json")]
    assert bad == [], bad


_CHILD = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"


def _child(src: pathlib.Path, cwd: pathlib.Path, *argv: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(src)
    return subprocess.run([sys.executable, "-c", _CHILD, *argv], cwd=cwd, env=env,
                          capture_output=True, timeout=120)


@pytest.fixture(scope="module")
def head_tree(tmp_path_factory):
    """The committed HEAD tree, extracted offline with `git archive`."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("no git checkout to read HEAD from")
    dest = tmp_path_factory.mktemp("head")
    archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "HEAD", "src", "gaps"],
                             capture_output=True, check=True, timeout=120)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True,
                   timeout=120)
    return dest


@pytest.mark.parametrize("verb", ["validate", "list", "report"])
def test_b8_list_and_report_bytes_match_head(head_tree, verb):
    head = _child(head_tree / "src", head_tree, verb, "gaps")
    now = _child(REPO_ROOT / "src", REPO_ROOT, verb, "gaps")
    assert head.returncode == now.returncode == 0, (head.stderr, now.stderr)
    # iter 401 inserted `## Identical evidence sets`; it is subtracted from BOTH sides as a measured term
    # so every other byte is still compared (see `tests/_iter401_section.py`).
    assert (without_identical_evidence_section(now.stdout)
            == without_identical_evidence_section(head.stdout))
    assert now.stdout.endswith(b"\n") and not now.stdout.endswith(b"\n\n")


# ---------------------------------------------------------------------------
# Behavior 9 -- an unreadable register directory keeps its refusal.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root can read a mode-000 directory")
def test_b9_unreadable_register_directory_keeps_its_refusal(tmp_path):
    reg = _register(tmp_path, "GAP-002-x.JSON")
    reg.chmod(0)
    try:
        code, out, err = _run("validate", str(reg))
    finally:
        reg.chmod(0o755)
    assert (code, out) == (2, ""), (code, out, err)
    assert err.startswith("Error: "), err
    assert f"cannot read register directory: {reg}" in err, err
    assert "looks like a gap record" not in err, err
