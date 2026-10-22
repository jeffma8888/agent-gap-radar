"""Iteration 344 behaviors: ``radar show <ID> [<repo>] --json``.

Emit the full gap brief as a stable JSON object via ``json_document()``,
closing the last ``--json`` parity gap in the verb surface.

THE ISOLATION CONTRACT IS HONORED.  Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7.  No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff.  Every
behavioral claim is measured by running the CLI, or by comparing verb
output against a git-archived pre-change tree, both of which are inside
the contract.
"""

from __future__ import annotations

import json as _json
import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

PRECHANGE_COMMIT = "094b8c4"

EXPECTED_TOP_KEYS = [
    "gap_id", "title", "layer", "gap_type", "status",
    "priority", "confidence", "below_floor", "strongest_source",
    "problem", "symptom", "why_now", "existing", "build_hypothesis",
    "tags", "evidence",
]

EXPECTED_EVIDENCE_KEYS = [
    "source_class", "title", "locator", "date", "quote", "confidence_without",
]


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


# ---------------------------------------------------------------------------
# B1 -- ``radar show GAP-001 --json`` exits 0, valid JSON, 16 top-level
# keys in contract order, evidence array with 6 required keys in order,
# exactly one trailing newline.  (EB1, EB2, EB3)
# ---------------------------------------------------------------------------

def test_b1_show_json_valid_structure(capsys):
    rc, out, err = _cli(["show", "GAP-001", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    assert out.endswith("\n"), "document must end in a newline"
    assert not out.endswith("\n\n"), "document must end in exactly one newline"

    doc = _json.loads(out)
    assert list(doc.keys()) == EXPECTED_TOP_KEYS, (
        f"top-level key order mismatch: {list(doc.keys())}")

    assert isinstance(doc["gap_id"], str)
    assert doc["gap_id"] == "GAP-001"
    assert isinstance(doc["below_floor"], bool)
    assert isinstance(doc["confidence"], int)
    assert isinstance(doc["priority"], (int, float))
    assert isinstance(doc["tags"], list)
    assert isinstance(doc["existing"], list)

    evidence = doc["evidence"]
    assert isinstance(evidence, list)
    assert len(evidence) >= 1, "must have at least one evidence item"
    for item in evidence:
        assert list(item.keys()) == EXPECTED_EVIDENCE_KEYS, (
            f"evidence key order mismatch: {list(item.keys())}")
        assert isinstance(item["source_class"], str)
        assert isinstance(item["confidence_without"], int)


# ---------------------------------------------------------------------------
# B2 -- ``radar show GAP-001`` (flagless) byte-identical to HEAD 094b8c4.
# Two-arm git-archive comparison.  (EB4)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_src(tmp_path_factory):
    root = tmp_path_factory.mktemp("base-arm-344")
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


def test_b2_flagless_show_byte_identical(base_src):
    verb = ("show", "GAP-001", str(GAPS))
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
            f"`radar show GAP-001` markdown changed against {PRECHANGE_COMMIT}; "
            f"first diffs: {snippet}")


# ---------------------------------------------------------------------------
# B3 -- ``radar show NONEXISTENT --json`` exits 2 with ``Error:`` prefix on
# stderr, empty stdout.  (EB6)
# ---------------------------------------------------------------------------

def test_b3_nonexistent_gap_exits_2(capsys):
    rc, out, err = _cli(
        ["show", "NONEXISTENT", str(GAPS), "--json"], capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    err_lines = [l for l in err.splitlines() if l.strip()]
    assert len(err_lines) >= 1, "must have at least one stderr line"
    assert err_lines[-1].startswith("Error: "), (
        f"last stderr line must start 'Error: '; got {err_lines[-1]!r}")


# ---------------------------------------------------------------------------
# B4 -- canonicalization: ``GAP-9`` resolves to ``GAP-009`` in JSON output.
# (EB7 wiring, implicit via existing id resolution)
# ---------------------------------------------------------------------------

def test_b4_canonicalization(capsys):
    rc, out, err = _cli(["show", "GAP-9", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    doc = _json.loads(out)
    assert doc["gap_id"] == "GAP-009", (
        f"GAP-9 must canonicalize to GAP-009; got {doc['gap_id']!r}")


# ---------------------------------------------------------------------------
# B5 -- determinism: two consecutive ``show --json`` runs produce
# byte-identical output.  (EB5)
# ---------------------------------------------------------------------------

def test_b5_determinism(capsys):
    argv = ["show", "GAP-001", str(GAPS), "--json"]
    rc1, out1, _ = _cli(argv, capsys)
    rc2, out2, _ = _cli(argv, capsys)
    assert rc1 == rc2 == 0
    assert out1 == out2, "two identical show --json runs must be byte-identical"


# ---------------------------------------------------------------------------
# B7 -- non-show verbs byte-identical to HEAD (regression guard).
# Parametrized two-arm byte comparison over 7 verbs.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", [
    ("report", str(GAPS)),
    ("list", str(GAPS)),
    ("list", str(GAPS), "--json"),
    ("taxonomy",),
    ("taxonomy", "--json"),
    ("prd", str(GAPS)),
    ("validate", str(GAPS)),
])
def test_b7_non_show_verbs_byte_identical(base_src, verb):
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
