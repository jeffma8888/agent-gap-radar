"""Iteration 309 behaviors: dead `_PublishedErrorParser` alias deleted.

The alias and its circular identity assertion are removed. The canonical
`PublishedErrorParser` and the `_fail` alias (which has production call sites)
are untouched. All verb output is unchanged.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors 1-8. No test here reads the implementation source,
the engineer's or the reviewer's notes, or any diff. Every behavioral claim is
measured by RUNNING the CLI or importing from it, or by reading tests/ files
(which is inside the contract).
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"


def _radar(*argv: str) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        capture_output=True, cwd=str(REPO_ROOT), timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


# -- B1: `_PublishedErrorParser` is absent from the cli module -----------------

def test_b1_private_alias_is_absent():
    from agent_gap_radar import cli
    assert not hasattr(cli, "_PublishedErrorParser"), (
        "cli._PublishedErrorParser should have been deleted")


# -- B2: `PublishedErrorParser` remains importable and is a subclass -----------

def test_b2_canonical_name_importable_and_is_parser_subclass():
    from agent_gap_radar.cli import PublishedErrorParser
    assert isinstance(PublishedErrorParser, type), "PublishedErrorParser must be a class"
    assert issubclass(PublishedErrorParser, argparse.ArgumentParser), (
        "PublishedErrorParser must subclass argparse.ArgumentParser")


# -- B3: `_fail` alias is untouched -------------------------------------------

def test_b3_fail_alias_still_exists():
    from agent_gap_radar import cli
    assert hasattr(cli, "_fail"), "cli._fail must still exist"
    assert hasattr(cli, "fail"), "cli.fail must still exist"
    assert cli._fail is cli.fail, "cli._fail must be the SAME object as cli.fail"


# -- B4: identity assertion removed from test_iter206 --------------------------

def test_b4_identity_assertion_deleted_from_test_iter206():
    content = (TESTS_DIR / "test_iter206_behavior.py").read_text()
    assert "_PublishedErrorParser" not in content, (
        "test_iter206_behavior.py must no longer reference _PublishedErrorParser")


# -- B5: `_fail is fail` assertion still in test_iter206 -----------------------

def test_b5_fail_identity_assertion_intact_in_test_iter206():
    content = (TESTS_DIR / "test_iter206_behavior.py").read_text()
    assert "cli._fail is cli.fail" in content, (
        "test_iter206_behavior.py must still contain the _fail identity assertion")


# -- B7: all verbs produce non-error output (byte-stability) -------------------

@pytest.mark.parametrize("argv", [
    ("list", "."),
    ("report", "."),
    ("taxonomy",),
    ("scan", ".", "--gaps", "gaps"),
    ("prd", "."),
    ("diff", ".", "."),
    ("validate", "."),
], ids=["list", "report", "taxonomy", "scan", "prd", "diff", "validate"])
def test_b7_verb_succeeds_with_nonempty_stdout(argv):
    rc, out, err = _radar(*argv)
    assert rc == 0, f"`radar {' '.join(argv)}` exited {rc}; stderr={err[:300]!r}"
    assert out, f"`radar {' '.join(argv)}` produced no stdout"
    assert out.endswith(b"\n"), f"output must end with exactly one newline"
