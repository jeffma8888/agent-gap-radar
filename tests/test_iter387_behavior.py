"""Iteration 387 -- tester pins for the `.python-version` interpreter pin.

Tests and env only: the repo gains `.python-version` so a fresh clone's uv venv
runs the interpreter the suite is verified on, and the iter 386 frozen-arm
retirement re-lands. Every node here is cheap: file bytes, git plumbing and module
text. It never scans and never builds a frozen tree.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
PIN = REPO_ROOT / ".python-version"
MODULES = ("test_iter264_behavior.py", "test_iter265_behavior.py", "test_iter296_behavior.py")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          timeout=60)


# Behavior 1 -------------------------------------------------------------------------
def test_tester_b1_python_version_bytes_are_exactly_one_minor_line():
    assert PIN.read_bytes() == b"3.13\n"


def test_tester_b1_python_version_is_not_gitignored():
    # A pin that .gitignore swallows would never reach a clone.
    proc = _git("check-ignore", "-q", ".python-version")
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)


# Behavior 2 -------------------------------------------------------------------------
def test_tester_b2_the_suite_runs_on_the_pinned_interpreter():
    major, minor = (int(part) for part in PIN.read_text(encoding="utf-8").strip().split("."))
    assert sys.version_info[:2] == (major, minor), sys.version


def test_tester_b2_pin_is_inside_requires_python():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'requires-python\s*=\s*">=\s*3\.(\d+)', pyproject)
    assert match, "requires-python lower bound not found"
    assert int(match.group(1)) <= 13


# Behavior 5 (corrected grep; PRECHANGE_COMMIT stays in iter264 by iter386 b7) ------
@pytest.mark.parametrize("module", MODULES)
def test_tester_b5_no_frozen_tree_build_machinery_remains(module):
    text = (TESTS / module).read_text(encoding="utf-8")
    hits = [line for line in text.splitlines()
            if re.search(r'"archive"|tarfile|PYTHONPATH', line)]
    assert hits == [], (module, hits)


@pytest.mark.parametrize("module", ("test_iter265_behavior.py", "test_iter296_behavior.py"))
def test_tester_b5_prechange_constant_is_gone_where_no_census_needs_it(module):
    assert "PRECHANGE_COMMIT" not in (TESTS / module).read_text(encoding="utf-8")

