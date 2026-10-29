"""Iteration 324 behaviors: error-path leak fix in ``radar scan``.

When ``radar scan`` is given a non-directory or non-existent target, the error
message now echoes the user's typed argument instead of the resolved absolute
path. This prevents leaking machine-specific paths (home directory, account
name) to stderr where they can be pasted into issues or logs.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-5. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every behavioral
claim is measured by running the CLI or by comparing verb output against a
git-archived pre-change tree, both of which are inside the contract.
"""

from __future__ import annotations

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
# B1 -- relative nonexistent path echoes the as-typed spelling, not an
# absolute path.  Exit code is 2.
# ---------------------------------------------------------------------------

def test_b1_relative_nonexistent_echoes_typed_spelling(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "not_a_dir"
    victim.write_text("x\n", encoding="utf-8")
    rc, out, err = _cli(["scan", "not_a_dir", "--gaps", str(GAPS)], capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    lines = err.splitlines()
    assert len(lines) == 1, f"exactly one stderr line; got {lines}"
    assert lines[0].startswith("Error: "), f"stderr prefixed; got {lines[0]!r}"
    assert "not_a_dir" in lines[0], (
        f"error must contain the typed argument; got {lines[0]!r}")
    resolved = str(victim.resolve())
    assert resolved not in lines[0], (
        f"error must NOT contain the resolved absolute path {resolved!r}; got {lines[0]!r}")


# ---------------------------------------------------------------------------
# B2 -- absolute nonexistent path echoes verbatim.  The user chose an
# absolute path, so the error message shows exactly what they typed.
# ---------------------------------------------------------------------------

def test_b2_absolute_nonexistent_echoes_verbatim(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    abs_target = str(tmp_path / "absolutely_nowhere")
    rc, out, err = _cli(["scan", abs_target, "--gaps", str(GAPS)], capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    lines = err.splitlines()
    assert len(lines) == 1, f"exactly one stderr line; got {lines}"
    assert lines[0].startswith("Error: "), f"stderr prefixed; got {lines[0]!r}"
    assert abs_target in lines[0], (
        f"error must echo the user's absolute path verbatim; got {lines[0]!r}")
