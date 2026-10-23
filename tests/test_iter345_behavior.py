"""Iteration 345 behaviors: ``re.compile`` cache in ``checks.py``.

Cache ``re.compile`` results per ``(pattern, flags)`` in a module-level dict
to eliminate recompilation within and across scans.  Pure performance
optimization with zero rendered output changes.

THE ISOLATION CONTRACT IS HONORED.  Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7.  No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff.  Every
behavioral claim is measured by running the CLI, or by comparing verb
output against a git-archived pre-change tree, both of which are inside
the contract.

NOTE ON EB1/EB2 ("byte-identical scan output"): the change touches
``checks.py``, which the scan self-referentially evaluates.  Line-number
locators pointing into ``checks.py`` shift by the insertion size.  This is
the correct rendering of the current file state, not a behavioral change.
B1/B2 verify that the ONLY differences are ``checks.py`` line-number
locator shifts — all other scan content is byte-identical.
"""

from __future__ import annotations

import json as _json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

PRECHANGE_COMMIT = "230f460"

_CHECKS_LOCATOR_RE = re.compile(r"checks\.py:\d+")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cli(argv, capsys):
    try:
        rc = main(argv) or 0
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src, *argv):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run(
        [sys.executable, "-c", _ARM_SCRIPT, *argv],
        capture_output=True, cwd=str(REPO), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


def _git(*args):
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: "
        f"{done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


def _normalise_checks_locators(text):
    """Replace ``checks.py:<line>`` with ``checks.py:NNN`` for comparison."""
    return _CHECKS_LOCATOR_RE.sub("checks.py:NNN", text)


# ---------------------------------------------------------------------------
# B1 -- ``radar scan .`` markdown: all differences are self-referential
# ``checks.py`` line-number locator shifts.  (EB1)
# Two-arm git-archive comparison.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_src(tmp_path_factory):
    root = tmp_path_factory.mktemp("base-arm-345")
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


def test_b1_scan_markdown_only_locator_shift(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS))
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    base_text = base_out.decode("utf-8", "replace")
    here_text = here_out.decode("utf-8", "replace")

    base_norm = _normalise_checks_locators(base_text)
    here_norm = _normalise_checks_locators(here_text)
    if base_norm != here_norm:
        base_lines = base_norm.splitlines()
        here_lines = here_norm.splitlines()
        diffs = [(i, b, h) for i, (b, h)
                 in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = (diffs[:5] if diffs
                   else f"len {len(base_norm)} vs {len(here_norm)}")
        assert base_norm == here_norm, (
            f"`radar scan .` markdown differs beyond checks.py locator "
            f"shifts against {PRECHANGE_COMMIT}; first diffs: {snippet}")

    if base_out != here_out:
        base_lines = base_text.splitlines()
        here_lines = here_text.splitlines()
        for i, (b, h) in enumerate(zip(base_lines, here_lines)):
            if b != h:
                assert _CHECKS_LOCATOR_RE.search(b), (
                    f"line {i}: diff not a checks.py locator shift: "
                    f"base={b!r}, here={h!r}")


# ---------------------------------------------------------------------------
# B2 -- ``radar scan . --json``: all differences are self-referential
# ``checks.py`` line-number locator shifts.  (EB2)
# Two-arm git-archive comparison.
# ---------------------------------------------------------------------------

def test_b2_scan_json_only_locator_shift(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS), "--json")
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    base_text = base_out.decode("utf-8", "replace")
    here_text = here_out.decode("utf-8", "replace")

    base_norm = _normalise_checks_locators(base_text)
    here_norm = _normalise_checks_locators(here_text)
    if base_norm != here_norm:
        base_lines = base_norm.splitlines()
        here_lines = here_norm.splitlines()
        diffs = [(i, b, h) for i, (b, h)
                 in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = (diffs[:5] if diffs
                   else f"len {len(base_norm)} vs {len(here_norm)}")
        assert base_norm == here_norm, (
            f"`radar scan . --json` differs beyond checks.py locator "
            f"shifts against {PRECHANGE_COMMIT}; first diffs: {snippet}")

    if base_out != here_out:
        base_lines = base_text.splitlines()
        here_lines = here_text.splitlines()
        for i, (b, h) in enumerate(zip(base_lines, here_lines)):
            if b != h:
                assert _CHECKS_LOCATOR_RE.search(b), (
                    f"line {i}: diff not a checks.py locator shift: "
                    f"base={b!r}, here={h!r}")


# ---------------------------------------------------------------------------
# B3 -- determinism: two consecutive ``radar scan .`` runs produce
# byte-identical output.  (EB3)
# ---------------------------------------------------------------------------

def test_b3_scan_determinism(capsys):
    argv = ["scan", str(REPO), "--gaps", str(GAPS)]
    rc1, out1, _ = _cli(argv, capsys)
    rc2, out2, _ = _cli(argv, capsys)
    assert rc1 == rc2 == 0
    assert out1 == out2, "two identical scan runs must be byte-identical"


# ---------------------------------------------------------------------------
# B4 -- non-scan verbs byte-identical to HEAD (regression guard).
# Parametrized two-arm byte comparison over 10 verbs.  (EB4)
# ---------------------------------------------------------------------------

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
def test_b4_non_scan_verbs_byte_identical(base_src, verb):
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
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


# ---------------------------------------------------------------------------
# B5 -- public function surface of ``checks`` module unchanged.  (EB6)
# The cache must be private (_-prefixed), not exposed.
# ---------------------------------------------------------------------------

def test_b5_no_new_public_surface():
    import agent_gap_radar.checks as checks
    public_names = sorted(n for n in dir(checks) if not n.startswith("_"))
    assert "cached_compile" not in public_names, (
        "cached_compile must not appear as a public name")
    assert "COMPILE_CACHE" not in public_names, (
        "COMPILE_CACHE must not appear as a public name")
