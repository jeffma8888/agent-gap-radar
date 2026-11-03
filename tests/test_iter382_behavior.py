"""Iteration 382 behaviors: `scan`/`diff --exit-code` help names every exit code.

Iter 380 made a whole-register `scan --exit-code` refuse (exit 2, empty stdout) on an
above-floor UNKNOWN, but `--help` still promised "exit 1 ..., 0 when it has none; same
document either way" -- a CI author wiring the gate from `--help` had no branch for 2.
These nodes pin the corrected sentences and add a DRIFT BRAKE: each exit code is
OBSERVED from a real run on a tiny tmp target, and the help must say "<code> when"
for every code observed, so the next code a verb learns fails here until it is named.

NORM(x) = " ".join(x.split()), so the sentences hold at any `COLUMNS` (the scan and
diff parsers wrap on whitespace only, never inside "above-floor" or "--gap").
"""

from __future__ import annotations

import os
import pathlib
import shutil
from collections.abc import Iterator

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

SCAN_SENTENCE = (
    "--exit-code confidence floor gated: exit 1 when this target has an above-floor "
    "PRESENT gap, 0 when it has none, 2 when the scan has no verdict to report -- zero "
    "records applied, a --gap record with no automated verdict, or an above-floor "
    "UNKNOWN finding -- with an empty stdout; same document whenever it exits 0 or 1")
DIFF_SENTENCE = (
    "--exit-code exit 1 when the new state lost a record or reopened a gap, 0 when "
    "neither, 2 when the old side is an empty baseline, with an empty stdout; same "
    "document whenever it exits 0 or 1")
STALE_PHRASE = "same document either way"

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a chmod 000 file, so unreadable cannot be staged",
)


def norm(text: str) -> str:
    """Whitespace-normalised text: argparse's wrap width can no longer matter."""
    return " ".join(text.split())


def run(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    """`(exit code, stdout, stderr)` of one in-process CLI call."""
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def help_text(capsys: pytest.CaptureFixture[str], verb: str) -> str:
    """Raw `radar <verb> --help` stdout, asserting argparse's exit 0."""
    with pytest.raises(SystemExit) as exc:
        main([verb, "--help"])
    assert exc.value.code == 0
    return capsys.readouterr().out


@pytest.fixture
def clean_target(tmp_path: pathlib.Path) -> pathlib.Path:
    """One-file target no check finds PRESENT."""
    root = tmp_path / "clean"
    root.mkdir()
    (root / "a.py").write_text("print(1)\n")
    return root


@pytest.fixture
def blocked_target(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    """Target holding a chmod-000 file: checks reach UNKNOWN, not a verdict."""
    root = tmp_path / "blocked"
    root.mkdir()
    (root / "a.py").write_text("print(1)\n")
    blocked = root / "b.py"
    blocked.write_text("x=1\n")
    blocked.chmod(0)
    try:
        yield root
    finally:
        blocked.chmod(0o644)


@pytest.mark.parametrize("columns", ["33", "60", "80", "120"])
@pytest.mark.parametrize(("verb", "sentence"), [("scan", SCAN_SENTENCE),
                                                ("diff", DIFF_SENTENCE)])
def test_b1_b2_b3_help_names_every_code(capsys, monkeypatch, columns, verb, sentence):
    monkeypatch.setenv("COLUMNS", columns)
    raw = help_text(capsys, verb)
    assert raw.endswith("\n") and not raw.endswith("\n\n")
    assert sentence in norm(raw), f"at COLUMNS={columns}"
    assert STALE_PHRASE not in norm(raw)


def test_b4_scan_brake_every_observed_code_is_named(
        capsys, tmp_path, clean_target, blocked_target):
    present = tmp_path / "present"
    shutil.copytree(REPO / "src", present, ignore=shutil.ignore_patterns("__pycache__"))
    empty_gaps = tmp_path / "no-gaps"
    empty_gaps.mkdir()
    observed: dict[str, int] = {}

    observed["present"], _, _ = run(capsys, "scan", present, "--gaps", GAPS, "--exit-code")
    observed["clean"], _, _ = run(capsys, "scan", clean_target, "--gaps", GAPS,
                                  "--exit-code")
    code, out, _ = run(capsys, "scan", clean_target, "--gaps", empty_gaps, "--exit-code")
    assert out == ""
    observed["zero-records"] = code
    if os.access(blocked_target / "b.py", os.R_OK):
        pytest.skip("chmod 000 is ineffective here")
    code, out, _ = run(capsys, "scan", blocked_target, "--gaps", GAPS, "--exit-code")
    assert out == ""
    observed["unknown"] = code

    assert observed == {"present": 1, "clean": 0, "zero-records": 2, "unknown": 2}
    text = norm(help_text(capsys, "scan"))
    for code in set(observed.values()):
        assert f"{code} when" in text, (code, observed)


def test_b5_diff_brake_every_observed_code_is_named(capsys, tmp_path):
    dropped = tmp_path / "dropped"
    shutil.copytree(GAPS, dropped)
    victim = sorted(dropped.glob("GAP-*.json"))[0]
    victim.unlink()
    empty = tmp_path / "empty"
    empty.mkdir()
    observed: dict[str, int] = {}

    observed["same"], _, _ = run(capsys, "diff", GAPS, GAPS, "--exit-code")
    observed["lost"], _, _ = run(capsys, "diff", GAPS, dropped, "--exit-code")
    code, out, _ = run(capsys, "diff", empty, GAPS, "--exit-code")
    assert out == ""
    observed["empty-old"] = code

    assert observed == {"same": 0, "lost": 1, "empty-old": 2}
    text = norm(help_text(capsys, "diff"))
    for code in set(observed.values()):
        assert f"{code} when" in text, (code, observed)


def test_b7_readme_quickstart_names_the_refusal():
    prefix = "uv run radar scan ../my-service --gaps gaps --exit-code  # "
    lines = [line for line in (REPO / "README.md").read_text().splitlines()
             if line.startswith(prefix)]
    assert len(lines) == 1
    assert "2 with an empty stdout if it has no verdict" in lines[0]
