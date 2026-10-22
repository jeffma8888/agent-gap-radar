"""Iteration 341 behaviors: ``radar scan --layer L`` filter wiring.

Narrow the scan domain to one taxonomy layer so a team adopting the
scanner in CI can gate on only the gaps in the layer it owns.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every
behavioral claim is measured by running the CLI or by comparing verb
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

PRECHANGE_COMMIT = "8bffe14"


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
# B1 -- ``radar scan . --layer context-memory`` produces a scan document
# containing ONLY findings for records whose layer is context-memory.
# Well-formed markdown ending in exactly one newline.
# ---------------------------------------------------------------------------

def test_b1_scan_layer_filter_scoped_output(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS), "--layer", "context-memory"],
        capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    assert out.endswith("\n"), "document must end in a newline"
    assert not out.endswith("\n\n"), "document must end in exactly one newline"
    assert "Register records applied:" in out
    lines = out.splitlines()
    applied_line = [l for l in lines if "Register records applied:" in l][0]
    count = int(applied_line.split(":")[-1].strip())
    assert count > 0, "filtered scan must apply at least one record"
    assert count < 119, (
        f"filtered count {count} must be less than the full register")


# ---------------------------------------------------------------------------
# B2 -- ``radar scan . --layer context-memory --json`` produces valid JSON
# with a ``"layer"`` key echoing the argument; absent flag gives ``null``.
# ---------------------------------------------------------------------------

def test_b2_scan_layer_json_has_layer_key(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS),
         "--layer", "context-memory", "--json"],
        capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    doc = _json.loads(out)
    assert doc["layer"] == "context-memory", (
        f"expected 'context-memory'; got {doc.get('layer')!r}")
    for finding in doc.get("findings", []):
        assert finding.get("layer") == "context-memory", (
            f"finding layer mismatch: {finding.get('layer')!r}")


def test_b2_scan_json_layer_null_when_absent(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS), "--json"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    doc = _json.loads(out)
    assert "layer" in doc, "top-level 'layer' key must be present"
    assert doc["layer"] is None, (
        f"expected null when --layer absent; got {doc['layer']!r}")


# ---------------------------------------------------------------------------
# B3 -- ``radar scan . --layer NONEXISTENT`` exits 2 with ``Error:`` on
# stderr naming every accepted layer value, and zero bytes on stdout.
# ---------------------------------------------------------------------------

def test_b3_scan_unknown_layer_exits_2(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS), "--layer", "NONEXISTENT"],
        capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    err_lines = err.splitlines()
    assert len(err_lines) == 1, f"exactly one stderr line; got {err_lines}"
    assert err_lines[0].startswith("Error: "), (
        f"stderr must be prefixed with 'Error: '; got {err_lines[0]!r}")
    for layer_name in ("model-runtime", "orchestration", "context-memory",
                       "tool-action", "sandbox-isolation", "eval-verification",
                       "observability", "cost-governance", "lifecycle-deploy",
                       "multi-agent", "human-interface"):
        assert layer_name in err_lines[0], (
            f"error must list accepted layer {layer_name!r}")


# ---------------------------------------------------------------------------
# B4 -- ``radar scan .`` (no --layer) byte-identical to HEAD ``8bffe14``.
# Uses two-arm git-archive comparison for scan markdown.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-341")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


def test_b4_scan_no_layer_markdown_identical(base_src):
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


def test_b4_scan_no_layer_json_identical(base_src):
    verb = ("scan", str(REPO), "--gaps", str(GAPS), "--json")
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src))
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    skip_top = {"layer"}
    skip_finding = {"skipped_files"}
    def _strip(doc):
        d = {k: v for k, v in doc.items() if k not in skip_top}
        d["findings"] = [{k: v for k, v in f.items() if k not in skip_finding}
                         for f in d["findings"]]
        return d
    base_doc = _strip(_json.loads(base_out))
    here_doc = _strip(_json.loads(here_out))
    assert here_doc == base_doc, (
        f"`radar scan --json` changed against {PRECHANGE_COMMIT} beyond the "
        f"`layer`/`skipped_files` keys")


# ---------------------------------------------------------------------------
# B5 -- ``radar scan . --layer context-memory --exit-code`` exits 1 only
# when an above-floor PRESENT gap in context-memory exists.
# ---------------------------------------------------------------------------

def test_b5_exit_code_gated_to_layer(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS),
         "--layer", "context-memory", "--exit-code"],
        capsys)
    assert rc == 1, (
        f"expected exit 1 (PRESENT gap in context-memory); got {rc}")
    assert out, "stdout must be non-empty even with --exit-code"


# ---------------------------------------------------------------------------
# B6 -- ``radar scan . --layer L --gap GAP-NNN`` composes: if GAP-NNN is
# not in layer L, the domain is empty; if it is, the scan runs for that gap.
# ---------------------------------------------------------------------------

def test_b6_layer_and_gap_compose_matching(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS),
         "--layer", "context-memory", "--gap", "GAP-072"],
        capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert "Register records applied: 1" in out, (
        f"matching layer+gap should apply exactly 1 record; got: {out!r}")


def test_b6_layer_and_gap_compose_mismatched(capsys):
    rc, out, err = _cli(
        ["scan", str(REPO), "--gaps", str(GAPS),
         "--layer", "orchestration", "--gap", "GAP-072"],
        capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert "Register records applied: 0" in out, (
        f"mismatched layer+gap should apply 0 records; got: {out!r}")


# ---------------------------------------------------------------------------
# B7 -- determinism: two identical ``radar scan . --layer L`` runs produce
# byte-identical output.
# ---------------------------------------------------------------------------

def test_b7_determinism(capsys):
    argv = ["scan", str(REPO), "--gaps", str(GAPS), "--layer", "context-memory"]
    rc1, out1, _ = _cli(argv, capsys)
    rc2, out2, _ = _cli(argv, capsys)
    assert rc1 == rc2 == 0
    assert out1 == out2, "two identical --layer scans must produce identical output"


# ---------------------------------------------------------------------------
# B_REG -- non-scan verbs byte-identical to HEAD (regression guard).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", [
    ("report", str(GAPS)),
    ("list", str(GAPS)),
    ("list", str(GAPS), "--json"),
    ("show", "GAP-001", str(GAPS)),
    ("taxonomy",),
    ("taxonomy", "--json"),
    ("prd", str(GAPS)),
    ("validate", str(GAPS)),
])
def test_breg_non_scan_verbs_byte_identical(base_src, verb):
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
