"""Iteration 308 behaviors: gap-id canonicalization.

`show`, `prd --gap`, and `scan --gap` accept shorthand gap ids (`GAP-9`,
`gap-009`, `9`) and resolve them to the canonical `GAP-NNN` form before lookup.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors 1-9. No test here reads the implementation source,
the engineer's or the reviewer's notes, or any diff. Every behavioral claim is
measured by RUNNING the CLI in a real child process.
"""

from __future__ import annotations

import subprocess
import sys
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _radar(*argv: str) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        capture_output=True, cwd=str(REPO_ROOT), timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


# -- fixtures for the canonical form (used in comparisons) ---------------------

@pytest.fixture(scope="module")
def show_canonical() -> tuple[int, bytes, bytes]:
    return _radar("show", "GAP-009", ".")


@pytest.fixture(scope="module")
def prd_canonical() -> tuple[int, bytes, bytes]:
    return _radar("prd", "--gap", "GAP-009", ".")


@pytest.fixture(scope="module")
def scan_canonical() -> tuple[int, bytes, bytes]:
    return _radar("scan", "--gap", "GAP-009", ".", "--gaps", "gaps")


# -- B1: show GAP-9 . == show GAP-009 . ---------------------------------------

def test_b1_show_gap_9_matches_canonical(show_canonical):
    canon_rc, canon_out, _ = show_canonical
    assert canon_rc == 0
    rc, out, err = _radar("show", "GAP-9", ".")
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B2: show gap-009 . == show GAP-009 . -------------------------------------

def test_b2_show_lowercase_gap_009_matches_canonical(show_canonical):
    canon_rc, canon_out, _ = show_canonical
    assert canon_rc == 0
    rc, out, err = _radar("show", "gap-009", ".")
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B3: show 9 . == show GAP-009 . -------------------------------------------

def test_b3_show_bare_9_matches_canonical(show_canonical):
    canon_rc, canon_out, _ = show_canonical
    assert canon_rc == 0
    rc, out, err = _radar("show", "9", ".")
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B4: prd --gap gap-9 . == prd --gap GAP-009 . -----------------------------

def test_b4_prd_lowercase_gap_9_matches_canonical(prd_canonical):
    canon_rc, canon_out, _ = prd_canonical
    assert canon_rc == 0
    rc, out, err = _radar("prd", "--gap", "gap-9", ".")
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B5: prd --gap 9 . == prd --gap GAP-009 . ---------------------------------

def test_b5_prd_bare_9_matches_canonical(prd_canonical):
    canon_rc, canon_out, _ = prd_canonical
    assert canon_rc == 0
    rc, out, err = _radar("prd", "--gap", "9", ".")
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B6: scan --gap 9 . == scan --gap GAP-009 . -------------------------------

def test_b6_scan_bare_9_matches_canonical(scan_canonical):
    canon_rc, canon_out, _ = scan_canonical
    rc, out, err = _radar("scan", "--gap", "9", ".", "--gaps", "gaps")
    assert rc == canon_rc, f"exit {rc} vs canonical {canon_rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B7: scan --gap gap-009 . == scan --gap GAP-009 . -------------------------

def test_b7_scan_lowercase_gap_009_matches_canonical(scan_canonical):
    canon_rc, canon_out, _ = scan_canonical
    rc, out, err = _radar("scan", "--gap", "gap-009", ".", "--gaps", "gaps")
    assert rc == canon_rc, f"exit {rc} vs canonical {canon_rc}; stderr {err[:300]!r}"
    assert out == canon_out


# -- B8: invalid ids still refuse with exit 2 ---------------------------------

@pytest.mark.parametrize("verb_argv,gap_id", [
    (["show", "{gap}", "."], "abc"),
    (["show", "{gap}", "."], "GAP-"),
    (["show", "{gap}", "."], "GAP-9999"),
    (["show", "{gap}", "."], "-1"),
])
def test_b8_invalid_ids_refuse_with_exit_2(verb_argv, gap_id):
    argv = [a.replace("{gap}", gap_id) for a in verb_argv]
    rc, out, err = _radar(*argv)
    assert rc == 2, f"expected exit 2 for {gap_id!r}, got {rc}; stderr {err[:300]!r}"
    assert out == b"", f"stdout must be empty for invalid id, got {len(out)} B"
    assert b"Error: " in err, f"stderr must contain 'Error: ', got {err[:300]!r}"


# -- B9: canonical form still works identically --------------------------------

def test_b9_canonical_form_still_works(show_canonical):
    rc, out, err = show_canonical
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert out, "canonical show must produce output"
    assert err == b"", f"stderr must be empty, got {err[:300]!r}"
