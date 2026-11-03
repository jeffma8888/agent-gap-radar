"""Iteration 382 tester behaviors: `scan/diff --exit-code` help names every exit code.

Black-box only: every assertion drives the public CLI (`main` in-process for the
gate runs, a fresh `python -m agent_gap_radar.cli` subprocess for `--help` so the
COLUMNS environment variable really reaches argparse's wrapper).

The brake here is broader than the spec's minimum: it also drives the `--gap <id>`
"no automated verdict" refusal and a diff that REOPENS a gap, both of which the new
help text names, and it checks the help's own claim "same document whenever it
exits 0 or 1" against the bytes the flag-less run prints.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
from collections.abc import Iterator

import pytest
from _selfscan import selfscan, selfscan_run_cache  # noqa: F401  (autouse fixture)

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
README = REPO / "README.md"

SCAN_SENTENCE = (
    "--exit-code confidence floor gated: exit 1 when this target has an above-floor "
    "PRESENT gap, 0 when it has none, 2 when the scan has no verdict to report -- zero "
    "records applied, a --gap record with no automated verdict, or an above-floor "
    "UNKNOWN finding -- with an empty stdout; same document whenever it exits 0 or 1"
)
DIFF_SENTENCE = (
    "--exit-code exit 1 when the new state lost a record or reopened a gap, 0 when "
    "neither, 2 when the old side is an empty baseline, with an empty stdout; same "
    "document whenever it exits 0 or 1"
)
STALE = "same document either way"

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a chmod 000 file, so unreadable cannot be staged",
)


def norm(text: str) -> str:
    return " ".join(text.split())


def run(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def help_text(verb: str, columns: int) -> tuple[int, str, str]:
    env = {**os.environ, "COLUMNS": str(columns)}
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(REPO / "src"), env.get("PYTHONPATH", "")) if p)
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", verb, "--help"],
        capture_output=True, text=True, env=env, cwd=REPO, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


def assert_refusal(code: int, out: str, err: str) -> None:
    assert (code, out) == (2, ""), (code, out[:200], err)
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines and lines[-1].startswith("Error: "), err


# --- Behaviors 1-3: the exact sentences, at every terminal width -----------------------

COLUMNS = (33, 60, 80, 120, 400)


@pytest.mark.parametrize("columns", COLUMNS)
@pytest.mark.parametrize("verb,sentence", [("scan", SCAN_SENTENCE), ("diff", DIFF_SENTENCE)],
                         ids=["scan", "diff"])
def test_b1_b2_b3_help_sentence_survives_every_wrap_width(verb, sentence, columns):
    code, out, err = help_text(verb, columns)
    assert (code, err) == (0, "")
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-3:])
    assert sentence in norm(out), norm(out)
    assert STALE not in norm(out)
    # The sentence appears once: the paragraph was rewritten, not appended to.
    assert norm(out).count(sentence) == 1


def test_b1_confidence_floor_gated_still_leads_the_scan_flag(capsys):
    _, out, _ = help_text("scan", 80)
    flat = norm(out)
    start = flat.index("--exit-code confidence floor gated:")
    assert flat[start:].startswith(SCAN_SENTENCE)


# --- Behavior 4: scan brake, every code driven by a real run ---------------------------

@pytest.fixture(scope="module")
def scan_targets(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, pathlib.Path]]:
    root = tmp_path_factory.mktemp("iter382t")
    present = root / "present"
    shutil.copytree(REPO / "src", present, ignore=shutil.ignore_patterns("__pycache__"))
    clean = root / "clean"
    clean.mkdir()
    (clean / "a.py").write_text("print(1)\n")
    empty_gaps = root / "empty-gaps"
    empty_gaps.mkdir()
    blocked_dir = root / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "a.py").write_text("import os\n")
    blocked = blocked_dir / "b.py"
    blocked.write_text("x=1\n")
    blocked.chmod(0)
    try:
        yield {"present": present, "clean": clean, "empty_gaps": empty_gaps,
               "blocked": blocked_dir}
    finally:
        blocked.chmod(0o644)


def _manual_gap_id(capsys, clean: pathlib.Path) -> str:
    """A record whose check on a clean target reaches no automated verdict (MANUAL)."""
    code, doc, _ = run(capsys, "scan", clean, "--gaps", GAPS, "--json")
    assert code == 0
    manual = sorted(f["gap_id"] for f in json.loads(doc)["findings"]
                    if f["verdict"] == "MANUAL")
    assert manual, "the register must hold at least one record with a MANUAL check"
    return manual[0]


def _scan_conditions(capsys, t) -> dict[str, list[object]]:
    return {
        "present": ["scan", t["present"], "--gaps", GAPS, "--exit-code"],
        "clean": ["scan", t["clean"], "--gaps", GAPS, "--exit-code"],
        "zero_records": ["scan", t["clean"], "--gaps", t["empty_gaps"], "--exit-code"],
        "no_automated_verdict": ["scan", t["clean"], "--gaps", GAPS,
                                 "--gap", _manual_gap_id(capsys, t["clean"]), "--exit-code"],
    }


EXPECTED_SCAN = {"present": 1, "clean": 0, "zero_records": 2, "no_automated_verdict": 2}


@pytest.mark.parametrize("name", sorted(EXPECTED_SCAN))
def test_b4_each_scan_condition_exits_as_the_help_says(capsys, scan_targets, name):
    argv = _scan_conditions(capsys, scan_targets)[name]
    code, out, err = run(capsys, *argv)
    assert code == EXPECTED_SCAN[name], (name, code, err)
    if code == 2:
        assert_refusal(code, out, err)
    else:
        # "same document whenever it exits 0 or 1": the flag never alters the bytes.
        plain_code, plain_out, _ = run(capsys, *[a for a in argv if a != "--exit-code"])
        assert plain_code == 0
        assert out == plain_out
        assert out.endswith("\n") and not out.endswith("\n\n")
        assert err == ""


@needs_non_root
def test_b4_unreadable_file_refuses_with_empty_stdout(capsys, scan_targets):
    code, out, err = run(capsys, "scan", scan_targets["blocked"], "--gaps", GAPS, "--exit-code")
    assert_refusal(code, out, err)


def test_b4_brake_every_observed_scan_code_is_named_in_help(capsys, scan_targets):
    observed = {run(capsys, *argv)[0] for argv in _scan_conditions(capsys, scan_targets).values()}
    assert observed == {0, 1, 2}, observed
    flat = norm(help_text("scan", 80)[1])
    for c in sorted(observed):
        assert f"{c} when" in flat, (c, flat)


# --- Behavior 5: diff brake ------------------------------------------------------------

@pytest.fixture(scope="module")
def diff_beds(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pathlib.Path]:
    root = tmp_path_factory.mktemp("iter382d")
    files = sorted(GAPS.glob("GAP-*.json"))
    assert len(files) >= 2
    dropped = root / "dropped"
    shutil.copytree(GAPS, dropped)
    (dropped / files[-1].name).unlink()
    addressed = root / "addressed"
    shutil.copytree(GAPS, addressed)
    victim = next(p for p in files if json.loads(p.read_text())["status"] == "open")
    record = json.loads(victim.read_text())
    record["status"] = "addressed"
    (addressed / victim.name).write_text(json.dumps(record, indent=2) + "\n")
    empty = root / "empty"
    empty.mkdir()
    return {"dropped": dropped, "addressed": addressed, "empty": empty}


def _diff_conditions(b) -> dict[str, tuple[list[object], int]]:
    return {
        "same": (["diff", GAPS, GAPS, "--exit-code"], 0),
        "lost_record": (["diff", GAPS, b["dropped"], "--exit-code"], 1),
        "reopened": (["diff", b["addressed"], GAPS, "--exit-code"], 1),
        "closed_is_not_regression": (["diff", GAPS, b["addressed"], "--exit-code"], 0),
        "empty_baseline": (["diff", b["empty"], GAPS, "--exit-code"], 2),
    }


@pytest.mark.parametrize("name", ["same", "lost_record", "reopened",
                                  "closed_is_not_regression", "empty_baseline"])
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["markdown", "json"])
def test_b5_each_diff_condition_exits_as_the_help_says(capsys, diff_beds, name, extra):
    argv, expected = _diff_conditions(diff_beds)[name]
    code, out, err = run(capsys, *argv, *extra)
    assert code == expected, (name, code, err)
    if code == 2:
        assert_refusal(code, out, err)
    else:
        plain_code, plain_out, _ = run(capsys, *[a for a in argv if a != "--exit-code"], *extra)
        assert plain_code == 0
        assert out == plain_out
        assert out.endswith("\n") and not out.endswith("\n\n")


def test_b5_brake_every_observed_diff_code_is_named_in_help(capsys, diff_beds):
    observed = {run(capsys, *argv)[0] for argv, _ in _diff_conditions(diff_beds).values()}
    assert observed == {0, 1, 2}, observed
    flat = norm(help_text("diff", 80)[1])
    for c in sorted(observed):
        assert f"{c} when" in flat, (c, flat)


# --- Behavior 7: README Quickstart -----------------------------------------------------

def test_b7_readme_scan_exit_code_line_names_the_refusal():
    lines = [line for line in README.read_text().splitlines()
             if line.startswith("uv run radar scan ../my-service --gaps gaps --exit-code ")
             or line.startswith("uv run radar scan ../my-service --gaps gaps --exit-code#")]
    assert len(lines) == 1, lines
    command, _, comment = lines[0].partition("#")
    assert command.strip() == "uv run radar scan ../my-service --gaps gaps --exit-code"
    assert "2 with an empty stdout" in comment, comment
    assert "no verdict" in comment and "UNKNOWN" in comment, comment
    assert "exit 1" in comment, comment


def test_b7_readme_never_repeats_the_stale_phrase():
    assert STALE not in norm(README.read_text())
