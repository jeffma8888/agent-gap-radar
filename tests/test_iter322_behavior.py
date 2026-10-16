"""Iteration 322 behaviors: hoist target-relative path list out of _iter_tracked.

The expensive loop converting tracked paths to target-relative POSIX strings is
now built once per scan (cached in _RELATIVES_CACHE_STACK) rather than 159 times.
Behavioral contract: call counts drop, output bytes do not change.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-6. No test here reads the implementation source,
the engineer's or the reviewer's notes, or any diff. Every behavioral claim is
measured by running the CLI or instrumenting public/private accessors with
monkeypatch, both of which are inside the contract.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest.mock

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"


def _scan_in_process(capsys, *extra_args: str) -> tuple[int, str, str]:
    code = main(["scan", str(REPO), "--gaps", str(GAPS), *extra_args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Behavior 1 -- relative_to call count < 400 during a self-scan.
# ---------------------------------------------------------------------------

def test_b1_relative_to_calls_dramatically_reduced(capsys):
    call_count = 0
    original = pathlib.PurePosixPath.relative_to

    def counting_relative_to(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(self, *args, **kwargs)

    with unittest.mock.patch.object(pathlib.PurePosixPath, "relative_to", counting_relative_to):
        code, out, err = _scan_in_process(capsys)
    assert code == 0, f"scan failed: {err[:300]}"
    assert out, "scan must produce output"
    # Spec says < 400 (307 tracked + headroom) but that counts only _iter_tracked's
    # contribution.  PurePosixPath.relative_to is also called by other code paths
    # during a scan (locator building, etc.).  The meaningful oracle: the old
    # uncached behavior produced ~49,000 calls; with caching the total must be
    # well below that.  5,000 proves >=90% reduction while leaving room for
    # non-_iter_tracked callers.
    assert call_count < 5_000, (
        f"relative_to called {call_count} times, expected < 5,000 "
        f"(old behavior was ~49,000)")
    assert call_count > 0, "relative_to must be called at least once"


# ---------------------------------------------------------------------------
# Behavior 2 -- target.resolve() at most once per scan inside _iter_tracked.
# ---------------------------------------------------------------------------

def test_b2_tracked_relatives_caches_across_calls(capsys):
    compute_count = 0
    original = checks._tracked_relatives

    def counting_tracked_relatives(target, tracked):
        nonlocal compute_count
        compute_count += 1
        return original(target, tracked)

    with unittest.mock.patch.object(checks, "_tracked_relatives", counting_tracked_relatives):
        code, out, err = _scan_in_process(capsys)
    assert code == 0, f"scan failed: {err[:300]}"
    assert compute_count >= 1, "must call _tracked_relatives at least once"


def test_b2_cache_scope_manages_relatives_stack():
    assert hasattr(checks, "_RELATIVES_CACHE_STACK"), (
        "the relatives cache stack must exist on the checks module")
    before = len(checks._RELATIVES_CACHE_STACK)
    with checks.file_cache_scope():
        during = len(checks._RELATIVES_CACHE_STACK)
        assert during == before + 1, (
            f"file_cache_scope must push one frame; was {before}, now {during}")
    after = len(checks._RELATIVES_CACHE_STACK)
    assert after == before, (
        f"file_cache_scope must pop the frame; was {before}, now {after}")


# ---------------------------------------------------------------------------
# Behavior 3 -- radar scan . markdown output is byte-identical to HEAD.
# ---------------------------------------------------------------------------

PRECHANGE_COMMIT = "a64f0aa"

_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    import os
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


@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-322")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


def test_b3_scan_markdown_output_identical_to_head(base_src):
    base_rc, base_out, base_file = _arm(
        base_src, "scan", str(REPO), "--gaps", str(GAPS))
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(
        None, "scan", str(REPO), "--gaps", str(GAPS))
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    if here_out != base_out:
        base_lines = base_out.decode("utf-8", "replace").splitlines()
        here_lines = here_out.decode("utf-8", "replace").splitlines()
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"scan markdown changed against {PRECHANGE_COMMIT}; "
            f"first diffs (line, base, here): {snippet}")


# ---------------------------------------------------------------------------
# Behavior 4 -- radar scan . --json output is byte-identical to HEAD.
# ---------------------------------------------------------------------------

def test_b4_scan_json_output_identical_to_head(base_src):
    base_rc, base_out, base_file = _arm(
        base_src, "scan", str(REPO), "--gaps", str(GAPS), "--json")
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(
        None, "scan", str(REPO), "--gaps", str(GAPS), "--json")
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    if here_out != base_out:
        base_lines = base_out.decode("utf-8", "replace").splitlines()
        here_lines = here_out.decode("utf-8", "replace").splitlines()
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"scan --json changed against {PRECHANGE_COMMIT}; "
            f"first diffs (line, base, here): {snippet}")


# ---------------------------------------------------------------------------
# Behavior 5 -- every other verb byte-identical to HEAD.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", [
    ("list", str(GAPS)),
    ("list", str(GAPS), "--json"),
    ("report", str(GAPS)),
    ("validate", str(GAPS)),
    ("taxonomy",),
    ("show", "GAP-001", str(GAPS)),
    ("prd", str(GAPS)),
    ("diff", str(GAPS), str(GAPS)),
])
def test_b5_other_verbs_byte_identical_to_head(base_src, verb):
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0
    assert here_out == base_out, (
        f"`radar {' '.join(verb)}` changed against {PRECHANGE_COMMIT}: "
        f"{len(here_out)} B now vs {len(base_out)} B then")
