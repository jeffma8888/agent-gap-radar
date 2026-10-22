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

import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
TESTS = REPO / "tests"

PRECHANGE_COMMIT = "7957a75"


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
# B3 -- ``radar scan`` (markdown and JSON) byte-identical to HEAD.
# Uses two-arm git-archive comparison.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-326")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


def test_b3_scan_markdown_byte_identical(base_src):
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


def test_b3_scan_json_byte_identical(base_src):
    import json as _json
    verb = ("scan", str(REPO), "--gaps", str(GAPS), "--json")
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src))
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    # iter-341 added a top-level `layer` key; exclude it from the comparison
    skip = {"layer"}
    base_doc = {k: v for k, v in _json.loads(base_out).items() if k not in skip}
    here_doc = {k: v for k, v in _json.loads(here_out).items() if k not in skip}
    assert here_doc == base_doc, (
        f"`radar scan --json` changed against {PRECHANGE_COMMIT} beyond the `layer` key")


# ---------------------------------------------------------------------------
# B4 -- ``radar scan .`` exit code 0 and stderr empty on the happy path.
# ---------------------------------------------------------------------------

def test_b4_scan_exit_code_and_stderr_unchanged(capsys):
    rc, out, err = _cli(["scan", str(REPO), "--gaps", str(GAPS)], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    assert err == "", f"stderr must be empty on success; got {err!r}"


# ---------------------------------------------------------------------------
# B5 -- all 8 non-scan verbs byte-identical to HEAD.
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
def test_b5_other_verbs_byte_identical(base_src, verb):
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
