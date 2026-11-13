"""Iteration 406 behaviors (tester, black-box): README's scan-scope promise is true.

README used to promise that vendored dependencies "cannot manufacture findings".
That was false in both scan modes, so the paragraph now opens with
`**What a scan reads.**` and states each mode's actual rule. Here the paragraph is
pinned to BOTH the code constant it names (`checks.SKIP_DIRS`) AND to real
scans of tmp trees in each mode, and the published rule is checked against what
the scan actually reports.

Spec behavior 8 ("src/ is byte-identical to the pre-change head") is checked by
hand in the tester report and deliberately NOT committed as a sha-pinned test,
because a committed sha pin would time-bomb on the next src change.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

import _selfscan
from _selfscan import selfscan_run_cache  # noqa: F401  (autouse: run-wide cache)

REPO = pathlib.Path(__file__).resolve().parents[1]
README = REPO / "README.md"
REGISTER = REPO / "gaps"
PKG = REPO / "src" / "agent_gap_radar"
LEAD = "**What a scan reads.**"


# --- helpers ----------------------------------------------------------------

def _paragraphs(text: str) -> list[str]:
    """Blocks of lines delimited by blank lines."""
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _the_paragraph() -> str:
    hits = [p for p in _paragraphs(README.read_text(encoding="utf-8"))
            if p.startswith(LEAD)]
    assert len(hits) == 1, f"expected exactly one {LEAD!r} paragraph, got {len(hits)}"
    return hits[0]


def _copy_pkg(dest: pathlib.Path) -> None:
    shutil.copytree(PKG, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _git_init(root: pathlib.Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")


def _scan_locations(target: pathlib.Path) -> list[str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(["scan", str(target), "--gaps", str(REGISTER), "--json"])
    assert rc == 0, err.getvalue()
    assert err.getvalue() == ""
    payload = json.loads(out.getvalue())
    return [loc for row in payload["findings"] for loc in row["locations"]]


# --- behaviors 1-5: the README paragraph ------------------------------------

def test_b1_false_promise_is_gone():
    assert "cannot manufacture findings" not in README.read_text(encoding="utf-8")


def test_b2_exactly_one_what_a_scan_reads_paragraph():
    assert _the_paragraph().startswith(LEAD)


def test_b2_paragraph_counter_counts_blank_line_blocks():
    """The helper the pins rely on: blank-line blocks, leading-literal match only."""
    text = f"{LEAD} a\nb\n\nx {LEAD}\n\n\n{LEAD} c\n"
    blocks = _paragraphs(text)
    assert blocks == [f"{LEAD} a\nb", f"x {LEAD}", f"{LEAD} c"]
    assert sum(b.startswith(LEAD) for b in blocks) == 2


@pytest.mark.parametrize("needle", ["git ls-files", "untracked", "gitignored",
                                    "vendored", "is scanned"])
def test_b3_paragraph_names_each_mode_rule(needle):
    assert needle in _the_paragraph()


def test_b4_backticked_names_equal_skip_dirs():
    tokens = re.findall(r"`([^`]+)`", _the_paragraph())
    assert "git ls-files" in tokens
    rest = list(tokens)
    rest.remove("git ls-files")
    assert set(rest) == set(checks.SKIP_DIRS), sorted(set(rest) ^ set(checks.SKIP_DIRS))


def test_b4_skip_dirs_is_the_published_twelve():
    assert set(checks.SKIP_DIRS) == {
        ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
        "dist", "build", ".mypy_cache", ".ruff_cache", ".tox", "target",
    }


def test_b5_second_sentence_survives():
    assert "Locators are ranked code-first and capped" in README.read_text(encoding="utf-8")


# --- behavior 6: git mode reads exactly what git ls-files lists ------------

def test_b6_git_mode_scans_committed_vendor_but_not_untracked_or_ignored(tmp_path):
    t = tmp_path / "gitmode"
    t.mkdir()
    _copy_pkg(t / "vendor" / "lib")
    _copy_pkg(t / "ignored")
    (t / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git_init(t)
    _git(t, "add", "-A")
    _git(t, "commit", "-q", "-m", "t")
    _copy_pkg(t / "scratch")  # untracked, not ignored
    locs = _scan_locations(t)
    assert any(loc.startswith("vendor/lib/") for loc in locs), locs
    assert not [loc for loc in locs if loc.startswith(("scratch/", "ignored/"))]


def test_b6_git_mode_untracked_and_ignored_alone_cite_nothing(tmp_path):
    """Without a vendored copy competing for capped slots, the exclusion still holds."""
    t = tmp_path / "gitmode_alone"
    t.mkdir()
    (t / "app.py").write_text("x = 1\n", encoding="utf-8")
    (t / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _copy_pkg(t / "ignored")
    _git_init(t)
    _git(t, "add", "-A")
    _git(t, "commit", "-q", "-m", "t")
    _copy_pkg(t / "scratch")
    locs = _scan_locations(t)
    assert not [loc for loc in locs if loc.startswith(("scratch/", "ignored/"))]


# --- behavior 7: off-git walks everything except SKIP_DIRS -----------------

def test_b7_off_git_scans_vendor_but_prunes_node_modules(tmp_path):
    t = tmp_path / "nogit"
    t.mkdir()
    _copy_pkg(t / "vendor" / "lib")
    _copy_pkg(t / "node_modules" / "lib")
    assert not (t / ".git").exists()
    locs = _scan_locations(t)
    assert any(loc.startswith("vendor/lib/") for loc in locs), locs
    assert not [loc for loc in locs if loc.startswith("node_modules/")]


def test_b7_off_git_node_modules_alone_cites_nothing(tmp_path):
    t = tmp_path / "nogit_alone"
    t.mkdir()
    _copy_pkg(t / "node_modules" / "lib")
    locs = _scan_locations(t)
    assert not [loc for loc in locs if loc.startswith("node_modules/")]


def test_b7_off_git_a_published_name_nested_deeper_is_pruned(tmp_path):
    """The rule is 'directories NAMED x', so a nested `build/` is pruned too."""
    t = tmp_path / "nogit_nested"
    t.mkdir()
    _copy_pkg(t / "pkg" / "build" / "lib")
    _copy_pkg(t / "pkg" / "vendored" / "lib")
    locs = _scan_locations(t)
    assert any(loc.startswith("pkg/vendored/lib/") for loc in locs), locs
    assert not [loc for loc in locs if loc.startswith("pkg/build/")]


# --- behavior 8: the live self-scan cites no README locator ----------------

def test_b8_self_scan_cites_no_readme_locator():
    rc, out, err = _selfscan.selfscan(("--json",))
    assert rc == 0, err
    payload = json.loads(out)
    locs = [loc for row in payload["findings"] for loc in row["locations"]]
    assert locs, "an empty self-scan would make this pin vacuous"
    assert not [loc for loc in locs if loc.split(":", 1)[0] == "README.md"]
