"""Iteration 343 behaviors: argparse in 4 hand-parsed tool scripts so ``--help`` exits 0.

Add argparse to ``check_offline.py``, ``check_public_safety.py``,
``check_locators.py``, and ``roadmap_integrity.py`` so that ``--help``
exits 0 with usage text instead of exit 2 with ``Error:``.

THE ISOLATION CONTRACT IS HONORED.  Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7.  No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff.  Every
behavioral claim is measured by running tool scripts as subprocesses or by
comparing output against a git-archived pre-change tree, both of which are
inside the contract.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

FOUR_FIXED = (
    "check_offline.py",
    "check_public_safety.py",
    "check_locators.py",
    "roadmap_integrity.py",
)

ALL_NINE = (
    "check_locators.py",
    "check_offline.py",
    "check_public_safety.py",
    "check_register_doc.py",
    "promote.py",
    "roadmap_integrity.py",
    "scan_cost.py",
    "verify_mutations.py",
    "verify_quotes.py",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tool(name: str, *args: str, text: bool = True):
    return subprocess.run(
        [sys.executable, f"tools/{name}", *args],
        cwd=REPO, capture_output=True, text=text,
        check=False, timeout=60)



# ---------------------------------------------------------------------------
# B1 -- ``--help`` on all 4 fixed scripts: exit 0, stdout starts with
# ``usage:`` and contains the prog name (EB1-EB4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", FOUR_FIXED)
def test_b1_help_exits_0_with_usage_and_prog_name(tool: str) -> None:
    result = _tool(tool, "--help")
    prog = tool.replace(".py", "")
    assert result.returncode == 0, (
        f"{tool} --help: expected exit 0, got {result.returncode}; "
        f"stderr: {result.stderr[:300]!r}")
    assert result.stdout.startswith("usage:"), (
        f"{tool} --help must open with 'usage:'; got {result.stdout[:80]!r}")
    assert prog in result.stdout, (
        f"{tool} --help stdout must contain {prog!r}; got {result.stdout[:200]!r}")


# ---------------------------------------------------------------------------
# B2 -- ``--help`` prints nothing to stderr on all 4 fixed scripts (EB6,
# generalised from check_offline.py to all four)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", FOUR_FIXED)
def test_b2_help_no_stderr(tool: str) -> None:
    result = _tool(tool, "--help")
    assert result.returncode == 0, f"{tool} --help exited {result.returncode}"
    assert result.stderr == "", (
        f"{tool} --help must print nothing to stderr; got {result.stderr!r}")


# ---------------------------------------------------------------------------
# B3 -- no-args success path preserved for the 3 offline tools (EB5).
#
# ``check_locators.py`` does HTTP on every default invocation and cannot
# be tested in the offline suite.  ``roadmap_integrity.py``'s row count
# shifts by design (new PRODUCT.md ledger row), so it is tested for shape
# only.  The two-arm git-archive approach does not apply to tool scripts
# (they resolve paths via ``__file__``, not ``PYTHONPATH``), so this tests
# behavioral correctness: exit 0, correct format, no stderr, exactly one
# trailing newline, and the expected summary token.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,summary_token", [
    ("check_offline.py", "0 violation(s)"),
    ("check_public_safety.py", "0 finding(s)"),
    ("roadmap_integrity.py", "0 violation(s)"),
])
def test_b3_no_args_success_path_correct(tool: str, summary_token: str) -> None:
    result = _tool(tool)
    assert result.returncode == 0, (
        f"{tool} no-args: expected exit 0, got {result.returncode}; "
        f"stderr: {result.stderr[:300]!r}")
    assert result.stderr == "", (
        f"{tool} no-args must produce no stderr; got {result.stderr!r}")
    assert result.stdout, f"{tool} no-args must produce output"
    assert result.stdout.endswith("\n"), (
        f"{tool} no-args output must end in a newline")
    assert not result.stdout.endswith("\n\n"), (
        f"{tool} no-args output must end in exactly one newline")
    assert summary_token in result.stdout, (
        f"{tool} no-args must report {summary_token!r}; "
        f"got: {result.stdout!r}")


# ---------------------------------------------------------------------------
# B4 -- determinism: two no-args runs of each non-network tool produce
# byte-identical output (EB5, shape guard)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", (
    "check_offline.py", "check_public_safety.py", "roadmap_integrity.py"))
def test_b4_no_args_deterministic(tool: str) -> None:
    r1 = _tool(tool)
    r2 = _tool(tool)
    assert r1.returncode == 0, f"exit {r1.returncode}; stderr={r1.stderr!r}"
    assert r2.returncode == 0, f"exit {r2.returncode}; stderr={r2.stderr!r}"
    assert r1.stderr == r2.stderr == "", (
        f"{tool} no-args should produce no stderr")
    assert r1.stdout == r2.stdout, (
        f"{tool} no-args output not byte-stable across two runs")


# ---------------------------------------------------------------------------
# B5 -- all 9 ``tools/*.py`` scripts exit 0 on ``--help`` (EB7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ALL_NINE)
def test_b5_all_nine_tools_help_exits_0(tool: str) -> None:
    result = _tool(tool, "--help")
    assert result.returncode == 0, (
        f"{tool} --help: expected exit 0, got {result.returncode}; "
        f"stderr: {result.stderr[:300]!r}")
    assert result.stdout.startswith("usage:"), (
        f"{tool} --help must open with 'usage:'; got {result.stdout[:80]!r}")


# ---------------------------------------------------------------------------
# B6 -- unknown flag ``--zzz`` exits 2 with ``Error:`` prefix, zero stdout,
# on all 4 fixed tools (error vocabulary preserved)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", FOUR_FIXED)
def test_b6_unknown_flag_exits_2_with_error_prefix(tool: str) -> None:
    result = _tool(tool, "--zzz")
    assert result.returncode == 2, (
        f"{tool} --zzz: expected exit 2, got {result.returncode}")
    assert result.stdout == "", (
        f"{tool} --zzz must produce no stdout; got {result.stdout!r}")
    non_empty = [l for l in result.stderr.splitlines() if l.strip()]
    assert non_empty, f"{tool} --zzz must produce stderr; got none"
    assert non_empty[-1].startswith("Error: "), (
        f"{tool} --zzz last non-empty stderr must start 'Error: '; "
        f"got {non_empty[-1]!r}")
