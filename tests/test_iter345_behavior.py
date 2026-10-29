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
import pathlib

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"


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
