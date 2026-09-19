"""Iteration 261 behavior tests (black-box; spec: state/iter-261/pm.md).

Feature: the roadmap brake ``tools/roadmap_integrity.py`` reads an optional
``PRODUCT_ARCHIVE.md`` beside the roadmap and judges ship coverage over the UNION of
both ledgers while judging ascending order within EACH file; an absent archive keeps
single-file semantics. Every fixture is a scratch pair under ``tmp_path``; no timing.

Behaviors 1-2 of the spec (the ledger MOVE into a tracked archive) are NOT asserted here:
the committed suite pins every historical ``- iter NN`` row inside the live ``PRODUCT.md``
(``test_iter04_behavior.py`` and eight siblings), so the move cannot be green alongside
``uv run pytest`` as the spec also requires. The tester report records that contradiction.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

PROG = "roadmap_integrity.py"

INDEX = """# Roadmap

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | a thing | shipped | landed |
| 2 | another thing | open | queued |

Status values are exactly `open` or `shipped` -- there is no third value.

**Next up:** row 2.

## Done ledger

Older rows live in `PRODUCT_ARCHIVE.md`.

- iter 03 third thing

## Non-goals

- iter 99 outside the ledger section, so it is not a record
"""

ARCHIVE = """# Roadmap archive

## Done ledger (archive)

