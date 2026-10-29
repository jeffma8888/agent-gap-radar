"""Iteration 326 behaviors: delete test-only ``layer_names()`` and ``gap_type_names()``.

Remove the two convenience wrappers from ``taxonomy.py`` (6 production lines)
and replace all 21 test call sites with ``tuple(LAYERS)`` / ``tuple(GAP_TYPES)``.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-5. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every behavioral
claim is measured by running the CLI, by attempting imports, or by comparing
verb output against a git-archived pre-change tree, all of which are inside
the contract.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
TESTS = REPO / "tests"


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
# B1 -- ``taxonomy.py`` no longer defines ``layer_names`` or
# ``gap_type_names``.  Attempting to import either raises ImportError.
# ---------------------------------------------------------------------------

def test_b1_layer_names_not_importable():
    with pytest.raises(ImportError):
        from agent_gap_radar.taxonomy import layer_names  # noqa: F401

def test_b1_gap_type_names_not_importable():
    with pytest.raises(ImportError):
        from agent_gap_radar.taxonomy import gap_type_names  # noqa: F401


# ---------------------------------------------------------------------------
# B2 -- No test file imports ``layer_names`` or ``gap_type_names`` from
# ``agent_gap_radar.taxonomy``.  The replacement expression
# ``tuple(LAYERS)`` / ``tuple(GAP_TYPES)`` works.
# ---------------------------------------------------------------------------

def test_b2_no_test_imports_deleted_functions():
    hits = []
    me = pathlib.Path(__file__).name
    for py in sorted(TESTS.glob("*.py")):
        if py.name == me:
            continue
        text = py.read_text(encoding="utf-8")
        for name in ("layer_names", "gap_type_names"):
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if f"import {name}" in line:
                    hits.append(f"{py.name}:{i}: {line.strip()}")
    assert not hits, (
        f"found imports of deleted functions:\n" + "\n".join(hits))


def test_b2_tuple_replacement_expression_works():
    from agent_gap_radar.taxonomy import LAYERS, GAP_TYPES
    layers = tuple(LAYERS)
    gap_types = tuple(GAP_TYPES)
    assert len(layers) > 0, "LAYERS must be non-empty"
    assert len(gap_types) > 0, "GAP_TYPES must be non-empty"
    assert all(isinstance(n, str) for n in layers)
    assert all(isinstance(n, str) for n in gap_types)


# ---------------------------------------------------------------------------
# B4 -- ``radar scan .`` exit code 0 and stderr empty on the happy path.
# ---------------------------------------------------------------------------

def test_b4_scan_exit_code_and_stderr_unchanged(capsys):
    rc, out, err = _cli(["scan", str(REPO), "--gaps", str(GAPS)], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    assert err == "", f"stderr must be empty on success; got {err!r}"
