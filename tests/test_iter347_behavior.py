"""Iteration 347 behaviors: README drift guard.

Replace the stale hard-coded "ten records spanning [six layers]" on
README.md line 125 with a derivation sentence pointing to ``radar list .``,
and guard against reintroduction.

ISOLATION CONTRACT HONORED: nothing here reads ``src/``, the engineer's or
reviewer's notes, or any diff.  Expectations come from ``pm.md``'s Expected
Behaviors 1-6.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
README = REPO / "README.md"

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

_NUM_GROUP = r"(?:(\d+)|(" + "|".join(_WORD_NUMBERS) + r"))"

_HARD_RECORD_RE = re.compile(_NUM_GROUP + r"\s+records", re.IGNORECASE)
_HARD_LAYER_RE = re.compile(_NUM_GROUP + r"\s+layers", re.IGNORECASE)


def _actual_gap_count() -> int:
    return len([f for f in os.listdir(GAPS) if f.endswith(".json")])


# -------------------------------------------------------------------
# B1 -- README.md line 125 carries no hard-coded record count.  (EB1)
# If a match is found, it must agree with the register.
# -------------------------------------------------------------------

def _current_register_section(text: str) -> str:
    """Extract the ``## Current register`` section from the README."""
    start = text.find("## Current register")
    assert start != -1, "README.md must have a '## Current register' section"
    rest = text[start:]
    next_heading = re.search(r"\n## ", rest[1:])
    if next_heading:
        return rest[: next_heading.start() + 1]
    return rest


def _parse_count(digit_str: str, word_str: str) -> int:
    if digit_str:
        return int(digit_str)
    return _WORD_NUMBERS[word_str.lower()]


def test_b1_no_stale_hard_coded_record_count():
    text = README.read_text(encoding="utf-8")
    section = _current_register_section(text)
    actual = _actual_gap_count()
    for digit_str, word_str in _HARD_RECORD_RE.findall(section):
        claimed = _parse_count(digit_str, word_str)
        assert claimed == actual, (
            f"README.md '## Current register' contains a hard-coded "
            f"record count ({claimed}) that disagrees with the {actual} "
            f"JSON files in gaps/")
    for digit_str, word_str in _HARD_LAYER_RE.findall(section):
        claimed = _parse_count(digit_str, word_str)
        layers = len({
            json.load(open(GAPS / f))["layer"]
            for f in os.listdir(GAPS) if f.endswith(".json")
        })
        assert claimed == layers, (
            f"README.md '## Current register' contains a hard-coded "
            f"layer count ({claimed}) that disagrees with the {layers} "
            f"layers in gaps/")


# -------------------------------------------------------------------
# B2 -- GAP-010 below-floor worked-example mention preserved.  (EB2)
# -------------------------------------------------------------------

def test_b2_gap010_worked_example_preserved():
    text = README.read_text(encoding="utf-8")
    assert "GAP-010" in text, (
        "README.md must mention GAP-010 as a below-floor worked example")
    assert "confidence floor" in text.lower() or "confidence floor" in text, (
        "README.md must mention the confidence floor near GAP-010")


# -------------------------------------------------------------------
# B3 -- the derivation sentence points to ``radar list .``.  (EB1)
# -------------------------------------------------------------------

def test_b3_derivation_sentence_present():
    text = README.read_text(encoding="utf-8")
    assert "radar list" in text, (
        "README.md must point readers to `radar list .` for the current count")


# -------------------------------------------------------------------
# B4 -- zero src/ files changed (EB6 regression).
# Verbs produce byte-identical output against HEAD.
# -------------------------------------------------------------------

_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)

PRECHANGE_COMMIT = "e7b827a"


def _git(*args):
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: "
        f"{done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


def _arm(src, *argv):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run(
        [sys.executable, "-c", _ARM_SCRIPT, *argv],
        capture_output=True, cwd=str(REPO), env=env, timeout=120)
    return proc.returncode, proc.stdout


@pytest.fixture(scope="module")
def base_src(tmp_path_factory):
    root = tmp_path_factory.mktemp("base-arm-347")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), (
        sorted(p.name for p in root.iterdir()))
    return src


@pytest.mark.parametrize("verb", [
    ("report", str(GAPS)),
    ("list", str(GAPS)),
    ("list", str(GAPS), "--json"),
    ("show", "GAP-001", str(GAPS)),
    ("show", "GAP-001", str(GAPS), "--json"),
    ("taxonomy",),
    ("taxonomy", "--json"),
    ("prd", str(GAPS)),
    ("validate", str(GAPS)),
    ("diff", str(GAPS), str(GAPS)),
])
def test_b4_all_verbs_byte_identical(base_src, verb):
    base_rc, base_out = _arm(base_src, *verb)
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    here_rc, here_out = _arm(None, *verb)
    assert here_rc == 0
    if here_out != base_out:
        base_lines = base_out.decode("utf-8", "replace").splitlines()
        here_lines = here_out.decode("utf-8", "replace").splitlines()
        diffs = [(i, b, h) for i, (b, h)
                 in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = (diffs[:5] if diffs
                   else f"len {len(base_out)} vs {len(here_out)}")
        assert here_out == base_out, (
            f"`radar {' '.join(verb)}` changed against {PRECHANGE_COMMIT}; "
            f"first diffs: {snippet}")


# -------------------------------------------------------------------
# B5 -- scan markdown byte-identical (zero src/ changes).  (EB6)
# -------------------------------------------------------------------

def test_b5_scan_markdown_byte_identical(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS))
    base_rc, base_out = _arm(base_src, *verb)
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    here_rc, here_out = _arm(None, *verb)
    assert here_rc == 0
    assert here_out == base_out, (
        "`radar scan .` output changed despite zero src/ changes")


# -------------------------------------------------------------------
# B6 -- scan JSON byte-identical (zero src/ changes).  (EB6)
# -------------------------------------------------------------------

def test_b6_scan_json_byte_identical(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS), "--json")
    base_rc, base_out = _arm(base_src, *verb)
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    here_rc, here_out = _arm(None, *verb)
    assert here_rc == 0
    assert here_out == base_out, (
        "`radar scan . --json` output changed despite zero src/ changes")