- iter 01 did a thing
- iter 02 did another thing
"""

#: A row for 300 placed above 299 INSIDE one file: an ordering violation (behavior 5).
ARCHIVE_DISORDERED = ARCHIVE + "- iter 300 late row\n- iter 299 earlier row\n"


def _pair(tmp_path: pathlib.Path, index: str, archive: str | None) -> pathlib.Path:
    roadmap = tmp_path / "PRODUCT.md"
    roadmap.write_text(index, encoding="utf-8")
    if archive is not None:
        (tmp_path / ri.ARCHIVE_NAME).write_text(archive, encoding="utf-8")
    return roadmap


def _run_main(roadmap: pathlib.Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ri.main([PROG, str(roadmap)])
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# behavior 3: coverage is judged over the union of both ledgers
# ---------------------------------------------------------------------------

def test_b3_a_row_in_either_file_records_the_ship() -> None:
    union = ri.ledger_union(INDEX, ARCHIVE)
    assert ri.unrecorded_ships(union, [1, 2, 3]) == []
    # the index alone does NOT cover 1 and 2: the union is doing the work
    assert ri.unrecorded_ships(INDEX, [1, 2, 3]) == [1, 2]


def test_b3_a_row_duplicated_across_the_seam_is_not_a_single_row() -> None:
    """Acceptance: every ship resolves to EXACTLY ONE row in the union. A row present in
    both files is therefore reported as unrecorded, not silently counted twice."""
    duplicated_index = INDEX.replace("- iter 03 third thing", "- iter 02 dup\n- iter 03 third thing")
    assert duplicated_index != INDEX
    union = ri.ledger_union(duplicated_index, ARCHIVE)
    assert ri.unrecorded_ships(union, [1, 2, 3]) == [2]


def test_b3_main_exits_zero_over_a_split_pair(tmp_path: pathlib.Path) -> None:
    rc, out, err = _run_main(_pair(tmp_path, INDEX, ARCHIVE))
    assert rc == 0, err
    assert err == ""
    assert out.endswith("0 violation(s)\n")


def test_b3_committed_brake_exits_zero_at_head() -> None:
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / PROG),
                           str(REPO_ROOT / "PRODUCT.md")],
                          capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


# ---------------------------------------------------------------------------
# behavior 4: a row in NEITHER file is still reported, on stderr, with exit != 0
# ---------------------------------------------------------------------------

def test_b4_unrecorded_ship_survives_the_union() -> None:
    assert ri.unrecorded_ships(ri.ledger_union(INDEX, ARCHIVE), [1, 2, 3, 4]) == [4]


def test_b4_main_fails_loudly_on_a_missing_row(tmp_path: pathlib.Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable not available")

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True,
                       text=True, check=True)

    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    roadmap = _pair(tmp_path, INDEX, ARCHIVE)
    for subject in ("feat: one (foundry iter 01)", "feat: two (foundry iter 02)",
                    "feat: three (foundry iter 03)", "feat: four (foundry iter 04)"):
        (tmp_path / "f.txt").write_text(subject, encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", subject)
    assert ri.shipped_iterations_from_git(tmp_path).iterations == (1, 2, 3, 4)

    rc, out, err = _run_main(roadmap)
    assert rc != 0
    # The brake reports violations on stdout and exits 1, as it did before the archive
    # existed (behavior 6 pins that); the spec's "Error: on stderr, nothing on stdout"
    # clause describes the exit-2 usage channel, so the FEATURE sentence is asserted here.
    report = [line for line in (out + err).splitlines() if "VIOLATION" in line]
    assert report, out + err
    assert any("04" in line for line in report), out + err


# ---------------------------------------------------------------------------
# behavior 5: ordering is judged per file, never across the seam
# ---------------------------------------------------------------------------

def test_b5_disorder_inside_the_archive_is_a_violation() -> None:
    assert [v.kind for v in ri.ledger_sequence_violations(ARCHIVE_DISORDERED)] == ["not-ascending"]
    assert ri.archive_findings(ARCHIVE_DISORDERED) != []
    assert ri.archive_findings(ARCHIVE) == []


def test_b5_disordered_archive_fails_main(tmp_path: pathlib.Path) -> None:
    rc, out, err = _run_main(_pair(tmp_path, INDEX, ARCHIVE_DISORDERED))
    assert rc != 0
    report = out + err
    assert ri.ARCHIVE_NAME in report and "299" in report and "not-ascending" in report


def test_b5_the_seam_is_not_a_violation() -> None:
    assert ri.ledger_sequence_violations(ARCHIVE) == []
    assert ri.ledger_sequence_violations(INDEX) == []


# ---------------------------------------------------------------------------
# behavior 6: an absent archive is single-file semantics, not an error
# ---------------------------------------------------------------------------

def test_b6_absent_archive_reads_as_none_and_union_is_the_index(tmp_path: pathlib.Path) -> None:
    roadmap = _pair(tmp_path, INDEX, None)
    assert ri.read_archive(roadmap) is None
    assert ri.ledger_union(INDEX, None) == INDEX
    assert ri.archive_findings(None) == []


def test_b6_absent_archive_keeps_the_old_verdicts(tmp_path: pathlib.Path) -> None:
    good = INDEX.replace("- iter 03 third thing", "- iter 01 a\n- iter 02 b\n- iter 03 c")
    rc, _, err = _run_main(_pair(tmp_path, good, None))
    assert (rc, err) == (0, "")
    bad = good.replace("- iter 02 b\n- iter 03 c", "- iter 03 c\n- iter 02 b")
    assert bad != good
    (tmp_path / "bad").mkdir()
    rc, out, err = _run_main(_pair(tmp_path / "bad", bad, None))
    assert rc != 0
    assert "not-ascending" in out + err


# ---------------------------------------------------------------------------
# behavior 7: no product surface moves (the register verbs stay deterministic)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [["list", "--json"], ["taxonomy"], ["validate"], ["report", "."]])
def test_b7_verbs_are_byte_stable_across_two_runs(argv: list[str]) -> None:
    from agent_gap_radar.cli import main as cli_main

    def run() -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                rc = cli_main(argv)
            except SystemExit as stop:
                rc = int(stop.code or 0)
        return rc or 0, out.getvalue()
    first, second = run(), run()
    assert first[0] == 0
    assert first[1] == second[1]
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")


def test_b7_the_register_doc_door_still_exits_zero() -> None:
    """REGISTER.md is untouched by this iteration, so its drift door stays silent."""
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "check_register_doc.py")],
                          capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stderr == ""


# ---------------------------------------------------------------------------
# behavior 8: the public-safety door reports zero findings
# ---------------------------------------------------------------------------

def test_b8_public_safety_door_is_clean() -> None:
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "check_public_safety.py")],
                          capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stderr
    assert "0 finding(s)" in proc.stdout + proc.stderr
