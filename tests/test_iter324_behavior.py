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

import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

PRECHANGE_COMMIT = "27a8448"


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


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run(
        [sys.executable, "-c", _ARM_SCRIPT, *argv],
        capture_output=True, cwd=str(REPO), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


def _git(*args: str) -> bytes:
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: "
        f"{done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


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


# ---------------------------------------------------------------------------
# B3 -- happy-path `radar scan .` byte-identical to HEAD.
# Uses two-arm git-archive comparison.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-324")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


def test_b3_scan_happy_path_byte_identical(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS))
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
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"`radar scan .` changed against {PRECHANGE_COMMIT}; "
            f"first diffs: {snippet}")


def test_b3_scan_json_happy_path_byte_identical(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS), "--json")
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src))
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    if here_out != base_out:
        base_lines = base_out.decode("utf-8", "replace").splitlines()
        here_lines = here_out.decode("utf-8", "replace").splitlines()
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"`radar scan --json` changed against {PRECHANGE_COMMIT}; "
            f"first diffs: {snippet}")


# ---------------------------------------------------------------------------
# B4 -- all other verbs byte-identical to HEAD.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", [
    ("report", str(GAPS)),
    ("list", str(GAPS)),
    ("list", str(GAPS), "--json"),
    ("show", "GAP-001", str(GAPS)),
    ("taxonomy",),
    ("prd", str(GAPS)),
    ("validate", str(GAPS)),
])
def test_b4_other_verbs_byte_identical(base_src, verb):
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
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"`radar {' '.join(verb)}` changed against {PRECHANGE_COMMIT}; "
            f"first diffs: {snippet}")
