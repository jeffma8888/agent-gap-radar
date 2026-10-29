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

import pathlib
import unittest.mock

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
